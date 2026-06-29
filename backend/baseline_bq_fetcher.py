"""
Baseline BQ Fetcher
===================

Shared core for pulling baseline CSVs from BigQuery views.
Called by:
  - scripts/fetch_baseline_bq.py (CLI)
  - backend/baseline_scheduler.py (APScheduler cron)
  - POST /api/baseline/refresh-from-bq (manual UI trigger)

Guardrail:
  if new precise/broad row count < previous version's count × 50%, or row == 0,
  the new version is still activated (per user decision) but flagged as
  `warning` so the UI can surface a banner. To hold instead, change
  ROW_RATIO_WARN to ROW_RATIO_REJECT semantics in apply_and_activate().
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from loguru import logger

from baseline_version_manager import baseline_version_manager, HANDOFF_DATA, PRECISE_NAME, BROAD_NAME

# SQL lives alongside the CLI (single source of truth).
# Resolve across layouts:
#   - Local dev: backend/baseline_bq_fetcher.py → repo_root/scripts/sql
#   - Docker: backend/* is COPYed flat into /app/, scripts/sql/ must be mounted
#     to /app/scripts/sql via docker-compose
_app_dir = Path(__file__).resolve().parent
SQL_DIR = next(
    (p for p in [
        _app_dir.parent / "scripts" / "sql",  # local dev
        _app_dir / "scripts" / "sql",          # Docker (mounted)
    ] if p.is_dir()),
    _app_dir.parent / "scripts" / "sql",       # fallback (for clearer error message)
)

PRECISE_COLS = [
    "query", "is_destination", "search_pv",
    "top1_prod_nm", "top1_prod_mid", "top1_profit", "top1_ctr",
    "top2_prod_nm", "top2_prod_mid", "top2_profit", "top2_ctr",
]
BROAD_COLS = ["query", "prod_nm", "prod_mid", "profit", "ctr", "profit_rank"]

# Guardrail threshold — warn if new rows < previous rows × this ratio
ROW_RATIO_WARN = 0.50


@dataclass
class FetchResult:
    success: bool
    precise_csv: Optional[str] = None
    broad_csv: Optional[str] = None
    precise_rows: int = 0
    broad_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _load_sql(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL not found: {path}")
    return path.read_text(encoding="utf-8")


def _normalize_precise(df):
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


def _normalize_broad(df):
    for c in ["prod_mid", "profit", "profit_rank"]:
        if c in df.columns:
            df[c] = df[c].astype("Int64")
    if "ctr" in df.columns:
        df["ctr"] = df["ctr"].astype("Float64")
    return df[BROAD_COLS]


def _df_to_csv_str(df) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def fetch_from_bq(project: Optional[str] = None) -> FetchResult:
    """
    Query BQ views and return CSV strings. Does NOT touch disk or activate
    a new version — that's the caller's job (see apply_and_activate).
    """
    project = project or os.environ.get("BQ_PROJECT_ID")
    try:
        from google.cloud import bigquery
    except ImportError as e:
        return FetchResult(success=False, error=f"google-cloud-bigquery not installed: {e}")

    try:
        precise_sql = _load_sql("baseline_precise.sql")
        broad_sql = _load_sql("baseline_broad.sql")
    except FileNotFoundError as e:
        return FetchResult(success=False, error=str(e))

    try:
        client = bigquery.Client(project=project) if project else bigquery.Client()
        logger.info(f"[BQFetcher] querying via project={client.project}")

        pdf = _normalize_precise(
            client.query(precise_sql).result().to_dataframe(create_bqstorage_client=False)
        )
        bdf = _normalize_broad(
            client.query(broad_sql).result().to_dataframe(create_bqstorage_client=False)
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        logger.error(f"[BQFetcher] query failed — {msg}")
        return FetchResult(success=False, error=msg)

    return FetchResult(
        success=True,
        precise_csv=_df_to_csv_str(pdf),
        broad_csv=_df_to_csv_str(bdf),
        precise_rows=len(pdf),
        broad_rows=len(bdf),
    )


def _row_count(csv_str: str) -> int:
    if not csv_str:
        return 0
    # subtract 1 for header
    return max(0, sum(1 for _ in csv_str.splitlines()) - 1)


def _check_guardrail(precise_rows: int, broad_rows: int) -> list[str]:
    """Compare against current active version; return warning messages."""
    warnings: list[str] = []
    if precise_rows == 0:
        warnings.append("precise: 0 rows")
    if broad_rows == 0:
        warnings.append("broad: 0 rows")

    # Find current version row counts from versions/<active>/meta.json
    active = baseline_version_manager.get_active_version()
    if not active:
        return warnings

    prev_p = int(active.get("precise_keywords") or 0)
    prev_b = int(active.get("broad_keywords") or 0)

    if prev_p and precise_rows < prev_p * ROW_RATIO_WARN:
        warnings.append(
            f"precise: {precise_rows} rows < previous {prev_p} × {int(ROW_RATIO_WARN*100)}%"
        )
    if prev_b and broad_rows < prev_b * ROW_RATIO_WARN:
        warnings.append(
            f"broad: {broad_rows} rows < previous {prev_b} × {int(ROW_RATIO_WARN*100)}%"
        )
    return warnings


def apply_and_activate(result: FetchResult, source: str = "bq_auto") -> FetchResult:
    """
    Write a fetched FetchResult through BaselineVersionManager.
    Mutates result.warnings with guardrail outcomes.
    Always activates the new version (per current product decision).
    """
    if not result.success:
        return result
    result.warnings = _check_guardrail(result.precise_rows, result.broad_rows)
    meta = baseline_version_manager.create_version(
        result.precise_csv, result.broad_csv, source_filename=source
    )
    logger.info(
        f"[BQFetcher] activated version {meta['timestamp']} "
        f"precise={meta['precise_keywords']} broad={meta['broad_keywords']} "
        f"warnings={result.warnings or 'none'}"
    )
    return result


def write_to_handoff_dir(result: FetchResult) -> tuple[Path, Path]:
    """Plain CSV write for CLI use (no versioning)."""
    if not result.success:
        raise RuntimeError(f"fetch failed: {result.error}")
    HANDOFF_DATA.mkdir(parents=True, exist_ok=True)
    p_out = HANDOFF_DATA / PRECISE_NAME
    b_out = HANDOFF_DATA / BROAD_NAME
    p_out.write_text(result.precise_csv, encoding="utf-8")
    b_out.write_text(result.broad_csv, encoding="utf-8")
    return p_out, b_out
