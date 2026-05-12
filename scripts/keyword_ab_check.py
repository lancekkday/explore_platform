"""
搜尋詞 AB 巡檢主腳本
====================

使用前 Claude Code 必須先做:
  1. 在這個 repo 找出既有的 search API client
  2. 把 import 跟 call_search_api() 接好
  3. 確認 baseline CSV 路徑

不要重新實作 API client,直接 import。

使用:
  python scripts/keyword_ab_check.py --version-a v1 --version-b v2

  輸出: reports/ab_alerts_{a}_vs_{b}_{timestamp}.csv
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

# ============================================================
# TODO[CC]: 換成 repo 裡既有的 search API client
# ============================================================
# from src.search_client import call_search_api as _real_api
#
# def call_search_api(query: str, version: str) -> list[int]:
#     """回傳 prod_mid list,最多 300 個"""
#     resp = _real_api(query=query, version=version, size=300)
#     # 視 API 回傳格式調整:
#     # return [r['mid'] for r in resp['results']]
#     # 或:
#     # return resp.product_ids
#     ...
#
# 接好後刪除這個 stub:
def call_search_api(query: str, version: str) -> list[int]:
    raise NotImplementedError(
        "請接入 repo 裡既有的 search API client(看 CONTEXT.md 的「API 對接」章節)"
    )

# ============================================================
# 巡檢規則 — 可調閾值
# ============================================================
PRECISE_DROP_THRESHOLD = 5     # 精準詞 Top1/2 在 B 版相對 A 版掉超過 5 名 → 告警
BROAD_DELTA_THRESHOLD = 5      # 泛詞商品在 A vs B 之間位置差超過 5 名(雙向)→ 告警

SIDE_PRECISE_TOP1_MAX_RANK = 10   # A 版本身 baseline Top1 在第 10 位之後 → A 不穩
SIDE_PRECISE_TOP2_MAX_RANK = 15
SIDE_BROAD_RANK_DELTA = 20        # A 版本身偏離 baseline_rank 超過 20 名 → A 不穩

API_PARALLEL_WORKERS = 10
API_MAX_RESULTS = 300

# ============================================================
# 預設路徑
# ============================================================
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
PRECISE_CSV = DATA_DIR / "search_keyword_precise.csv"
BROAD_CSV = DATA_DIR / "search_keyword_broad.csv"


@dataclass
class Alert:
    alert_type: str          # 'main' | 'side'
    keyword_type: str        # 'precise' | 'broad'
    query: str
    prod_mid: int
    baseline_rank: int
    a_rank: Optional[int]
    b_rank: Optional[int]
    severity: str            # 'P0' | 'P1' | 'P2' | 'INFO'
    reason: str


# ============================================================
# API cache:同 query 同 version 不重複呼叫
# ============================================================
@lru_cache(maxsize=10000)
def fetch_results(query: str, version: str) -> tuple[int, ...]:
    """回傳 tuple 是為了能被 lru_cache,使用時轉 list"""
    try:
        results = call_search_api(query, version)
        return tuple(results[:API_MAX_RESULTS])
    except Exception as e:
        print(f"  [API ERROR] query={query!r} version={version!r}: {e}")
        return tuple()


def find_rank(mid: int, results: tuple[int, ...]) -> Optional[int]:
    try:
        return results.index(mid) + 1
    except ValueError:
        return None


# ============================================================
# 精準詞檢查
# ============================================================
def check_a_health_precise(query, mid, baseline_rank, a_rank) -> Optional[Alert]:
    threshold = SIDE_PRECISE_TOP1_MAX_RANK if baseline_rank == 1 else SIDE_PRECISE_TOP2_MAX_RANK
    if a_rank is None:
        return Alert(
            alert_type="side", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=None, b_rank=None, severity="INFO",
            reason=f"baseline Top{baseline_rank} 商品在 A 版找不到,可能 baseline 過時或商品下架",
        )
    if a_rank > threshold:
        return Alert(
            alert_type="side", keyword_type="precise", query=query, prod_mid=mid,
            baseline_rank=baseline_rank, a_rank=a_rank, b_rank=None, severity="INFO",
            reason=f"baseline Top{baseline_rank} 在 A 版排到第 {a_rank} 位 (>閾值 {threshold}),A 版可能不穩",
        )
    return None


def check_ab_precise(query, mid, baseline_rank, a_rank, b_rank) -> Optional[Alert]:
    if a_rank is None:
        return None  # A 也沒有 → baseline 過時,不算 B 的鍋
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


def process_precise_query(row, version_a, version_b) -> list[Alert]:
    query = row["query"]
    a_results = fetch_results(query, version_a)
    b_results = fetch_results(query, version_b)

    alerts = []
    for rank_n, mid_col in [(1, "top1_prod_mid"), (2, "top2_prod_mid")]:
        mid = row[mid_col]
        if pd.isna(mid):
            continue
        mid = int(mid)

        a_rank = find_rank(mid, a_results)
        b_rank = find_rank(mid, b_results)

        if (side := check_a_health_precise(query, mid, rank_n, a_rank)):
            alerts.append(side)

        if (main := check_ab_precise(query, mid, rank_n, a_rank, b_rank)):
            alerts.append(main)

    return alerts


# ============================================================
# 泛詞檢查
# ============================================================
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


def process_broad_query(query, group, version_a, version_b) -> list[Alert]:
    a_results = fetch_results(query, version_a)
    b_results = fetch_results(query, version_b)

    alerts = []
    for _, row in group.iterrows():
        mid = int(row["prod_mid"])
        baseline_rank = int(row["profit_rank"])

        a_rank = find_rank(mid, a_results)
        b_rank = find_rank(mid, b_results)

        if (side := check_a_health_broad(query, mid, baseline_rank, a_rank)):
            alerts.append(side)

        if (main := check_ab_broad(query, mid, baseline_rank, a_rank, b_rank)):
            alerts.append(main)

    return alerts


# ============================================================
# 並行調度
# ============================================================
def run_precise_check(precise_df, version_a, version_b) -> list[Alert]:
    alerts = []
    rows = list(precise_df.to_dict(orient="records"))
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(process_precise_query, r, version_a, version_b): r["query"]
            for r in rows
        }
        for i, f in enumerate(as_completed(futures), 1):
            try:
                alerts.extend(f.result())
            except Exception as e:
                print(f"  [ERROR] precise query={futures[f]}: {e}")
            if i % 50 == 0:
                print(f"  精準詞進度: {i}/{len(rows)}")
    return alerts


def run_broad_check(broad_df, version_a, version_b) -> list[Alert]:
    alerts = []
    groups = list(broad_df.groupby("query"))
    with ThreadPoolExecutor(max_workers=API_PARALLEL_WORKERS) as ex:
        futures = {
            ex.submit(process_broad_query, q, g, version_a, version_b): q
            for q, g in groups
        }
        for i, f in enumerate(as_completed(futures), 1):
            try:
                alerts.extend(f.result())
            except Exception as e:
                print(f"  [ERROR] broad query={futures[f]}: {e}")
            if i % 100 == 0:
                print(f"  泛詞進度: {i}/{len(groups)}")
    return alerts


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="搜尋詞 AB 巡檢")
    parser.add_argument("--version-a", required=True, help="A 版本識別字串(由 PM 指定)")
    parser.add_argument("--version-b", required=True, help="B 版本識別字串(由 PM 指定)")
    parser.add_argument("--precise-csv", default=str(PRECISE_CSV))
    parser.add_argument("--broad-csv", default=str(BROAD_CSV))
    parser.add_argument("--output-dir", default=str(REPORTS_DIR))
    parser.add_argument("--skip-precise", action="store_true")
    parser.add_argument("--skip-broad", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    precise = pd.read_csv(args.precise_csv)
    broad = pd.read_csv(args.broad_csv)

    print(f"巡檢開始")
    print(f"  A 版: {args.version_a}")
    print(f"  B 版: {args.version_b}")
    print(f"  精準詞: {len(precise)} 個 query")
    print(f"  泛詞: {broad['query'].nunique()} 個 query / {len(broad)} row")
    print()

    t0 = time.time()
    all_alerts: list[Alert] = []

    if not args.skip_precise:
        all_alerts += run_precise_check(precise, args.version_a, args.version_b)
    if not args.skip_broad:
        all_alerts += run_broad_check(broad, args.version_a, args.version_b)

    df = pd.DataFrame([asdict(a) for a in all_alerts])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"ab_alerts_{args.version_a}_vs_{args.version_b}_{ts}.csv"
    df.to_csv(out_path, index=False)

    print(f"\n=== 巡檢完成 ({time.time() - t0:.1f}s) ===")
    print(f"輸出: {out_path}\n")
    print(f"總告警: {len(all_alerts)}")
    if not df.empty:
        print("\n按類型 + 嚴重度分布:")
        print(df.groupby(["alert_type", "severity"]).size().to_string())

        critical = df[(df["alert_type"] == "main") & (df["severity"].isin(["P0", "P1"]))]
        if not critical.empty:
            print(f"\n=== 主告警 P0/P1 ({len(critical)} 筆) ===")
            print(critical[
                ["keyword_type", "query", "prod_mid", "a_rank", "b_rank", "severity", "reason"]
            ].to_string(index=False))


if __name__ == "__main__":
    main()
