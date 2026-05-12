"""
從 Joyce 的搜尋詞巡檢報告 HTML 解析兩張 baseline 表
=====================================================

來源:
  https://kkday-analysis-reports.pages.dev/reports/joyce.zhang/search_keyword_inspection_30d
  (在瀏覽器存成「網頁,完整」格式得到 .html + _files 資料夾)

使用:
  python scripts/parse_html.py path/to/report.html [output_dir]

  輸出:
    {output_dir}/search_keyword_precise.csv
    {output_dir}/search_keyword_broad.csv

  output_dir 預設 ./data/

維護:
  Joyce 出新版報告時,更新報告 HTML 檔重跑即可。
  不需要改程式(欄位是用 header 文字辨識的,不依賴順序)。

注意:
  目前 Joyce 的報告 HTML 只放 sample(精準詞前 200、泛詞前 60 query),
  全量資料需另外從 BQ 拿。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup


def clean_int(s):
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "—", "-"):
        return None
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def clean_float(s):
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    try:
        return float(s.replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def cells_of(tr):
    return [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]


def parse_table(table, columns):
    rows = table.find_all("tr")
    data = []
    for tr in rows[1:]:  # skip header
        vals = cells_of(tr)
        if len(vals) < len(columns):
            continue
        data.append(dict(zip(columns, vals[: len(columns)])))
    return data


def parse_report(html_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    with html_path.open(encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    tables = soup.find_all("table")

    # 用 header 文字辨識(不依賴順序)
    precise_table = None
    broad_table = None
    for t in tables:
        header_row = t.find("tr")
        if not header_row:
            continue
        header = " ".join(cells_of(header_row))
        if "top1_prod_mid" in header and "top2_prod_mid" in header:
            precise_table = t
        elif "profit_rank" in header:
            broad_table = t

    assert precise_table is not None, "找不到精準詞表(header 應含 top1_prod_mid / top2_prod_mid)"
    assert broad_table is not None, "找不到泛詞表(header 應含 profit_rank)"

    # 精準詞
    precise_cols = [
        "query", "is_destination", "search_pv",
        "top1_prod_nm", "top1_prod_mid", "top1_profit", "top1_ctr",
        "top2_prod_nm", "top2_prod_mid", "top2_profit", "top2_ctr",
    ]
    pdf = pd.DataFrame(parse_table(precise_table, precise_cols))

    pdf["search_pv"]      = pdf["search_pv"].apply(clean_int)
    pdf["top1_prod_mid"]  = pdf["top1_prod_mid"].apply(clean_int)
    pdf["top1_profit"]    = pdf["top1_profit"].apply(clean_int)
    pdf["top1_ctr"]       = pdf["top1_ctr"].apply(clean_float)
    pdf["top2_prod_mid"]  = pdf["top2_prod_mid"].apply(clean_int)
    pdf["top2_profit"]    = pdf["top2_profit"].apply(clean_int)
    pdf["top2_ctr"]       = pdf["top2_ctr"].apply(clean_float)
    pdf["is_destination"] = pdf["is_destination"].map({"Y": True, "N": False})

    # 泛詞
    broad_cols = ["query", "prod_nm", "prod_mid", "profit", "ctr", "profit_rank"]
    bdf = pd.DataFrame(parse_table(broad_table, broad_cols))

    bdf["prod_mid"]    = bdf["prod_mid"].apply(clean_int)
    bdf["profit"]      = bdf["profit"].apply(clean_int)
    bdf["ctr"]         = bdf["ctr"].apply(clean_float)
    bdf["profit_rank"] = bdf["profit_rank"].apply(clean_int)

    return pdf, bdf


def validate(pdf: pd.DataFrame, bdf: pd.DataFrame) -> None:
    """印出 sanity check 結果,方便人工目視檢查"""
    print("=" * 60)
    print("精準詞")
    print(f"  rows: {len(pdf)}")
    print(f"  is_destination=True:  {pdf['is_destination'].sum()}")
    print(f"  is_destination=False: {(~pdf['is_destination'].astype(bool)).sum()}")
    print(f"  has top1_prod_mid: {pdf['top1_prod_mid'].notna().sum()}")
    print(f"  has top2_prod_mid: {pdf['top2_prod_mid'].notna().sum()}")

    no_top2 = pdf[pdf["top2_prod_mid"].isna()]
    if len(no_top2) > 0:
        print(f"\n  ⚠️  {len(no_top2)} 個極致集中精準詞(詞下只有 1 個成交商品):")
        for q in no_top2["query"].tolist():
            print(f"     - {q}")

    print()
    print("=" * 60)
    print("泛詞")
    print(f"  rows: {len(bdf)}")
    print(f"  unique query: {bdf['query'].nunique()}")

    rank_check = bdf.groupby("query")["profit_rank"].apply(
        lambda x: list(sorted(x.dropna().astype(int))) == list(range(1, len(x) + 1))
    )
    n_ok = rank_check.sum()
    n_total = len(rank_check)
    print(f"  profit_rank 1..N 連續的 query: {n_ok}/{n_total}")
    if n_ok < n_total:
        bad = rank_check[~rank_check].index.tolist()
        print(f"  ⚠️  不連續的 query: {bad[:10]}{'...' if len(bad) > 10 else ''}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    html_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not html_path.exists():
        print(f"找不到 HTML: {html_path}")
        sys.exit(1)

    pdf, bdf = parse_report(html_path)

    p_out = output_dir / "search_keyword_precise.csv"
    b_out = output_dir / "search_keyword_broad.csv"
    pdf.to_csv(p_out, index=False)
    bdf.to_csv(b_out, index=False)

    validate(pdf, bdf)

    print()
    print("輸出:")
    print(f"  {p_out}")
    print(f"  {b_out}")


if __name__ == "__main__":
    main()
