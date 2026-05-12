"""
搜尋詞 AB 巡檢核心模組
======================

從 handoff/scripts/keyword_ab_check.py 搬入並接上 fetch_kkday_products_v3。
提供 run_ab_check() 供 main.py endpoint 呼叫。
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from kkday_api import fetch_kkday_products_v3

# ── 閾值 ──────────────────────────────────────────────────────────────────────
PRECISE_DROP_THRESHOLD = 5
BROAD_DELTA_THRESHOLD = 5

SIDE_PRECISE_TOP1_MAX_RANK = 10
SIDE_PRECISE_TOP2_MAX_RANK = 15
SIDE_BROAD_RANK_DELTA = 20

API_PARALLEL_WORKERS = 10
API_MAX_RESULTS = 300

# ── Baseline CSV 路徑 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
HANDOFF_DATA = BASE_DIR / "handoff" / "data"
PRECISE_CSV = HANDOFF_DATA / "search_keyword_precise.csv"
BROAD_CSV = HANDOFF_DATA / "search_keyword_broad.csv"


@dataclass
class Alert:
    alert_type: str       # 'main' | 'side'
    keyword_type: str     # 'precise' | 'broad'
    query: str
    prod_mid: int
    baseline_rank: int
    a_rank: Optional[int]
    b_rank: Optional[int]
    severity: str         # 'P0' | 'P1' | 'P2' | 'INFO'
    reason: str


# ── API 呼叫 ─────────────────────────────────────────────────────────────────


def _fetch_results(query: str, version: int, cookie: str, cache: dict = None) -> tuple[int, ...]:
    """呼叫 v3 search API，回傳 prod_mid tuple（有 cache）"""
    key = (query, version)
    if cache is not None and key in cache:
        return cache[key]
    try:
        prods, _, _ = fetch_kkday_products_v3(
            keyword=query, env="stage", cookie=cookie,
            row_count=API_MAX_RESULTS, test_exp=version,
        )
        mids = tuple(
            p.get("prod_mid") or p.get("prod_oid") or 0
            for p in prods
        )
        if cache is not None:
            cache[key] = mids
        return mids
    except Exception as e:
        logger.error(f"[AB] API error query={query!r} version={version}: {e}")
        if cache is not None:
            cache[key] = ()
        return ()


def find_rank(mid: int, results: tuple[int, ...]) -> Optional[int]:
    try:
        return results.index(mid) + 1
    except ValueError:
        return None


# ── 精準詞檢查 ───────────────────────────────────────────────────────────────

def check_a_health_precise(query, mid, baseline_rank, a_rank) -> Optional[Alert]:
    threshold = SIDE_PRECISE_TOP1_MAX_RANK if baseline_rank == 1 else SIDE_PRECISE_TOP2_MAX_RANK
    if a_rank is None:
        return Alert(
            alert_type="side", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=None, b_rank=None, severity="INFO",
            reason=f"baseline Top{baseline_rank} 商品在 A 版找不到",
        )
    if a_rank > threshold:
        return Alert(
            alert_type="side", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None, severity="INFO",
            reason=f"baseline Top{baseline_rank} 在 A 版排到第 {a_rank} 位 (>閾值 {threshold})",
        )
    return None


def check_ab_precise(query, mid, baseline_rank, a_rank, b_rank) -> Optional[Alert]:
    if a_rank is None:
        return None
    if b_rank is None:
        return Alert(
            alert_type="main", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None,
            severity="P0" if baseline_rank == 1 else "P1",
            reason=f"A 版第 {a_rank} 位,B 版完全消失",
        )
    drop = b_rank - a_rank
    if drop > PRECISE_DROP_THRESHOLD:
        return Alert(
            alert_type="main", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=b_rank,
            severity="P1" if baseline_rank == 1 else "P2",
            reason=f"A 版第 {a_rank} 位 → B 版第 {b_rank} 位 (掉 {drop} 名)",
        )
    return None


def _process_precise_query(row, version_a, version_b, cookie, cache=None) -> list[Alert]:
    query = row["query"]
    a_results = _fetch_results(query, version_a, cookie, cache)
    b_results = _fetch_results(query, version_b, cookie, cache)

    alerts = []
    for rank_n, mid_col in [(1, "top1_prod_mid"), (2, "top2_prod_mid")]:
        mid = row[mid_col]
        if pd.isna(mid):
            continue
        mid = int(mid)
        a_rank = find_rank(mid, a_results)
        b_rank = find_rank(mid, b_results)

        side = check_a_health_precise(query, mid, rank_n, a_rank)
        if side:
            alerts.append(side)
        main = check_ab_precise(query, mid, rank_n, a_rank, b_rank)
        if main:
            alerts.append(main)
    return alerts


# ── 泛詞檢查 ─────────────────────────────────────────────────────────────────

def check_a_health_broad(query, mid, baseline_rank, a_rank) -> Optional[Alert]:
    if a_rank is None:
        if baseline_rank <= 3:
            return Alert(
                alert_type="side", keyword_type="broad", query=query, prod_mid=mid,
                baseline_rank=baseline_rank, a_rank=None, b_rank=None, severity="INFO",
                reason=f"baseline profit_rank={baseline_rank} 商品在 A 版找不到",
            )
        return None
    delta = abs(a_rank - baseline_rank)
    if delta > SIDE_BROAD_RANK_DELTA:
        return Alert(
            alert_type="side", keyword_type="broad", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None, severity="INFO",
            reason=f"baseline profit_rank={baseline_rank} 在 A 版第 {a_rank} 位 (偏離 {delta} 名)",
        )
    return None


def check_ab_broad(query, mid, baseline_rank, a_rank, b_rank) -> Optional[Alert]:
    if a_rank is None:
        return None
    if b_rank is None:
        return Alert(
            alert_type="main", keyword_type="broad", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None,
            severity="P1" if baseline_rank <= 3 else "P2",
            reason=f"A 版第 {a_rank} 位,B 版完全消失",
        )
    delta = b_rank - a_rank
    if abs(delta) > BROAD_DELTA_THRESHOLD:
        direction = "下降" if delta > 0 else "上升"
        return Alert(
            alert_type="main", keyword_type="broad", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=b_rank,
            severity="P1" if baseline_rank <= 3 else "P2",
            reason=f"A 版第 {a_rank} 位 → B 版第 {b_rank} 位 ({direction} {abs(delta)} 名)",
        )
    return None


def _process_broad_query(query, group, version_a, version_b, cookie, cache=None) -> list[Alert]:
    a_results = _fetch_results(query, version_a, cookie, cache)
    b_results = _fetch_results(query, version_b, cookie, cache)

    alerts = []
    for _, row in group.iterrows():
        mid = int(row["prod_mid"])
        baseline_rank = int(row["profit_rank"])
        a_rank = find_rank(mid, a_results)
        b_rank = find_rank(mid, b_results)

        side = check_a_health_broad(query, mid, baseline_rank, a_rank)
        if side:
            alerts.append(side)
        main = check_ab_broad(query, mid, baseline_rank, a_rank, b_rank)
        if main:
            alerts.append(main)
    return alerts


# ── 並行調度 ─────────────────────────────────────────────────────────────────

def _run_precise(precise_df, va, vb, cookie, cache=None) -> list[Alert]:
    alerts = []
    rows = list(precise_df.to_dict(orient="records"))
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(_process_precise_query, r, va, vb, cookie, cache): r["query"]
            for r in rows
        }
        for f in as_completed(futures):
            try:
                alerts.extend(f.result())
            except Exception as e:
                logger.error(f"[AB] precise query={futures[f]}: {e}")
    return alerts


def _run_broad(broad_df, va, vb, cookie, cache=None) -> list[Alert]:
    alerts = []
    groups = list(broad_df.groupby("query"))
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(_process_broad_query, q, g, va, vb, cookie, cache): q
            for q, g in groups
        }
        for f in as_completed(futures):
            try:
                alerts.extend(f.result())
            except Exception as e:
                logger.error(f"[AB] broad query={futures[f]}: {e}")
    return alerts


# ── 對外入口 ─────────────────────────────────────────────────────────────────

def run_ab_check(
    version_a: int,
    version_b: int,
    cookie: str,
    skip_precise: bool = False,
    skip_broad: bool = False,
) -> dict:
    """
    執行 AB 巡檢，回傳 { summary, alerts }。
    cache 為 request-local，避免 concurrency 問題。
    """
    cache: dict[tuple[str, int], tuple[int, ...]] = {}

    precise_df = pd.read_csv(PRECISE_CSV) if not skip_precise and PRECISE_CSV.exists() else None
    broad_df = pd.read_csv(BROAD_CSV) if not skip_broad and BROAD_CSV.exists() else None

    all_alerts: list[Alert] = []

    if precise_df is not None and not skip_precise:
        logger.info(f"[AB] Running precise check: {len(precise_df)} queries, A={version_a} B={version_b}")
        all_alerts += _run_precise(precise_df, version_a, version_b, cookie, cache)

    if broad_df is not None and not skip_broad:
        n_queries = broad_df["query"].nunique()
        logger.info(f"[AB] Running broad check: {n_queries} queries, A={version_a} B={version_b}")
        all_alerts += _run_broad(broad_df, version_a, version_b, cookie, cache)

    severity_counts = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    for a in all_alerts:
        severity_counts[a.severity] = severity_counts.get(a.severity, 0) + 1

    return {
        "summary": {
            "total": len(all_alerts),
            **severity_counts,
        },
        "alerts": [asdict(a) for a in all_alerts],
    }
