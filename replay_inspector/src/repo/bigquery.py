"""資料存取層 — 直查資料團隊維護的 flat 中繼表,分區/叢集/PII 規則都在這一層。

資料源 (2026-08-26 定案):`dw_analysis_record.stream_search_record_flat`
- 每日批次落 D-1,分區 `event_date`,叢集 `(event_type, kkud, query_keyword)`
- content 列已預 join uf (實測 100%);cf/qu/lbs 在 recall 列
- 成本實測 (單日分區):keyword 精準 566MB、kkud 精準 168MB、
  cf 回查 (kkud+keyword 剪枝 + event_id 過濾) 10.5MB — 全部百 MB 內

成本紅線:
- 原始事件流 (無 _flat 後綴的那張) 一律禁查 —
  per-path 計費 = path × 掃過的分區,「單筆」回查實測 14~36GB (2026-08-19 教訓)
- flat 表查詢強制帶叢集鍵 (kkud 或 query_keyword 等值),event_id-only
  點查會掃全天 (實測 21GB) — `ClusterKeyRequired` 擋下,API 層轉 400
- `event_date` 分區條件必填,範圍比較 (不用 TIMESTAMP_TRUNC)
- 列表 LIMIT 50 (單次回放 session 約 2~4 次查詢,總量 < 1GB)
- ip 欄未遮罩 — API 層一律轉 /24 才出去

MCP tool (後續 search-event-inspect) 與 UI 共用這一層,規則只維護一份。
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "kkday-data-dap")
BQ_DATASET = os.getenv("BQ_DATASET", "dw_analysis_record")
BQ_BILLING_PROJECT = os.getenv("BQ_BILLING_PROJECT", "kkday-data-dap-sit")

FLAT_TABLE = f"`{BQ_PROJECT_ID}.{BQ_DATASET}.stream_search_record_flat`"

TZ_TAIPEI = timezone(timedelta(hours=8))

# 原始事件流禁查 pattern:涵蓋 ar-stream_… 舊名與 stream_search_record;
# negative lookahead 放行我們的合法資料源 stream_search_record_flat
_RAW_TABLE_PATTERN = re.compile(
    r"(ar[-_])?stream[-_]search[-_]record(?!_flat)", re.IGNORECASE)

# spec 4.5:各特徵覆蓋率實測基準,與數值並列顯示
UF_COVERAGE_BASELINE = {
    "uf_intent": 0.635,
    "uf_profile": 0.540,
    "uf_lbs": 0.203,
    "cf": 1.0,
}

# 列表回應鍵白名單 (FakeRepo 與測試共用;PII 只出衍生欄 logged_in)
LIST_COLUMNS = [
    "session_id", "event_date", "event_type", "cache_hit", "keyword",
    "locale", "lang", "currency", "exp_version", "source", "kkud",
    "page_start", "page_count", "total_count", "prod_cnt",
    "source_event_id", "join_failed", "uf_absent",
]

RERANK_BOUNDARY = 100   # spec 4.4:只有召回 top 100 進精排
LIST_LIMIT = 50         # 使用者要求:limit 收小,單 session 10 幾次查詢內


class MissingPartitionDate(ValueError):
    """event_date 分區條件缺失 — API 層轉 400,查詢不得送出。"""


class ClusterKeyRequired(ValueError):
    """缺叢集鍵 (kkud / query_keyword 等值) — event_id-only 點查會掃全天
    分區 (實測 21GB),API 層轉 400,查詢不得送出。"""


def assert_no_raw_table(sql: str) -> str:
    """成本紅線防呆:SQL 摸到原始事件流即丟例外 (spec 驗收 1)。
    stream_search_record_flat 是合法資料源,不受此限。"""
    if _RAW_TABLE_PATTERN.search(sql):
        raise RuntimeError(
            "cost guard: query references raw event stream — 平台只准查 "
            "stream_search_record_flat (叢集中繼表);原始事件流的「單筆」"
            "回查實測 14~36GB (per-path × 分區),一律禁止"
        )
    return sql


def local_date_to_utc_range(date_str: str) -> tuple[datetime, datetime]:
    """UTC+8 日曆日 → UTC 分區範圍,前後各留 8 小時緩衝 (spec 5.1)。"""
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
    """flat 表的 ip 欄是原始 IP — 出 API 前一律遮罩成 /24。"""
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


# ── 查詢建構器 (flat 表) ───────────────────────────────────────────────────────

# API filter 名 → flat 欄位;cache_hit 特殊處理 (event_type 推導)
_FILTER_COLS = {
    "keyword": "query_keyword",
    "kkud": "kkud",
    "member_uuid": "member_uuid",
    "session_id": "event_id",       # API 的 session_id = content 的 event_id
    "exp_version": "exp_version",
    "locale": "query_locale",
    "lang": "query_lang",
    "currency": "query_currency",
}

# 列表/明細共用的 content 列欄位映射 (cf_raw 概念不存在於 flat;PII 只出衍生欄)
_CONTENT_BASE_COLS = (
    "event_id AS session_id, event_date, event_type, "
    "(event_type = 'content.cache') AS cache_hit, "
    "query_keyword AS keyword, query_locale AS locale, query_lang AS lang, "
    "query_currency AS currency, exp_version, source, kkud, "
    "pagination_start AS page_start, pagination_count AS page_count, "
    "pagination_total_count AS total_count, prod_cnt, source_event_id, "
    "(source_event_id IS NULL) AS join_failed, "
    "(uf_intent IS NULL AND uf_profile IS NULL) AS uf_absent, "
    "(member_uuid IS NOT NULL) AS logged_in"
)


def _require_cluster_key(filters: dict[str, Any]) -> None:
    if not filters.get("keyword") and not filters.get("kkud"):
        raise ClusterKeyRequired(
            "keyword 或 kkud 至少一項必填 — 這兩個是 flat 表的叢集鍵,"
            "缺了會掃整天分區 (實測 21GB/次)"
        )


def _day_where(date: str, params: dict[str, Any]) -> list[str]:
    start, end = local_date_to_utc_range(date)
    params["p_start"] = start
    params["p_end"] = end
    return ["event_date >= @p_start", "event_date < @p_end"]


def build_list_query(date: str, filters: dict[str, Any]) -> tuple[str, dict]:
    """列表:content 列,強制叢集鍵,LIMIT 50。member_uuid 走 POST body (5.1)。"""
    _require_cluster_key(filters)
    params: dict[str, Any] = {}
    where = _day_where(date, params)
    where.append("event_type IN ('content', 'content.cache')")
    for key, col in _FILTER_COLS.items():
        if filters.get(key) is not None:
            where.append(f"{col} = @{key}")
            params[key] = filters[key]
    if filters.get("cache_hit") is not None:
        where.append("event_type = @et")
        params["et"] = "content.cache" if filters["cache_hit"] else "content"
    sql = (
        f"SELECT {_CONTENT_BASE_COLS} FROM {FLAT_TABLE} "
        f"WHERE {' AND '.join(where)} ORDER BY event_date DESC LIMIT {LIST_LIMIT}"
    )
    return assert_no_raw_table(sql), params


def build_detail_query(session_id: str, date: str,
                       keyword: Optional[str] = None,
                       exp_version: Optional[str] = None,
                       locale: Optional[str] = None) -> tuple[str, dict]:
    """明細 (content 列):keyword 為叢集鍵必填;uf 已預 join 在 content 列。"""
    _require_cluster_key({"keyword": keyword})
    params: dict[str, Any] = {"session_id": session_id, "keyword": keyword}
    where = _day_where(date, params)
    where += ["event_type IN ('content', 'content.cache')",
              "query_keyword = @keyword", "event_id = @session_id"]
    if exp_version:
        where.append("exp_version = @exp_version")
        params["exp_version"] = exp_version
    if locale:
        where.append("query_locale = @locale")
        params["locale"] = locale
    cols = (_CONTENT_BASE_COLS +
            ", ip, search_filter AS filter_json, "
            "uf_intent, uf_profile, profile_version AS uf_profile_version, "
            "uf_user_type, uf_membership_tier")
    sql = (f"SELECT {cols} FROM {FLAT_TABLE} "
           f"WHERE {' AND '.join(where)} LIMIT 1")
    return assert_no_raw_table(sql), params


# recall 列的 cf/qu/lbs 欄位 (cf 摘要 + 完整 cf 組裝共用)
_RECALL_CF_COLS = (
    "event_id, cf_platform, cf_hour, cf_weekday, "
    "cf_query_raw, cf_query_normalized, cf_query_rewritten, cf_query_final, "
    "cf_query_tokens, cf_query_synonym, cf_query_correction, "
    "cf_entities, cf_intent, cf_recall_features, "
    "qu_normalized_keyword, "
    "lbs_injected, lbs_city, lbs_trip_destination, lbs_trip_phase"
)


def build_recall_query(recall_event_id: str, date: str, kkud: str,
                       keyword: str) -> tuple[str, dict]:
    """recall 列回查 (cf/qu/lbs):kkud + keyword 叢集剪枝、event_id 結果過濾。
    實測 10.5MB/次;沒有叢集鍵的 event_id-only 版本是 21GB — 差 2000 倍。"""
    _require_cluster_key({"keyword": keyword, "kkud": kkud})
    params: dict[str, Any] = {"event_id": recall_event_id,
                              "kkud": kkud, "keyword": keyword}
    where = _day_where(date, params)
    where += ["event_type IN ('recall', 'recall.cache')",
              "kkud = @kkud", "query_keyword = @keyword",
              "event_id = @event_id"]
    sql = (f"SELECT {_RECALL_CF_COLS} FROM {FLAT_TABLE} "
           f"WHERE {' AND '.join(where)} LIMIT 1")
    return assert_no_raw_table(sql), params


def build_prods_query(date: str, keyword: str, locale: Optional[str],
                      exp_version: str,
                      session_id: Optional[str] = None) -> tuple[str, dict]:
    """prods 在 content 列的 JSON 欄位 — 取回後由 repo 解析展開。
    session_id 帶入時鎖定單一事件 (同天同 keyword+exp 可能多個 session)。"""
    _require_cluster_key({"keyword": keyword})
    params: dict[str, Any] = {"keyword": keyword, "exp_version": exp_version}
    where = _day_where(date, params)
    where += ["event_type IN ('content', 'content.cache')",
              "query_keyword = @keyword", "exp_version = @exp_version"]
    if locale:
        where.append("query_locale = @locale")
        params["locale"] = locale
    if session_id:
        where.append("event_id = @session_id")
        params["session_id"] = session_id
    sql = (f"SELECT event_id, pagination_start, prods FROM {FLAT_TABLE} "
           f"WHERE {' AND '.join(where)} ORDER BY event_date DESC LIMIT 1")
    return assert_no_raw_table(sql), params


def parse_prods(prods_json: Optional[str], page_start: Optional[int]) -> list[dict]:
    """flat.prods (JSON 字串) → prod dict list。
    rank = pagination_start + 頁內 offset + 1 (spec 3.2);payload 無商品名。"""
    if not prods_json:
        return []
    try:
        items = json.loads(prods_json) if isinstance(prods_json, str) else prods_json
    except (ValueError, TypeError):
        return []
    if not isinstance(items, list):
        return []
    base = page_start or 0
    out = []
    for idx, p in enumerate(items):
        if not isinstance(p, dict):
            continue
        rank = base + idx + 1
        ltr = p.get("ltr_score")
        out.append({
            "rank": rank,
            "prod_mid": str(p.get("prod_mid")) if p.get("prod_mid") is not None else None,
            "prod_oid": str(p.get("prod_oid")) if p.get("prod_oid") is not None else None,
            "prod_name": p.get("prod_name"),   # 實測 payload 無此欄 → None,UI fallback mid
            "is_ad": bool(p.get("is_ad")),
            "ltr_score": float(ltr) if ltr is not None else None,
            "relevance_status_code": p.get("relevance_status_code"),
            "in_rerank_scope": rank <= RERANK_BOUNDARY,
        })
    return out


def _assemble_cf_raw(recall_row: dict) -> str:
    """flat 沒有整包 cf_raw — 以全部 cf_*/qu_*/lbs_* 欄組回 JSON 供 5.4 展開。"""
    def _j(v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return v
        return v
    return json.dumps({
        "platform": recall_row.get("cf_platform"),
        "hour": recall_row.get("cf_hour"),
        "weekday": recall_row.get("cf_weekday"),
        "query": {
            "raw": recall_row.get("cf_query_raw"),
            "normalized": recall_row.get("cf_query_normalized"),
            "rewritten": recall_row.get("cf_query_rewritten"),
            "final": recall_row.get("cf_query_final"),
            "tokens": list(recall_row.get("cf_query_tokens") or []),
            "synonym": list(recall_row.get("cf_query_synonym") or []),
            "correction": list(recall_row.get("cf_query_correction") or []),
        },
        "entities": _j(recall_row.get("cf_entities")),
        "intent": _j(recall_row.get("cf_intent")),
        "recall_features": _j(recall_row.get("cf_recall_features")),
        "qu_normalized_keyword": recall_row.get("qu_normalized_keyword"),
        "lbs": {
            "injected": recall_row.get("lbs_injected"),
            "city": recall_row.get("lbs_city"),
            "trip_destination": recall_row.get("lbs_trip_destination"),
            "trip_phase": recall_row.get("lbs_trip_phase"),
        },
    }, ensure_ascii=False)


class BigQueryEventRepo:
    """flat 表實作。client 延遲建立,測試不需要 GCP 憑證。"""

    def __init__(self) -> None:
        self._client = None

    def _bq(self):
        if self._client is None:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=BQ_BILLING_PROJECT)
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

    def _content_row(self, session_id, date, keyword, exp_version, locale):
        sql, params = build_detail_query(session_id, date, keyword, exp_version, locale)
        rows = self._run(sql, params)
        return rows[0] if rows else None

    def _recall_row(self, row: dict, date: str) -> Optional[dict]:
        src, kkud, kw = row.get("source_event_id"), row.get("kkud"), row.get("keyword")
        if not (src and kkud and kw):
            return None
        sql, params = build_recall_query(src, date, kkud, kw)
        rows = self._run(sql, params)
        return rows[0] if rows else None

    def get_event(self, session_id: str, date: str,
                  keyword: Optional[str] = None, exp_version: Optional[str] = None,
                  locale: Optional[str] = None) -> Optional[dict]:
        row = self._content_row(session_id, date, keyword, exp_version, locale)
        if not row:
            return None
        row["ip_masked"] = mask_ip_to_24(row.pop("ip", None))
        # cf/qu/lbs 在 recall 列 — 第二段回查 (kkud+keyword 剪枝,10.5MB/次)
        recall = self._recall_row(row, date)
        if recall:
            row["normalized_keyword"] = recall.get("qu_normalized_keyword")
            row["cf_platform"] = recall.get("cf_platform")
            row["cf_hour"] = recall.get("cf_hour")
            row["cf_weekday"] = recall.get("cf_weekday")
            row["cf_query_final"] = recall.get("cf_query_final")
            row["cf_query_tokens"] = list(recall.get("cf_query_tokens") or []) or None
            lbs = {k: recall.get(f"lbs_{k}")
                   for k in ("injected", "city", "trip_destination", "trip_phase")}
            row["uf_lbs"] = (json.dumps(lbs, ensure_ascii=False)
                             if any(v is not None for v in lbs.values()) else None)
        else:
            # 串不回 recall (含跨日 cache 超出單日窗) → join_failed
            row["join_failed"] = True
            row["normalized_keyword"] = None
            for k in ("cf_platform", "cf_hour", "cf_weekday",
                      "cf_query_final", "cf_query_tokens", "uf_lbs"):
                row[k] = None
        row["ltr_features_recovered"] = False   # flat 表無 donor 概念
        return row

    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]:
        row = self._content_row(session_id, date, keyword, exp_version, locale)
        if not row:
            return None
        recall = self._recall_row(row, date)
        return _assemble_cf_raw(recall) if recall else None

    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]:
        sql, params = build_prods_query(date, keyword, locale, exp_version, session_id)
        rows = self._run(sql, params)
        if not rows:
            return []
        return parse_prods(rows[0].get("prods"), rows[0].get("pagination_start"))


_repo_singleton: Optional[EventRepo] = None


def get_repo() -> EventRepo:
    """API 層的 repo factory (FastAPI Depends 每請求呼叫一次)。

    Singleton:BigQueryEventRepo 的 client 建立含憑證流程,不該每請求重建。
    USE_FAKE=1 時吃內建 demo 資料;env 在首次呼叫時定案。
    """
    global _repo_singleton
    if _repo_singleton is None:
        if os.getenv("USE_FAKE") == "1":
            from .fake import FakeEventRepo
            _repo_singleton = FakeEventRepo()
        else:
            _repo_singleton = BigQueryEventRepo()
    return _repo_singleton
