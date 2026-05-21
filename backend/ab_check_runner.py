"""
backend/ab_check_runner.py
==========================

Independent AB-check runner with sqlite-checkpointed runs.

Goals separate from ab_check.run_ab_check():
  - Pre-insert all queries as `pending` checkpoints so progress is observable
    from query 0
  - Single-threaded per run (粒度細,降低 SIT 504 timeout 風險)
  - precise / broad 可平行(獨立 run、獨立 daemon thread)
  - resume / cancel / startup-sweep hooks 預留,實際接線在後續 step

Schema 寫進現有 backend/data/history.db（與 batch_engine 共用,但 table 隔離）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from ab_check import (
    process_one_precise_query,
    process_one_broad_query,
)
from baseline_service import baseline_service
from baseline_version_manager import baseline_version_manager

# 與 batch_engine 共用 history.db,但 table 隔離(ab_check_runs / ab_check_checkpoints)。
# 不從 batch_engine import 是為了避免 CLI 拉進 kkday_api / skills 一整串相依。
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "data", "history.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

TZ_TAIPEI = timezone(timedelta(hours=8))

RUN_STATUS_RUNNING = "running"
RUN_STATUS_DONE = "done"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_INTERRUPTED = "interrupted"
RUN_STATUS_CANCELLED = "cancelled"

CHECKPOINT_PENDING = "pending"
CHECKPOINT_RUNNING_ = "running"
CHECKPOINT_OK = "ok"
CHECKPOINT_ERROR = "error"


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema() -> None:
    """Create ab_check_runs / ab_check_checkpoints tables if missing. Idempotent."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ab_check_runs (
              run_id              TEXT PRIMARY KEY,
              type                TEXT NOT NULL,
              status              TEXT NOT NULL,
              version_a           INTEGER NOT NULL,
              version_b           INTEGER NOT NULL,
              limit_n             INTEGER,
              total_queries       INTEGER NOT NULL,
              done_count          INTEGER DEFAULT 0,
              baseline_version    TEXT NOT NULL,
              error_msg           TEXT,
              started_at          TEXT NOT NULL,
              finished_at         TEXT,
              summary_json        TEXT,
              parent_run_id       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_type_started
              ON ab_check_runs(type, started_at DESC);

            CREATE TABLE IF NOT EXISTS ab_check_checkpoints (
              run_id       TEXT NOT NULL,
              query_idx    INTEGER NOT NULL,
              query        TEXT NOT NULL,
              status       TEXT NOT NULL,
              alerts_json  TEXT,
              error_msg    TEXT,
              finished_at  TEXT,
              PRIMARY KEY (run_id, query_idx)
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoints_run
              ON ab_check_checkpoints(run_id);
            """
        )


def sweep_interrupted_runs() -> int:
    """Mark any in-flight runs as interrupted. Call once at backend startup."""
    init_schema()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE ab_check_runs SET status=? WHERE status=?",
            (RUN_STATUS_INTERRUPTED, RUN_STATUS_RUNNING),
        )
        return cur.rowcount


# ── Cancellation registry (in-memory) ─────────────────────────────────────────

_cancel_flags: dict[str, threading.Event] = {}
_cancel_flags_lock = threading.Lock()


def request_cancel(run_id: str) -> bool:
    with _cancel_flags_lock:
        flag = _cancel_flags.get(run_id)
    if flag is None:
        return False
    flag.set()
    return True


def _new_cancel_flag(run_id: str) -> threading.Event:
    flag = threading.Event()
    with _cancel_flags_lock:
        _cancel_flags[run_id] = flag
    return flag


def _clear_cancel_flag(run_id: str) -> None:
    with _cancel_flags_lock:
        _cancel_flags.pop(run_id, None)


# ── Query selection / limit ────────────────────────────────────────────────────

def _select_precise_queue(limit: Optional[int]) -> list[dict]:
    """precise 按 search_pv DESC NULLS LAST 排,取 top N。"""
    rows = list(baseline_service._precise.values())
    rows.sort(
        key=lambda r: (r.get("search_pv") is not None, r.get("search_pv") or 0),
        reverse=True,
    )
    if limit and limit > 0:
        rows = rows[:limit]
    return rows


def _select_broad_queue(limit: Optional[int]) -> list[tuple[str, list[dict]]]:
    """broad 按 sum(profit) DESC 排,取 top N query (該 query 整組 row 一起跑)。"""
    items = list(baseline_service._broad.items())
    items.sort(
        key=lambda kv: sum((r.get("profit") or 0.0) for r in kv[1]),
        reverse=True,
    )
    if limit and limit > 0:
        items = items[:limit]
    return items


# ── Run state mutators ────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(TZ_TAIPEI).isoformat()


def _get_active_baseline_ts() -> str:
    meta = baseline_version_manager.get_active_version()
    return meta.get("timestamp") if meta else ""


def _insert_run(run_id, type_, version_a, version_b, limit_n, total,
                baseline_version, parent_run_id) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO ab_check_runs
                 (run_id, type, status, version_a, version_b, limit_n,
                  total_queries, baseline_version, started_at, parent_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, type_, RUN_STATUS_RUNNING, version_a, version_b, limit_n,
             total, baseline_version, _now_iso(), parent_run_id),
        )


def _insert_initial_checkpoints(run_id: str, queries: list[str]) -> None:
    with _connect() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO ab_check_checkpoints
                 (run_id, query_idx, query, status)
               VALUES (?, ?, ?, ?)""",
            [(run_id, idx, q, CHECKPOINT_PENDING) for idx, q in enumerate(queries)],
        )


