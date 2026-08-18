"""資料存取層 — 分區強制、成本紅線、PII 規則都做在這一層。

spec §2 紅線:
- 前端與 API 一律不得查詢原表 (dl_base 的 ar-stream 搜尋事件流;一小時 10.7 GB)
  → `assert_no_raw_table()` 對每一句組出的 SQL 做防呆,連手滑都擋
- `event_date` 分區條件必填,用範圍比較 (不用 TIMESTAMP_TRUNC)
- 列表 SELECT 走欄位白名單,cf_raw 永不出現在列表查詢
- ip 僅以 /24 形式出現 (落表已遮罩,此處再防一次)

MCP tool (後續 search-event-inspect) 與 UI 共用這一層,規則只維護一份。
"""
from __future__ import annotations

import ipaddress
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "kkday-data-dap")
BQ_DATASET = os.getenv("BQ_DATASET", "dl_qa")

EVENT_TABLE = f"`{BQ_PROJECT_ID}.{BQ_DATASET}.search_event_daily`"
PROD_TABLE = f"`{BQ_PROJECT_ID}.{BQ_DATASET}.search_event_prod_daily`"

TZ_TAIPEI = timezone(timedelta(hours=8))

# spec 2.1:出現這個 pattern 的查詢視為 bug。涵蓋 `-` 與 `_` 兩種寫法。
_RAW_TABLE_PATTERN = re.compile(r"ar[-_]stream[-_]search[-_]record", re.IGNORECASE)

# spec 5.2 列表回應欄位 (白名單;絕不含 cf_raw / uf_* / member_uuid / user_id / ip_masked)
LIST_COLUMNS = [
    "session_id", "event_date", "event_type", "cache_hit", "keyword",
    "locale", "exp_version", "source", "page_start", "page_count",
    "total_count", "prod_cnt", "join_failed", "uf_absent",
]

# spec 4.5:各特徵覆蓋率實測基準,與數值並列顯示
UF_COVERAGE_BASELINE = {
    "uf_intent": 0.635,
    "uf_profile": 0.540,
    "uf_lbs": 0.203,
    "cf": 1.0,
}

RERANK_BOUNDARY = 100   # spec 4.4:只有召回 top 100 進精排


class MissingPartitionDate(ValueError):
    """event_date 分區條件缺失 — API 層轉 400,查詢不得送出。"""


def assert_no_raw_table(sql: str) -> str:
    """成本紅線防呆:SQL 內出現原表名即丟例外 (spec 驗收 1)。"""
    if _RAW_TABLE_PATTERN.search(sql):
        raise RuntimeError(
            "cost guard: query references raw table ar-stream_search_record — "
            "only the dataform incremental job may touch it (spec 2.1)"
        )
    return sql


def local_date_to_utc_range(date_str: str) -> tuple[datetime, datetime]:
    """UTC+8 日曆日 → UTC 分區範圍,前後各留 8 小時緩衝 (spec 5.1)。

    '2026-08-13' (UTC+8) 的本地日窗 [08-13 00:00+08, 08-14 00:00+08)
    = UTC [08-12 16:00Z, 08-13 16:00Z),前後展 8h
    → [08-12 08:00Z, 08-14 00:00Z)。
    """
    if not date_str:
        raise MissingPartitionDate("date is required (partition pruning)")
    try:
        local_day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ_TAIPEI)
    except ValueError as e:
        raise MissingPartitionDate(f"invalid date {date_str!r}, expect YYYY-MM-DD") from e
    start_utc = local_day.astimezone(timezone.utc) - timedelta(hours=8)
    end_utc = (local_day + timedelta(days=1)).astimezone(timezone.utc) + timedelta(hours=8)
    return start_utc, end_utc


def mask_ip_to_24(ip: Optional[str]) -> Optional[str]:
    """落表時已遮罩;API 層再防一次,任何形式的 IP 出去都必須是 /24。"""
    if not ip:
        return ip
    if ip.endswith("/24"):
        return ip
    try:
        net = ipaddress.ip_network(f"{ip}/24", strict=False)
        return str(net)
    except ValueError:
        return None   # 看不懂的值寧可丟掉,不外洩


# ── Repository 介面 ────────────────────────────────────────────────────────────

