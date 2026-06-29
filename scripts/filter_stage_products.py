"""
Stage product existence checker
================================

對 baseline CSV (`search_keyword_precise.csv`, `search_keyword_broad.csv`)
中的每個 prod_mid 打 stage 的商品頁,過濾掉 stage 上已經不存在的商品,
產出乾淨版 CSV 給後續巡檢使用,並記錄被濾掉的清單。

存在判斷 (走 HEAD,不跟 redirect):
  - HTTP 200 → 商品存在 (少數舊商品 stage 直接回 200,不 redirect)
  - HTTP 301/302 → 商品存在 (大多數會 redirect 到帶 slug 的 canonical URL)
  - HTTP 404 → 商品不存在
  - 其他狀態 → 視為 "unknown",預設保留並記錄 (避免暫時性網路問題誤刪)

用法:
  python scripts/filter_stage_products.py
  python scripts/filter_stage_products.py --workers 20 --limit 30
  python scripts/filter_stage_products.py --drop-unknown

輸出 (預設):
  handoff/data/filtered/search_keyword_precise.csv
  handoff/data/filtered/search_keyword_broad.csv
  handoff/data/filtered/filter_log.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRECISE = ROOT / "handoff" / "data" / "search_keyword_precise.csv"
DEFAULT_BROAD = ROOT / "handoff" / "data" / "search_keyword_broad.csv"
DEFAULT_OUTPUT = ROOT / "handoff" / "data" / "filtered"

STAGE_PRODUCT_URL = "https://www.stage.kkday.com/zh-tw/product/{mid}"

# Cookies copied from a real browser session — datadome 會擋裸請求,需要這組
# 才能穩定拿到 301/404 而不是被丟去 challenge 頁
DEFAULT_COOKIE = (
    "i18n_redirected=zh-tw; country_lang=zh-tw; lang_ui=zh-tw; currency=TWD"
)
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)

EXISTS_STATUS = {200, 301, 302}
MISSING_STATUS = {404}


@dataclass
class CheckResult:
    prod_mid: int
    status: str          # 'exists' | 'missing' | 'unknown'
    http_code: Optional[int]
    error: Optional[str] = None


def check_one(
    session: requests.Session,
    mid: int,
    timeout: float,
    retries: int,
) -> CheckResult:
    url = STAGE_PRODUCT_URL.format(mid=mid)
    last_err: Optional[str] = None
    for attempt in range(retries + 1):
        try:
            resp = session.head(url, timeout=timeout, allow_redirects=False)
            code = resp.status_code
            if code in EXISTS_STATUS:
                return CheckResult(mid, "exists", code)
            if code in MISSING_STATUS:
                return CheckResult(mid, "missing", code)
            # 其他狀態 (403 / 429 / 5xx ...) — 重試或視為 unknown
            last_err = f"unexpected HTTP {code}"
            if code >= 500 or code == 429:
                time.sleep(0.5 * (attempt + 1))
                continue
            return CheckResult(mid, "unknown", code, error=last_err)
        except requests.RequestException as e:
            last_err = str(e)
            time.sleep(0.5 * (attempt + 1))
    return CheckResult(mid, "unknown", None, error=last_err)


def collect_prod_mids(precise_df: pd.DataFrame, broad_df: pd.DataFrame) -> set[int]:
    mids: set[int] = set()
    for col in ("top1_prod_mid", "top2_prod_mid"):
        if col in precise_df.columns:
            mids.update(_clean_mids(precise_df[col]))
    if "prod_mid" in broad_df.columns:
        mids.update(_clean_mids(broad_df["prod_mid"]))
    return mids


def _clean_mids(series: pd.Series) -> list[int]:
    # baseline 內偶有 nan / float 形態 (e.g. 139872.0) — 全部轉成 int
    out: list[int] = []
    for v in series:
        if pd.isna(v):
            continue
        try:
            out.append(int(float(v)))
        except (TypeError, ValueError):
            continue
    return out


def run_checks(
    mids: list[int],
    workers: int,
    timeout: float,
    retries: int,
    cookie: str,
    user_agent: str,
    recheck_unknown: bool = True,
    recheck_delay: float = 1.5,
    recheck_retries: int = 4,
) -> dict[int, CheckResult]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": user_agent,
        "Cookie": cookie,
        "Accept-Language": "zh-TW,zh;q=0.9",
    })
    results: dict[int, CheckResult] = {}
    total = len(mids)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_one, session, m, timeout, retries): m for m in mids}
        for fut in as_completed(futures):
            mid = futures[fut]
            try:
                results[mid] = fut.result()
            except Exception as e:
                results[mid] = CheckResult(mid, "unknown", None, error=repr(e))
            done += 1
            if done % 25 == 0 or done == total:
                exists = sum(1 for r in results.values() if r.status == "exists")
                missing = sum(1 for r in results.values() if r.status == "missing")
                unknown = sum(1 for r in results.values() if r.status == "unknown")
                print(
                    f"  progress {done}/{total}  exists={exists} missing={missing} unknown={unknown}",
                    flush=True,
                )

    if recheck_unknown:
        # 第一輪用 concurrency 很容易踩到 datadome / 5xx,unknown 多半是假陽性
        # 第二輪 sequential + 較長 backoff 把它們救回來
        unknown_mids = [m for m, r in results.items() if r.status == "unknown"]
        if unknown_mids:
            print(f"recheck {len(unknown_mids)} unknown mids (sequential, slow)...", flush=True)
            for i, m in enumerate(unknown_mids, 1):
                time.sleep(recheck_delay)
                new_r = check_one(session, m, timeout, recheck_retries)
                if new_r.status != "unknown":
                    print(f"  [recheck {i}/{len(unknown_mids)}] mid={m} {results[m].status}→{new_r.status} (http={new_r.http_code})", flush=True)
                else:
                    print(f"  [recheck {i}/{len(unknown_mids)}] mid={m} still unknown (http={new_r.http_code} err={new_r.error})", flush=True)
                results[m] = new_r

    return results


def filter_precise(
    df: pd.DataFrame,
    results: dict[int, CheckResult],
    drop_unknown: bool,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    Precise rule:
      - top1 不存在 → drop 整列 (這列的主用途就是 top1)
      - top2 不存在 → 清空 top2_* 欄位
      - unknown:預設保留;drop_unknown=True 時當作不存在處理
    """
    dropped: list[dict] = []
    keep_rows: list[dict] = []
    bad = {"missing"} | ({"unknown"} if drop_unknown else set())

    for _, row in df.iterrows():
        row = row.to_dict()
        top1_mid = _coerce_int(row.get("top1_prod_mid"))
        top2_mid = _coerce_int(row.get("top2_prod_mid"))

        top1_status = results[top1_mid].status if top1_mid in results else "unknown"
        top2_status = results[top2_mid].status if top2_mid in results else None

        if top1_status in bad:
            dropped.append({
                "source": "precise",
                "query": row.get("query"),
                "prod_mid": top1_mid,
                "slot": "top1",
                "status": top1_status,
                "http_code": results[top1_mid].http_code if top1_mid in results else None,
                "error": results[top1_mid].error if top1_mid in results else None,
            })
            continue

        if top2_status in bad and top2_mid is not None:
            dropped.append({
                "source": "precise",
                "query": row.get("query"),
                "prod_mid": top2_mid,
                "slot": "top2",
                "status": top2_status,
                "http_code": results[top2_mid].http_code,
                "error": results[top2_mid].error,
            })
            for col in ("top2_prod_nm", "top2_prod_mid", "top2_profit", "top2_ctr"):
                if col in row:
                    row[col] = None

        keep_rows.append(row)

    return pd.DataFrame(keep_rows, columns=list(df.columns)), dropped