def _set_checkpoint(run_id, idx, status, alerts_json=None, error_msg=None) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE ab_check_checkpoints
               SET status=?, alerts_json=?, error_msg=?, finished_at=?
               WHERE run_id=? AND query_idx=?""",
            (
                status,
                alerts_json,
                error_msg,
                _now_iso() if status in (CHECKPOINT_OK, CHECKPOINT_ERROR) else None,
                run_id,
                idx,
            ),
        )


def _bump_done_count(run_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE ab_check_runs SET done_count = done_count + 1 WHERE run_id=?",
            (run_id,),
        )


def _finish_run(run_id, status, summary_json=None, error_msg=None) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE ab_check_runs
               SET status=?, finished_at=?, summary_json=?, error_msg=?
               WHERE run_id=?""",
            (status, _now_iso(), summary_json, error_msg, run_id),
        )


# ── Worker loop ────────────────────────────────────────────────────────────────

def _run_worker(
    run_id: str,
    type_: str,
    queue,
    version_a: int,
    version_b: int,
    cookie: str,
    cancel_flag: threading.Event,
) -> None:
    """同步單緒跑 queue。每跑完一個 query 就 commit 一次 checkpoint。"""
    cache: dict[tuple[str, int], tuple[int, ...]] = {}
    severity_counts = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    total_alerts = 0

    for idx, item in enumerate(queue):
        if cancel_flag.is_set():
            _finish_run(run_id, RUN_STATUS_CANCELLED)
            logger.info(f"[ABRunner] run={run_id} cancelled at idx={idx}")
            return

        if type_ == "precise":
            row = item
            query = row["query"]
        else:
            query, group = item

        _set_checkpoint(run_id, idx, CHECKPOINT_RUNNING_)

        try:
            if type_ == "precise":
                alerts = process_one_precise_query(row, version_a, version_b, cookie, cache)
            else:
                alerts = process_one_broad_query(query, group, version_a, version_b, cookie, cache)

            alerts_dicts = [asdict(a) for a in alerts]
            _set_checkpoint(
                run_id, idx, CHECKPOINT_OK,
                alerts_json=json.dumps(alerts_dicts, ensure_ascii=False),
            )
            _bump_done_count(run_id)

            total_alerts += len(alerts)
            for a in alerts:
                severity_counts[a.severity] = severity_counts.get(a.severity, 0) + 1

        except Exception as e:
            logger.error(f"[ABRunner] run={run_id} idx={idx} query={query!r} error: {e}")
            _set_checkpoint(run_id, idx, CHECKPOINT_ERROR, error_msg=str(e))

    summary = {"total": total_alerts, **severity_counts}
    _finish_run(run_id, RUN_STATUS_DONE, summary_json=json.dumps(summary, ensure_ascii=False))
    logger.info(f"[ABRunner] run={run_id} done — {summary}")