class EventRepo(Protocol):
    def list_events(self, date: str, filters: dict[str, Any]) -> list[dict]: ...
    def get_event(self, session_id: str, date: str,
                  keyword: Optional[str] = None, exp_version: Optional[str] = None,
                  locale: Optional[str] = None) -> Optional[dict]: ...
    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]: ...
    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]: ...


# ── BigQuery 實作 ─────────────────────────────────────────────────────────────

# 列表允許的等值 filter → 欄位映射 (member_uuid 走 POST body,見 api 層)
_LIST_FILTERS = {
    "keyword": "keyword",
    "kkud": "kkud",
    "member_uuid": "member_uuid",
    "session_id": "session_id",
    "exp_version": "exp_version",
    "locale": "locale",
    "lang": "lang",
    "currency": "currency",
    "cache_hit": "cache_hit",
}


def build_list_query(date: str, filters: dict[str, Any]) -> tuple[str, dict]:
    """組列表查詢。回傳 (sql, params)。cf_raw 永不在 SELECT 裡 (spec 驗收 7)。

    logged_in 是衍生欄:身分摘要要顯示登入狀態 (spec 6.2) 但 member_uuid 是
    PII 不得進列表回應 — 只回布林。
    """
    start, end = local_date_to_utc_range(date)
    where = ["event_date >= @p_start", "event_date < @p_end"]
    params: dict[str, Any] = {"p_start": start, "p_end": end}
    for key, col in _LIST_FILTERS.items():
        if filters.get(key) is not None:
            where.append(f"{col} = @{key}")
            params[key] = filters[key]
    cols = ", ".join(LIST_COLUMNS) + ", (member_uuid IS NOT NULL) AS logged_in"
    sql = (
        f"SELECT {cols} FROM {EVENT_TABLE} "
        f"WHERE {' AND '.join(where)} ORDER BY event_date DESC LIMIT 500"
    )
    return assert_no_raw_table(sql), params


def _cluster_hint_where(params: dict[str, Any], keyword: Optional[str],
                        exp_version: Optional[str], locale: Optional[str]) -> list[str]:
    """點查用的 cluster hint 條件。

    表叢集鍵是 (keyword, exp_version, locale) — 只用 session_id 點查會繞過
    cluster pruning、掃整個 40 小時分區窗;互動工具每點一列就掃一次,成本
    紅線失守。呼叫端(前端列表 row 本來就有這三欄)應盡量帶滿。
    """
    where = []
    for key, val in (("keyword", keyword), ("exp_version", exp_version),
                     ("locale", locale)):
        if val:
            where.append(f"{key} = @hint_{key}")
            params[f"hint_{key}"] = val
    return where


def build_detail_query(session_id: str, date: str,
                       keyword: Optional[str] = None,
                       exp_version: Optional[str] = None,
                       locale: Optional[str] = None) -> tuple[str, dict]:
    start, end = local_date_to_utc_range(date)
    # 明細含 uf 摘要欄,但同樣不撈 cf_raw (走 5.4 單獨端點)
    cols = LIST_COLUMNS + [
        "normalized_keyword", "lang", "currency", "kkud", "ip_masked",
        "filter_json", "uf_intent", "uf_profile", "uf_profile_version", "uf_lbs",
        "cf_platform", "cf_hour", "cf_weekday", "cf_query_final", "cf_query_tokens",
        "ltr_features_recovered",
    ]
    params: dict[str, Any] = {"p_start": start, "p_end": end, "session_id": session_id}
    where = ["event_date >= @p_start", "event_date < @p_end", "session_id = @session_id"]
    where += _cluster_hint_where(params, keyword, exp_version, locale)
    sql = (
        f"SELECT {', '.join(cols)} FROM {EVENT_TABLE} "
        f"WHERE {' AND '.join(where)} LIMIT 1"
    )
    return assert_no_raw_table(sql), params