def filter_broad(
    df: pd.DataFrame,
    results: dict[int, CheckResult],
    drop_unknown: bool,
) -> tuple[pd.DataFrame, list[dict]]:
    dropped: list[dict] = []
    keep_rows: list[dict] = []
    bad = {"missing"} | ({"unknown"} if drop_unknown else set())

    for _, row in df.iterrows():
        row = row.to_dict()
        mid = _coerce_int(row.get("prod_mid"))
        status = results[mid].status if mid in results else "unknown"
        if status in bad:
            dropped.append({
                "source": "broad",
                "query": row.get("query"),
                "prod_mid": mid,
                "slot": f"profit_rank={row.get('profit_rank')}",
                "status": status,
                "http_code": results[mid].http_code if mid in results else None,
                "error": results[mid].error if mid in results else None,
            })
            continue
        keep_rows.append(row)
    return pd.DataFrame(keep_rows, columns=list(df.columns)), dropped


def _coerce_int(v) -> Optional[int]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--precise", type=Path, default=DEFAULT_PRECISE)
    p.add_argument("--broad", type=Path, default=DEFAULT_BROAD)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--retries", type=int, default=2, help="重試次數 (不含首次)")
    p.add_argument("--limit", type=int, default=0, help=">0 時只檢查前 N 個 prod_mid (smoke test 用)")
    p.add_argument("--drop-unknown", action="store_true", help="把 unknown 也當不存在處理")
    p.add_argument("--no-recheck", action="store_true", help="跳過第二輪 unknown 慢速複檢")
    p.add_argument("--recheck-delay", type=float, default=1.5, help="複檢每筆間隔秒數 (預設 1.5)")
    p.add_argument("--recheck-retries", type=int, default=4, help="複檢時的重試次數 (預設 4)")
    p.add_argument("--cookie", default=DEFAULT_COOKIE)
    p.add_argument("--user-agent", default=DEFAULT_UA)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.precise.exists():
        print(f"[ERROR] precise CSV not found: {args.precise}", file=sys.stderr)
        return 1
    if not args.broad.exists():
        print(f"[ERROR] broad CSV not found: {args.broad}", file=sys.stderr)
        return 1

    print(f"load precise: {args.precise}")
    precise_df = pd.read_csv(args.precise)
    print(f"  {len(precise_df)} rows")
    print(f"load broad:   {args.broad}")
    broad_df = pd.read_csv(args.broad)
    print(f"  {len(broad_df)} rows")

    mids = sorted(collect_prod_mids(precise_df, broad_df))
    print(f"unique prod_mids to check: {len(mids)}")
    if args.limit > 0:
        mids = mids[: args.limit]
        print(f"[--limit] truncated to {len(mids)}")

    start = time.time()
    results = run_checks(
        mids,
        workers=args.workers,
        timeout=args.timeout,
        retries=args.retries,
        cookie=args.cookie,
        user_agent=args.user_agent,
        recheck_unknown=not args.no_recheck,
        recheck_delay=args.recheck_delay,
        recheck_retries=args.recheck_retries,
    )
    elapsed = time.time() - start

    exists = sum(1 for r in results.values() if r.status == "exists")
    missing = sum(1 for r in results.values() if r.status == "missing")
    unknown = sum(1 for r in results.values() if r.status == "unknown")
    print(f"checks done in {elapsed:.1f}s — exists={exists} missing={missing} unknown={unknown}")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    precise_out, precise_dropped = filter_precise(precise_df, results, args.drop_unknown)
    broad_out, broad_dropped = filter_broad(broad_df, results, args.drop_unknown)

    precise_path = args.output_dir / "search_keyword_precise.csv"
    broad_path = args.output_dir / "search_keyword_broad.csv"
    log_path = args.output_dir / "filter_log.csv"

    precise_out.to_csv(precise_path, index=False)
    broad_out.to_csv(broad_path, index=False)

    all_dropped = precise_dropped + broad_dropped
    if all_dropped:
        with log_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["source", "query", "prod_mid", "slot", "status", "http_code", "error"],
            )
            writer.writeheader()
            writer.writerows(all_dropped)
    else:
        log_path.write_text("source,query,prod_mid,slot,status,http_code,error\n", encoding="utf-8")

    print()
    print("written:")
    print(f"  {precise_path}  ({len(precise_out)} rows, was {len(precise_df)})")
    print(f"  {broad_path}    ({len(broad_out)} rows, was {len(broad_df)})")
    print(f"  {log_path}      ({len(all_dropped)} filtered entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
