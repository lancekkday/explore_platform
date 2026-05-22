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
    # WAL lets readers (polling /status, /history) proceed concurrently
    # with the worker thread's checkpoint writes — without WAL, sqlite
    # serializes everything and the 2s poll interval can pile up behind
    # a slow UPDATE.
    conn.execute("PRAGMA journal_mode=WAL")
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
    """
    Mark any in-flight runs as interrupted. Call at backend startup.
    Also flips orphan checkpoint rows from 'running' back to 'pending',
    otherwise history detail view shows a phantom "executing" row forever.
    """
    init_schema()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE ab_check_runs SET status=?, finished_at=? WHERE status=?",
            (RUN_STATUS_INTERRUPTED, _now_iso(), RUN_STATUS_RUNNING),
        )
        n_runs = cur.rowcount
        # Reset orphan checkpoint rows that were mid-flight when the process died.
        # Anything in 'running' status now is necessarily orphaned (worker is gone).
        conn.execute(
            "UPDATE ab_check_checkpoints SET status='pending' WHERE status=?",
            (CHECKPOINT_RUNNING_,),
        )
        return n_runs


def force_interrupt_run(run_id: str) -> bool:
    """
    Flip a run that is `running` in DB but has no live worker (e.g. worker
    crashed silently) to `interrupted`. Returns True if the row was actually
    updated. Same checkpoint-cleanup as sweep_interrupted_runs.
    """
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE ab_check_runs SET status=?, finished_at=? "
            "WHERE run_id=? AND status=?",
            (RUN_STATUS_INTERRUPTED, _now_iso(), run_id, RUN_STATUS_RUNNING),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "UPDATE ab_check_checkpoints SET status='pending' "
            "WHERE run_id=? AND status=?",
            (run_id, CHECKPOINT_RUNNING_),
        )
        return True


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


# ── Read helpers (consumed by API endpoints) ──────────────────────────────────

_RUN_COLS = (
    "run_id, type, status, version_a, version_b, limit_n, total_queries, "
    "done_count, baseline_version, error_msg, started_at, finished_at, "
    "summary_json, parent_run_id"
)


def _row_to_run_dict(row) -> dict:
    keys = [c.strip() for c in _RUN_COLS.split(",")]
    d = dict(zip(keys, row))
    # Parse summary_json for convenience
    if d.get("summary_json"):
        try:
            d["summary"] = json.loads(d["summary_json"])
        except json.JSONDecodeError:
            d["summary"] = None
    else:
        d["summary"] = None
    return d


def get_run(run_id: str) -> Optional[dict]:
    """Return run meta as dict, or None if not found."""
    with _connect() as conn:
        cur = conn.execute(
            f"SELECT {_RUN_COLS} FROM ab_check_runs WHERE run_id=?",
            (run_id,),
        )
        row = cur.fetchone()
    return _row_to_run_dict(row) if row else None


def get_checkpoints(run_id: str, since_idx: int = 0) -> list[dict]:
    """Return checkpoint rows for run_id where query_idx >= since_idx, ordered by idx."""
    with _connect() as conn:
        cur = conn.execute(
            """SELECT query_idx, query, status, alerts_json, error_msg, finished_at
               FROM ab_check_checkpoints
               WHERE run_id=? AND query_idx >= ?
               ORDER BY query_idx""",
            (run_id, since_idx),
        )
        rows = cur.fetchall()
    out: list[dict] = []
    for idx, q, status, alerts_json, err, fin in rows:
        alerts = None
        if alerts_json:
            try:
                alerts = json.loads(alerts_json)
            except json.JSONDecodeError:
                alerts = None
        out.append({
            "query_idx": idx,
            "query": q,
            "status": status,
            "alerts": alerts,
            "error_msg": err,
            "finished_at": fin,
        })
    return out


def get_running_idx(run_id: str) -> Optional[int]:
    """Return the query_idx currently `running` (at most one), or None."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT query_idx FROM ab_check_checkpoints "
            "WHERE run_id=? AND status=? LIMIT 1",
            (run_id, CHECKPOINT_RUNNING_),
        )
        row = cur.fetchone()
    return row[0] if row else None


def list_runs(type_: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List recent runs (most-recent first). Filter by type if provided."""
    limit = max(1, min(limit, 500))
    sql = f"SELECT {_RUN_COLS} FROM ab_check_runs"
    args: tuple = ()
    if type_:
        sql += " WHERE type=?"
        args = (type_,)
    sql += " ORDER BY started_at DESC LIMIT ?"
    args = args + (limit,)
    with _connect() as conn:
        cur = conn.execute(sql, args)
        rows = cur.fetchall()
    return [_row_to_run_dict(r) for r in rows]


# ── Worker loop ────────────────────────────────────────────────────────────────

def _run_worker(
    run_id: str,
    type_: str,
    queue,
    version_a: int,
    version_b: int,
    cookie: str,
    cancel_flag: threading.Event,
    skip_idx: Optional[set[int]] = None,
    seed_counts: Optional[dict] = None,
) -> None:
    """同步單緒跑 queue。每跑完一個 query 就 commit 一次 checkpoint。

    skip_idx: query_idx 已從 parent run 複製過來(status=ok),worker 直接跳過。
    seed_counts: parent run 的累積 alert tally,合到本 run 的 summary。
    """
    skip_idx = skip_idx or set()
    cache: dict[tuple[str, int], tuple[int, ...]] = {}
    severity_counts = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    total_alerts = 0
    if seed_counts:
        total_alerts = seed_counts.get("total", 0)
        for k in ("P0", "P1", "P2", "INFO"):
            severity_counts[k] = seed_counts.get(k, 0)

    for idx, item in enumerate(queue):
        if cancel_flag.is_set():
            _finish_run(run_id, RUN_STATUS_CANCELLED)
            logger.info(f"[ABRunner] run={run_id} cancelled at idx={idx}")
            return

        if idx in skip_idx:
            continue

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