def build_cf_query(session_id: str, date: str,
                   keyword: Optional[str] = None,
                   exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> tuple[str, dict]:
    """5.4 專用:cf_raw 單筆載入,絕不隨列表回傳。"""
    start, end = local_date_to_utc_range(date)
    params: dict[str, Any] = {"p_start": start, "p_end": end, "session_id": session_id}
    where = ["event_date >= @p_start", "event_date < @p_end", "session_id = @session_id"]
    where += _cluster_hint_where(params, keyword, exp_version, locale)
    sql = (
        f"SELECT cf_raw FROM {EVENT_TABLE} "
        f"WHERE {' AND '.join(where)} LIMIT 1"
    )
    return assert_no_raw_table(sql), params


def build_prods_query(date: str, keyword: str, locale: Optional[str],
                      exp_version: str,
                      session_id: Optional[str] = None) -> tuple[str, dict]:
    """prod 層查詢。session_id 帶入時鎖定單一事件 — 同一天同 keyword+exp
    可能有多個 session,不鎖的話多個事件的 rank 會混在一起 (spec 3.2 FK)。"""
    start, end = local_date_to_utc_range(date)
    where = [
        "event_date >= @p_start", "event_date < @p_end",
        "keyword = @keyword", "exp_version = @exp_version",
    ]
    params: dict[str, Any] = {
        "p_start": start, "p_end": end,
        "keyword": keyword, "exp_version": exp_version,
    }
    if locale:
        where.append("locale = @locale")
        params["locale"] = locale
    if session_id:
        where.append("session_id = @session_id")
        params["session_id"] = session_id
    sql = (
        f"SELECT session_id, rank, prod_mid, prod_oid, is_ad, ltr_score, "
        f"relevance_status_code, in_rerank_scope "
        f"FROM {PROD_TABLE} WHERE {' AND '.join(where)} "
        f"ORDER BY rank ASC LIMIT 1000"
    )
    return assert_no_raw_table(sql), params


class BigQueryEventRepo:
    """真 BQ 實作。client 延遲建立,測試不需要 GCP 憑證。"""

    def __init__(self) -> None:
        self._client = None

    def _bq(self):
        if self._client is None:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=BQ_PROJECT_ID)
        return self._client

    def _run(self, sql: str, params: dict[str, Any]) -> list[dict]:
        from google.cloud import bigquery
        job_params = []
        for k, v in params.items():
            if isinstance(v, datetime):
                job_params.append(bigquery.ScalarQueryParameter(k, "TIMESTAMP", v))
            elif isinstance(v, bool):
                job_params.append(bigquery.ScalarQueryParameter(k, "BOOL", v))
            elif isinstance(v, int):
                job_params.append(bigquery.ScalarQueryParameter(k, "INT64", v))
            else:
                job_params.append(bigquery.ScalarQueryParameter(k, "STRING", v))
        job = self._bq().query(
            assert_no_raw_table(sql),
            job_config=bigquery.QueryJobConfig(query_parameters=job_params),
        )
        return [dict(row) for row in job.result()]

    def list_events(self, date: str, filters: dict[str, Any]) -> list[dict]:
        sql, params = build_list_query(date, filters)
        return self._run(sql, params)

    def get_event(self, session_id: str, date: str,
                  keyword: Optional[str] = None, exp_version: Optional[str] = None,
                  locale: Optional[str] = None) -> Optional[dict]:
        sql, params = build_detail_query(session_id, date, keyword, exp_version, locale)
        rows = self._run(sql, params)
        if not rows:
            return None
        row = rows[0]
        row["ip_masked"] = mask_ip_to_24(row.get("ip_masked"))
        return row

    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]:
        sql, params = build_cf_query(session_id, date, keyword, exp_version, locale)
        rows = self._run(sql, params)
        return rows[0]["cf_raw"] if rows else None

    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]:
        sql, params = build_prods_query(date, keyword, locale, exp_version, session_id)
        return self._run(sql, params)


_repo_singleton: Optional[EventRepo] = None


def get_repo() -> EventRepo:
    """API 層的 repo factory (FastAPI Depends 每請求呼叫一次)。

    Singleton:BigQueryEventRepo 的 client 建立含憑證流程,不該每請求重建。
    USE_FAKE=1 時吃內建 demo 資料 (BQ 表未就緒也能跑);env 在首次呼叫時定案。
    """
    global _repo_singleton
    if _repo_singleton is None:
        if os.getenv("USE_FAKE") == "1":
            from .fake import FakeEventRepo
            _repo_singleton = FakeEventRepo()
        else:
            _repo_singleton = BigQueryEventRepo()
    return _repo_singleton
