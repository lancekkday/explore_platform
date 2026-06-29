"""
從 BigQuery 直接抽精準詞 / 泛詞 baseline
==============================================

SQL 來源:Joyce 2026-05-08 v4
  "搜尋場景關鍵字巡檢:精準詞 / 泛詞上線表 schema 預覽(台灣市場)"
  → scripts/sql/baseline_precise.sql
  → scripts/sql/baseline_broad.sql

使用:
  # 1. 安裝 (一次性)
  pip install google-cloud-bigquery pandas db-dtypes

  # 2. 設認證 — 兩種任選
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
  # 或 user ADC: gcloud auth application-default login

  # 3. 跑
  python scripts/fetch_baseline_bq.py                 # 寫到 handoff/data/
  python scripts/fetch_baseline_bq.py --output-dir /tmp/baseline
  python scripts/fetch_baseline_bq.py --only precise  # 只跑精準詞
  python scripts/fetch_baseline_bq.py --dry-run       # 印 SQL 不執行
  python scripts/fetch_baseline_bq.py --version       # 寫進 BaselineVersionManager(自動建版本+啟用)

設計:
  - SQL 寫在外部檔(sql/baseline_*.sql),不在 Python 字串裡 —— Joyce 改規則時改 SQL 即可
  - 輸出 CSV header 與 handoff/data/search_keyword_*.csv 完全對齊 → baseline_service.py 不用改
  - profit 取整數(對齊現有 CSV;Joyce SQL 已用 ROUND(SUM(profit), 0))
  - is_destination 寫成 True/False 字串(對齊現有 CSV)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = Path(__file__).resolve().parent / "sql"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "handoff" / "data"

# Load root .env (single source of truth, per CLAUDE.md)
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass  # python-dotenv 沒裝就算了,改用 shell export 也行

PRECISE_COLS = [
    "query", "is_destination", "search_pv",
    "top1_prod_nm", "top1_prod_mid", "top1_profit", "top1_ctr",
    "top2_prod_nm", "top2_prod_mid", "top2_profit", "top2_ctr",
]
BROAD_COLS = ["query", "prod_nm", "prod_mid", "profit", "ctr", "profit_rank"]


def load_sql(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        sys.exit(f"找不到 SQL: {path}")
    return path.read_text(encoding="utf-8")


def run_query(client, sql: str):
    import pandas as pd  # noqa: F401  (used via to_dataframe)
    job = client.query(sql)
    return job.result().to_dataframe(create_bqstorage_client=False)


def normalize_precise(df):
    df = df.rename(columns={
        "top1_prod_nm": "top1_prod_nm", "top2_prod_nm": "top2_prod_nm",
    })
    # Cast types to match existing CSV
    int_cols = ["search_pv", "top1_prod_mid", "top1_profit", "top2_prod_mid", "top2_profit"]
    for c in int_cols:
        if c in df.columns:
            df[c] = df[c].astype("Int64")
    for c in ["top1_ctr", "top2_ctr"]:
        if c in df.columns:
            df[c] = df[c].astype("Float64")
    if "is_destination" in df.columns:
        df["is_destination"] = df["is_destination"].astype(bool)
    return df[PRECISE_COLS]


def normalize_broad(df):
    int_cols = ["prod_mid", "profit", "profit_rank"]
    for c in int_cols:
        if c in df.columns:
            df[c] = df[c].astype("Int64")
    if "ctr" in df.columns:
        df["ctr"] = df["ctr"].astype("Float64")
    return df[BROAD_COLS]


def validate(pdf, bdf):
    print("=" * 60)
    print("精準詞")
    print(f"  rows: {len(pdf)}")
    print(f"  is_destination=True:  {int(pdf['is_destination'].sum())}")
    print(f"  is_destination=False: {int((~pdf['is_destination']).sum())}")
    print(f"  has top1_prod_mid: {pdf['top1_prod_mid'].notna().sum()}")
    print(f"  has top2_prod_mid: {pdf['top2_prod_mid'].notna().sum()}")

    no_top2 = pdf[pdf["top2_prod_mid"].isna()]
    if len(no_top2) > 0:
        print(f"\n  ⚠️  {len(no_top2)} 個極致集中精準詞(詞下只有 1 個成交商品):")
        for q in no_top2["query"].tolist()[:20]:
            print(f"     - {q}")

    print()
    print("=" * 60)
    print("泛詞")
    print(f"  rows: {len(bdf)}")
    print(f"  unique query: {bdf['query'].nunique()}")

    rank_check = bdf.groupby("query")["profit_rank"].apply(
        lambda x: list(sorted(x.dropna().astype(int))) == list(range(1, len(x) + 1))
    )
    n_ok = int(rank_check.sum())
    n_total = len(rank_check)
    print(f"  profit_rank 1..N 連續的 query: {n_ok}/{n_total}")
    if n_ok < n_total:
        bad = rank_check[~rank_check].index.tolist()
        print(f"  ⚠️  不連續的 query: {bad[:10]}{'...' if len(bad) > 10 else ''}")


def write_via_version_manager(pdf, bdf):
    """Use BaselineVersionManager — auto-version + activate (rolls history.db etc.)."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from baseline_version_manager import BaselineVersionManager  # type: ignore

    mgr = BaselineVersionManager()
    import io
    p_buf = io.StringIO(); pdf.to_csv(p_buf, index=False)
    b_buf = io.StringIO(); bdf.to_csv(b_buf, index=False)
    meta = mgr.create_version(p_buf.getvalue(), b_buf.getvalue(), source_filename="bq_fetch")
    print(f"\n已建立並啟用版本: {meta['timestamp']}")
    print(f"  precise_keywords: {meta['precise_keywords']}")
    print(f"  broad_keywords:   {meta['broad_keywords']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                    help=f"輸出資料夾(預設 {DEFAULT_OUTPUT_DIR.relative_to(REPO_ROOT)})")
    ap.add_argument("--only", choices=["precise", "broad"], help="只跑其中一張表")
    ap.add_argument("--project", default=os.environ.get("BQ_PROJECT_ID"),
                    help="BQ 計費 project(預設讀 env BQ_PROJECT_ID,否則用 SA 預設)")
    ap.add_argument("--dry-run", action="store_true", help="只印 SQL 不執行")
    ap.add_argument("--version", action="store_true",
                    help="寫進 BaselineVersionManager(自動建版本+啟用),不寫平面 CSV")
    args = ap.parse_args()

    precise_sql = load_sql("baseline_precise.sql") if args.only != "broad" else None
    broad_sql = load_sql("baseline_broad.sql") if args.only != "precise" else None

    if args.dry_run:
        for name, sql in [("precise", precise_sql), ("broad", broad_sql)]:
            if sql is None:
                continue
            print(f"===== {name} SQL =====")
            print(sql)
            print()
        return

    try:
        from google.cloud import bigquery
    except ImportError:
        sys.exit("缺套件:pip install google-cloud-bigquery pandas db-dtypes")

    client = bigquery.Client(project=args.project) if args.project else bigquery.Client()
    print(f"BQ project: {client.project}")

    pdf = bdf = None
    if precise_sql:
        print("→ 跑精準詞 SQL ...")
        pdf = normalize_precise(run_query(client, precise_sql))
    if broad_sql:
        print("→ 跑泛詞 SQL ...")
        bdf = normalize_broad(run_query(client, broad_sql))

    if pdf is not None and bdf is not None:
        validate(pdf, bdf)

    if args.version:
        if pdf is None or bdf is None:
            sys.exit("--version 需同時抽兩張表(不要搭配 --only)")
        write_via_version_manager(pdf, bdf)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if pdf is not None:
        p_out = args.output_dir / "search_keyword_precise.csv"
        pdf.to_csv(p_out, index=False)
        print(f"\n寫出: {p_out}  ({len(pdf)} rows)")
    if bdf is not None:
        b_out = args.output_dir / "search_keyword_broad.csv"
        bdf.to_csv(b_out, index=False)
        print(f"寫出: {b_out}  ({len(bdf)} rows)")


if __name__ == "__main__":
    main()