def _copy_parent_done_rows(
    new_run_id: str,
    parent_run_id: str,
    total_new: int,
    type_new: str,
    version_a_new: int,
    version_b_new: int,
    baseline_new: str,
    queries_new: list[str],
) -> tuple[set[int], dict]:
    """
    Copy parent run's status='ok' checkpoint rows into the new run (alerts_json
    preserved). Returns (skip_idx, seed_counts). Bails (returns empty) if the
    parent run's "queue identity" doesn't match the new run — i.e. any of:
      - type differs
      - total_queries differs
      - version_a/version_b differs (alerts were computed under different AB)
      - baseline_version differs (queue ordering / row set may have shifted)
      - per-idx query text differs (defensive: catches sort-order drift inside
        the same baseline_version)
    """
    with _connect() as conn:
        parent = conn.execute(
            """SELECT total_queries, type, version_a, version_b, baseline_version
               FROM ab_check_runs WHERE run_id=?""",
            (parent_run_id,),
        ).fetchone()
        if not parent:
            logger.warning(f"[ABRunner] resume parent={parent_run_id!r} not found, falling back to full run")
            return set(), {}
        parent_total, parent_type, parent_va, parent_vb, parent_baseline = parent
        if parent_type != type_new:
            logger.warning(f"[ABRunner] resume parent type={parent_type!r} != {type_new!r}, skipping copy")
            return set(), {}
        if parent_total != total_new:
            logger.warning(f"[ABRunner] resume parent total={parent_total} != new total={total_new}, skipping copy")
            return set(), {}
        if parent_va != version_a_new or parent_vb != version_b_new:
            logger.warning(
                f"[ABRunner] resume parent A/B=({parent_va},{parent_vb}) != "
                f"new A/B=({version_a_new},{version_b_new}); alerts would be "
                f"misattributed across versions — skipping copy, running fresh"
            )
            return set(), {}
        if parent_baseline != baseline_new:
            logger.warning(
                f"[ABRunner] resume parent baseline={parent_baseline!r} != "
                f"new baseline={baseline_new!r}; queue ordering may have shifted "
                f"— skipping copy, running fresh"
            )
            return set(), {}

        ok_rows = conn.execute(
            """SELECT query_idx, query, alerts_json
               FROM ab_check_checkpoints
               WHERE run_id=? AND status='ok'""",
            (parent_run_id,),
        ).fetchall()
        if not ok_rows:
            return set(), {}

        # Defensive per-idx text check — if anything mismatches we bail entirely.
        for idx, parent_query, _ in ok_rows:
            if 0 <= idx < len(queries_new) and queries_new[idx] != parent_query:
                logger.warning(
                    f"[ABRunner] resume parent idx={idx} query={parent_query!r} != "
                    f"new query={queries_new[idx]!r}; ordering drift — skipping copy"
                )
                return set(), {}

        now = _now_iso()
        conn.executemany(
            """UPDATE ab_check_checkpoints
               SET status='ok', alerts_json=?, finished_at=?
               WHERE run_id=? AND query_idx=?""",
            [(alerts_json, now, new_run_id, idx) for idx, _q, alerts_json in ok_rows],
        )
        conn.execute(
            "UPDATE ab_check_runs SET done_count=? WHERE run_id=?",
            (len(ok_rows), new_run_id),
        )

    # Tally alert counts so the resumed run's summary stays consistent.
    seed_counts = {"total": 0, "P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    for _, _q, alerts_json in ok_rows:
        if not alerts_json:
            continue
        try:
            alerts = json.loads(alerts_json)
        except json.JSONDecodeError:
            continue
        for a in alerts or []:
            seed_counts["total"] += 1
            sev = a.get("severity")
            if sev in seed_counts:
                seed_counts[sev] += 1

    skip_idx = {idx for idx, _q, _ in ok_rows}
    logger.info(f"[ABRunner] resume from {parent_run_id} → {new_run_id}: skipping {len(skip_idx)} idx")
    return skip_idx, seed_counts


def start_run(
    type_: str,
    version_a: int,
    version_b: int,
    cookie: str = "",
    limit: Optional[int] = None,
    resume_run_id: Optional[str] = None,
    sync: bool = False,
) -> str:
    """啟動一個 run,回傳 run_id。

      sync=True : foreground (CLI / 測試)
      sync=False: daemon thread (API endpoint)

    resume_run_id: 帶入時,parent run 已 status='ok' 的 idx 會被複製進新 run
    的 checkpoint(含 alerts_json),worker 跳過那些 idx 只跑剩下的。Queue 順序
    必須跟 parent 一致(同 baseline + 同 limit)否則 fallback 全跑。
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

    skip_idx: set[int] = set()
    seed_counts: dict = {}
    if resume_run_id:
        skip_idx, seed_counts = _copy_parent_done_rows(
            run_id, resume_run_id, total,
            type_new=type_,
            version_a_new=version_a,
            version_b_new=version_b,
            baseline_new=baseline_ts,
            queries_new=queries,
        )

    cancel_flag = _new_cancel_flag(run_id)

    def _target():
        try:
            _run_worker(
                run_id, type_, queue, version_a, version_b, cookie, cancel_flag,
                skip_idx=skip_idx, seed_counts=seed_counts,
            )
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
