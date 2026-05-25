"""
搜尋詞 AB 巡檢核心模組
======================

從 handoff/scripts/keyword_ab_check.py 搬入並接上 fetch_kkday_products_v3。
提供 run_ab_check() 供 main.py endpoint 呼叫。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Optional

from loguru import logger

from baseline_service import baseline_service
from kkday_api import (
    fetch_kkday_products_v3,
    DEFAULT_LANG,
    DEFAULT_LOCALE,
    DEFAULT_CHANNEL,
)
from stage_product_check import stage_checker

# ── 閾值 ──────────────────────────────────────────────────────────────────────
PRECISE_DROP_THRESHOLD = 5
BROAD_DELTA_THRESHOLD = 5

SIDE_PRECISE_TOP1_MAX_RANK = 10
SIDE_PRECISE_TOP2_MAX_RANK = 15
SIDE_BROAD_RANK_DELTA = 20

API_PARALLEL_WORKERS = 10
API_MAX_RESULTS = 300


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
    # 當 a_rank/b_rank 為 None 時去 stage 查得的結果
    # 'removed' = 商品下架; 'exists' = 商品存在但排名 >300; 'check_failed' = stage 查詢失敗
    stage_status: Optional[str] = None


def _stage_label_zh(stage_status: Optional[str]) -> str:
    """產出 alert reason 用的中文 label"""
    return {
        "removed": "商品已下架",
        "exists": "排名 >300 名",
        "check_failed": "未確認 (stage 查詢失敗)",
    }.get(stage_status, "未出現")


# ── API 呼叫 ─────────────────────────────────────────────────────────────────


def _fetch_results(
    query: str, version: int, cookie: str, cache: dict = None,
    lang: str = DEFAULT_LANG, locale: str = DEFAULT_LOCALE, channel: str = DEFAULT_CHANNEL,
) -> tuple[int, ...]:
    """呼叫 v3 search API，回傳 prod_mid tuple（有 cache）。
    cache key 包含 (query, version, lang, locale, channel) 以免不同語系/locale 共用結果。"""
    key = (query, version, lang, locale, channel)
    if cache is not None and key in cache:
        return cache[key]
    try:
        prods, _, _ = fetch_kkday_products_v3(
            keyword=query, env="stage", cookie=cookie,
            row_count=API_MAX_RESULTS, test_exp=version,
            lang=lang, locale=locale, channel=channel,
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
        stage = stage_checker.check(mid)
        return Alert(
            alert_type="side", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=None, b_rank=None, severity="INFO",
            reason=f"baseline Top{baseline_rank} 商品在 A 版{_stage_label_zh(stage)}",
            stage_status=stage,
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
        stage = stage_checker.check(mid)
        # 保守:確認商品還存在 (exists) 才降一階為「排名偏離」;
        # removed 或 check_failed 都不降 (前者確認下架,後者不確定也當下架處理,
        # 避免 transient network blip 把真正的 regression 默默變輕)
        if stage == "exists":
            sev = "P1" if baseline_rank == 1 else "P2"
        else:  # removed 或 check_failed
            sev = "P0" if baseline_rank == 1 else "P1"
        return Alert(
            alert_type="main", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None,
            severity=sev,
            reason=f"A 版第 {a_rank} 位,B 版{_stage_label_zh(stage)}",
            stage_status=stage,
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


def process_one_precise_query(
    row, version_a, version_b, cookie, cache=None,
    lang: str = DEFAULT_LANG, locale: str = DEFAULT_LOCALE, channel: str = DEFAULT_CHANNEL,
) -> list[Alert]:
    query = row["query"]
    a_results = _fetch_results(query, version_a, cookie, cache, lang, locale, channel)
    b_results = _fetch_results(query, version_b, cookie, cache, lang, locale, channel)

    alerts = []
    for rank_n, mid_col in [(1, "top1_prod_mid"), (2, "top2_prod_mid")]:
        mid = row.get(mid_col)
        if mid is None:
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
            stage = stage_checker.check(mid)
            return Alert(
                alert_type="side", keyword_type="broad", query=query, prod_mid=mid,
                baseline_rank=baseline_rank, a_rank=None, b_rank=None, severity="INFO",
                reason=f"baseline profit_rank={baseline_rank} 商品在 A 版{_stage_label_zh(stage)}",
                stage_status=stage,
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
        stage = stage_checker.check(mid)
        # 保守:exists 才降一階 (確認排名偏離 ≠ 下架);
        # removed 或 check_failed 都不降 — check_failed 假設最壞情況,
        # 避免網路 transient blip 默默把 P1 降到 P2
        if stage == "exists":
            sev = "P2"
        else:  # removed 或 check_failed
            sev = "P1" if baseline_rank <= 3 else "P2"
        return Alert(
            alert_type="main", keyword_type="broad", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None,
            severity=sev,
            reason=f"A 版第 {a_rank} 位,B 版{_stage_label_zh(stage)}",
            stage_status=stage,
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


def process_one_broad_query(
    query, group, version_a, version_b, cookie, cache=None,
    lang: str = DEFAULT_LANG, locale: str = DEFAULT_LOCALE, channel: str = DEFAULT_CHANNEL,
) -> list[Alert]:
    """group: list of broad baseline row dicts (prod_mid, profit_rank, ...) for this query."""
    a_results = _fetch_results(query, version_a, cookie, cache, lang, locale, channel)
    b_results = _fetch_results(query, version_b, cookie, cache, lang, locale, channel)

    alerts = []
    for row in group:
        mid = row.get("prod_mid")
        baseline_rank = row.get("profit_rank")
        if mid is None or baseline_rank is None:
            continue
        mid = int(mid)
        baseline_rank = int(baseline_rank)
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

def _run_precise(
    precise_rows, va, vb, cookie, cache=None,
    lang: str = DEFAULT_LANG, locale: str = DEFAULT_LOCALE, channel: str = DEFAULT_CHANNEL,
) -> list[Alert]:
    """precise_rows: iterable of baseline_service._precise.values()"""
    alerts = []
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(process_one_precise_query, r, va, vb, cookie, cache, lang, locale, channel): r["query"]
            for r in precise_rows
        }
        for f in as_completed(futures):
            try:
                alerts.extend(f.result())
            except Exception as e:
                logger.error(f"[AB] precise query={futures[f]}: {e}")
    return alerts


def _run_broad(
    broad_groups, va, vb, cookie, cache=None,
    lang: str = DEFAULT_LANG, locale: str = DEFAULT_LOCALE, channel: str = DEFAULT_CHANNEL,
) -> list[Alert]:
    """broad_groups: iterable of (query, [row dict, ...])"""
    alerts = []
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(process_one_broad_query, q, g, va, vb, cookie, cache, lang, locale, channel): q
            for q, g in broad_groups
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
    lang: str = DEFAULT_LANG,
    locale: str = DEFAULT_LOCALE,
    channel: str = DEFAULT_CHANNEL,
) -> dict:
    """
    執行 AB 巡檢，回傳 { summary, alerts }。
    cache 為 request-local，避免 concurrency 問題。
    """
    # cache key shape: (query, version, lang, locale, channel) — 5-tuple after PR #28
    cache: dict[tuple[str, int, str, str, str], tuple[int, ...]] = {}
    all_alerts: list[Alert] = []

    # Use baseline_service singleton (already loaded in memory) instead of re-reading CSVs
    if not skip_precise:
        precise_rows = list(baseline_service._precise.values())
        if precise_rows:
            logger.info(
                f"[AB] Running precise check: {len(precise_rows)} queries, "
                f"A={version_a} B={version_b} lang={lang} locale={locale} channel={channel}"
            )
            all_alerts += _run_precise(precise_rows, version_a, version_b, cookie, cache, lang, locale, channel)

    if not skip_broad:
        broad_groups = list(baseline_service._broad.items())
        if broad_groups:
            logger.info(
                f"[AB] Running broad check: {len(broad_groups)} queries, "
                f"A={version_a} B={version_b} lang={lang} locale={locale} channel={channel}"
            )
            all_alerts += _run_broad(broad_groups, version_a, version_b, cookie, cache, lang, locale, channel)

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