# ── Public entry point ────────────────────────────────────────────────────────

def start_run(
    type_: str,
    version_a: int,
    version_b: int,
    cookie: str = "",
    limit: Optional[int] = None,
    resume_run_id: Optional[str] = None,
    sync: bool = False,
) -> str:
    """
    啟動一個 run,回傳 run_id。
      sync=True : foreground (給 CLI / 測試用)
      sync=False: daemon thread (API endpoint 用,等 step 3)

    resume_run_id 目前先記在 parent_run_id 欄;實際續跑邏輯留待 step 3 接 API
    時補完(需 UI 配合)。
    """
    if type_ not in ("precise", "broad"):
        raise ValueError(f"unknown run type: {type_}")

    init_schema()

    if type_ == "precise":
        queue = _select_precise_queue(limit)
        queries = [r["query"] for r in queue]
    else:
        queue = _select_broad_queue(limit)
        queries = [q for q, _ in queue]

    run_id = uuid.uuid4().hex
    total = len(queue)
    baseline_ts = _get_active_baseline_ts()

    _insert_run(run_id, type_, version_a, version_b, limit, total, baseline_ts, resume_run_id)
    _insert_initial_checkpoints(run_id, queries)

    cancel_flag = _new_cancel_flag(run_id)

    def _target():
        try:
            _run_worker(run_id, type_, queue, version_a, version_b, cookie, cancel_flag)
        except Exception as e:
            logger.exception(f"[ABRunner] run={run_id} fatal: {e}")
            _finish_run(run_id, RUN_STATUS_FAILED, error_msg=str(e))
        finally:
            _clear_cancel_flag(run_id)

    if sync:
        _target()
    else:
        threading.Thread(
            target=_target,
            name=f"ab-check-runner-{run_id[:8]}",
            daemon=True,
        ).start()

    return run_id


# ── CLI ────────────────────────────────────────────────────────────────────────

def _print_run_summary(run_id: str) -> None:
    with _connect() as conn:
        cur = conn.execute(
            """SELECT status, done_count, total_queries, summary_json, error_msg,
                      baseline_version, started_at, finished_at
               FROM ab_check_runs WHERE run_id=?""",
            (run_id,),
        )
        row = cur.fetchone()
    if not row:
        print(f"run_id={run_id} NOT FOUND")
        return
    status, done, total, summary, err, baseline, started, finished = row
    print(f"run_id={run_id}")
    print(f"  status     = {status}")
    print(f"  progress   = {done}/{total}")
    print(f"  baseline   = {baseline}")
    print(f"  started_at = {started}")
    print(f"  finished_at= {finished}")
    print(f"  summary    = {summary}")
    if err:
        print(f"  error      = {err}")


def _main() -> None:
    ap = argparse.ArgumentParser(
        description="AB-check standalone runner (sqlite-checkpointed). "
                    "Use for local dev / CLI smoke; API endpoints land in step 3."
    )
    ap.add_argument("--type", choices=["precise", "broad"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="top-N queries (default: 全跑)")
    ap.add_argument("--version-a", type=int, default=0)
    ap.add_argument("--version-b", type=int, default=1)
    ap.add_argument("--cookie", default="", help="guest cookie for KKDay search v3")
    ap.add_argument("--resume", default=None, help="resume_run_id (parent reference)")
    args = ap.parse_args()

    run_id = start_run(
        type_=args.type,
        version_a=args.version_a,
        version_b=args.version_b,
        cookie=args.cookie,
        limit=args.limit,
        resume_run_id=args.resume,
        sync=True,
    )
    _print_run_summary(run_id)


if __name__ == "__main__":
    _main()
