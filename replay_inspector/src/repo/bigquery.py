"""資料存取層 — 直查資料團隊維護的原始事件表,分區/叢集/PII 規則都在這一層。

資料源 (2026-08-27 定案,改回原始表):`dw_analysis_record.stream_search_record`
(VIEW,`data` 為原生 JSON 型別)。JSON path 對映以 `sql/search_event_daily.sqlx` +
`sql/search_event_prod_daily.sqlx`(資料團隊 review 過的 dataform 初稿,原本要餵
flat 表,2026-08-26 一度 SUPERSEDED)為準,並已對 `kkday-data-dap-ui` 帳單 project
實跑真資料驗證過 (2026-08-27,event_date=2026-08-24,keyword=福岡)。驗證時抓到
並修正 3 個 sqlx 原稿寫錯的路徑 (request_type 欄位不存在、cf.hour/weekday 應巢狀
在 cf.time_context 下、uf_user_type/uf_membership_tier 是 uf.profile 特徵表裡的
具名 feature 不是獨立欄位) —— 完整脈絡見 CLAUDE.md 紅線 1。

為什麼改回去(2026-08-27,跟 RD 討論後定案):
- 該表是 VIEW 且 `data` 為原生 JSON 型別 → per-path 計費有效(sqlx 內註記:
  1hr 窗 dry-run 估 9.17GB、實際計費 12.6MB,728 倍差;dry-run 數字僅為上限)
- Slack 討論(2026-08-26,D07NAF7UGKH)實測:無過濾 + LIMIT 1000 只要 117~132MB;
  kkud/event_id 等值過濾會到 12.9~35.7GB,但 RD (Duncan) 澄清這是「過程查詢量」
  (計費用的 bytes processed),不是硬碟(storage)占用,不會累積成本
- 帳單 project 指到 `kkday-data-dap-ui`(與主平台 backend 用的 `-sit` 隔開)

沿用的紅線(跟原始表無關,一律適用):
- `event_date` 分區條件必填,範圍比較(不用 TIMESTAMP_TRUNC)
- 列表 LIMIT 50(單次回放 session 約 2~4 次查詢)
- keyword 或 kkud 至少一項必填(`ClusterKeyRequired`)—— 原始表沒有實體叢集,
  這條規則现在是「正確性」考量(鎖定唯一事件)而非省成本,event_id-only 點查
  仍會拉出不只一筆
- ip 欄未遮罩 — API 層一律轉 /24 才出去

MCP tool (後續 search-event-inspect) 與 UI 共用這一層,規則只維護一份。
"""
from __future__ import annotations

import ipaddress
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

BQ_PROJECT_ID = os.getenv("BQ_PROJECT_ID", "kkday-data-dap")
BQ_DATASET = os.getenv("BQ_DATASET", "dw_analysis_record")
BQ_BILLING_PROJECT = os.getenv("BQ_BILLING_PROJECT", "kkday-data-dap-ui")

RAW_TABLE = f"`{BQ_PROJECT_ID}.{BQ_DATASET}.stream_search_record`"

# 單次查詢硬上限 —— 只當「跑到明顯失控」的最後防線,不是真正的 20GB 用量控管。
#
# ⚠ 2026-08-27 實測推翻:原本設 20GB,結果連平常的「單人回放,只給 keyword」
# 查詢都被擋(BigQuery 官方文件:maximum_bytes_billed 是拿查詢送出前的「預估」
# 位元組數比對,超過就直接不跑)。用 dry_run 量到:同一句 SQL,不管拿掉
# keyword 過濾、拿掉 ORDER BY、砍到只剩 3 個欄位,預估值全部釘在 112.92GB
# 一動也不動 —— 這張表的 JSON per-path 計費優化只有「真的跑」才會生效,
# BigQuery 的預估器對 JSON 欄位沒有 per-path 概念,一律抓「整欄上限」當預估值
# (跟 sql/*.sqlx 裡「dry-run 估 9.17GB、實跑計費 12.6MB,728 倍差」是同一件事,
# 只是這次差距沒那麼誇張)。拿掉這層預估限制後真的跑同一句查詢,實際計費是
# 20.4GB(用 job.total_bytes_billed 量的,不是估的)。
#
# 結論:maximum_bytes_billed 這個機制對這張表不可靠 —— 用「預估」擋真實用量,
# 會把明明便宜的查詢也一起擋掉。改把這個常數當「跑到失控才擋」的最後防線
# (預設抓到比觀察到的最高預估值 112.92GB 還高一截,不擋一般查詢),真正的
# 20GB 級用量控管改成事後量測 + UI 顯示(見 last_query_bytes()),不是這裡。
# 2026-08-31 使用者要求拿掉單次查詢上限:預設不設 maximum_bytes_billed(不擋)。
# 原因見上方註解 —— 預估值對這張 JSON 表灌水,任何合理上限都會擋到便宜查詢。
# 仍保留 env 覆寫:要重新設失控防線時給 BQ_MAX_BYTES_BILLED(直接給位元組數)。
_env_max = os.getenv("BQ_MAX_BYTES_BILLED")
MAX_BYTES_BILLED_PER_QUERY = int(_env_max) if _env_max else None

TZ_TAIPEI = timezone(timedelta(hours=8))

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
    """缺 keyword / kkud 等值 — 原始表無實體叢集,這條規則現在是正確性考量
    (鎖定唯一事件),不是省成本;event_id-only 點查仍可能抓出不只一筆。
    API 層轉 400,查詢不得送出。"""


class QueryTooExpensive(RuntimeError):
    """單次查詢預估位元組數超過 MAX_BYTES_BILLED_PER_QUERY(預設 300GB,
    只當失控防線 — 見該常數註解),BigQuery 直接拒絕執行。API 層轉 400。"""


def _is_bytes_billed_limit_error(e: Exception) -> bool:
    """判斷 BigQuery 例外是不是 maximum_bytes_billed 超標 —— 優先讀
    google.api_core.exceptions.GoogleAPICallError.errors 裡結構化的
    reason == 'bytesBilledLimitExceeded'(實測 2026-08-27:
    google.api_core.exceptions.InternalServerError,errors=[{'reason':
    'bytesBilledLimitExceeded', ...}]),字串比對只當這個屬性不存在時的
    備援(2026-08-27 code review 抓到:原本只做字串比對,SDK 措辭一變
    就會悄悄失效)。"""
    for err in getattr(e, "errors", None) or []:
        if isinstance(err, dict) and err.get("reason") == "bytesBilledLimitExceeded":
            return True
    return "bytes billed" in str(e).lower()


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
    """原始表的 ip 欄是原始 IP — 出 API 前一律遮罩成 /24。"""
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
                  locale: Optional[str] = None) -> Optional[dict]:
        """回傳的 dict 必須含 `"prods"`(parse_prods() 格式的 list[dict],
        找不到就給 `[]`,不可省略此 key)—— 2026-08-27 起 main.py::event_detail
        直接讀 `ev.get("prods")`,不再另外呼叫 get_prods()(省一支重複查詢,
        原本的 build_prods_query() 掃的是同一列資料)。任何實作(含測試用
        stub/fake)忘記塞這個 key,event_detail 會靜默回空商品列表,不會報錯
        —— 見 tests/test_api.py 的 FakeEventRepo/stub 都必須帶上這個 key。"""
        ...
    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]: ...
    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]: ...
    def last_query_bytes(self) -> int:
        """最近一次公開方法呼叫(list_events/get_event/...)累積的 BQ 計費位元組數。
        給 UI 顯示「這次查詢用了多少資料量」(2026-08-27 使用者要求)。"""
        ...


# ── 查詢建構器 (原始表 · JSON 抽取) ────────────────────────────────────────────
# JSON path 對映參考 sql/search_event_daily.sqlx + search_event_prod_daily.sqlx
# (資料團隊 review 過的 dataform 初稿),已用真資料驗證過 (見上方 module docstring)。

# API filter 名 → SQL 運算式 (原始表無實體欄位,一律 JSON_VALUE 抽取)
_FILTER_COLS = {
    "keyword": "JSON_VALUE(data, '$.query.keyword')",
    "kkud": "JSON_VALUE(data, '$.kkud')",
    "member_uuid": "JSON_VALUE(data, '$.member_uuid')",
    "session_id": "event_id",       # API 的 session_id = content 的 event_id (頂層欄位)
    "exp_version": "JSON_VALUE(data, '$.experiment.exp_version')",
    "locale": "JSON_VALUE(data, '$.query.locale')",
    "lang": "JSON_VALUE(data, '$.query.lang')",
    "currency": "JSON_VALUE(data, '$.query.currency')",
}

# 列表/明細共用的 content 列欄位映射。event_id/event_date/event_type/cache_hit 是
# 原始表頂層欄位 (非 JSON,sqlx 已確認),其餘皆為 JSON 抽取。uf_* 不在此列 ——
# content 事件本身沒有 uf (只掛在 recall,spec 2.3),detail 路徑由 get_event()
# 二段回查補上;PII 只出衍生欄 (logged_in)。
_CONTENT_BASE_COLS = (
    "event_id AS session_id, event_date, event_type, cache_hit, "
    "JSON_VALUE(data, '$.query.keyword') AS keyword, "
    "JSON_VALUE(data, '$.query.locale') AS locale, "
    "JSON_VALUE(data, '$.query.lang') AS lang, "
    "JSON_VALUE(data, '$.query.currency') AS currency, "
    "JSON_VALUE(data, '$.experiment.exp_version') AS exp_version, "
    "JSON_VALUE(data, '$.source') AS source, "
    "JSON_VALUE(data, '$.kkud') AS kkud, "
    "SAFE_CAST(JSON_VALUE(data, '$.pagination.start') AS INT64) AS page_start, "
    "SAFE_CAST(JSON_VALUE(data, '$.pagination.count') AS INT64) AS page_count, "
    "SAFE_CAST(JSON_VALUE(data, '$.pagination.total_count') AS INT64) AS total_count, "
    "ARRAY_LENGTH(JSON_QUERY_ARRAY(data, '$.prods')) AS prod_cnt, "
    "JSON_VALUE(data, '$.source_event_id') AS source_event_id, "
    "(JSON_VALUE(data, '$.source_event_id') IS NULL) AS join_failed, "
    "CAST(NULL AS BOOL) AS uf_absent, "   # detail 路徑由 get_event() 回查後填正確值;list 路徑維持 unknown (不猜)
    "(JSON_VALUE(data, '$.member_uuid') IS NOT NULL) AS logged_in"
)


def _require_cluster_key(filters: dict[str, Any]) -> None:
    if not filters.get("keyword") and not filters.get("kkud"):
        raise ClusterKeyRequired(
            "keyword 或 kkud 至少一項必填 — 用於鎖定唯一事件 (正確性考量,"
            "原始表無實體叢集,不代表能降低掃描量)"
        )


def _day_where(date: str, params: dict[str, Any]) -> list[str]:
    start, end = local_date_to_utc_range(date)
    params["p_start"] = start
    params["p_end"] = end
    return ["event_date >= @p_start", "event_date < @p_end"]


def build_list_query(date: str, filters: dict[str, Any]) -> tuple[str, dict]:
    """列表:content 列,強制 keyword/kkud 至少一項,LIMIT 50。member_uuid 走 POST body (5.1)。"""
    _require_cluster_key(filters)
    params: dict[str, Any] = {}
    where = _day_where(date, params)
    where.append("event_type IN ('content', 'content.cache')")
    # 註:spec/sqlx 原本這裡有 request_type='product.list' 過濾,但 2026-08-27
    # 對真實資料實測 (event_date=2026-08-24) 發現 payload 根本沒有 request_type
    # 這個欄位 (TO_JSON_STRING(data) 完整 dump 沒這個 key) —— 加了會把所有列表
    # 濾光,已移除。目前 event_type IN ('content','content.cache') 已足夠界定範圍。
    for key, col in _FILTER_COLS.items():
        if filters.get(key) is not None:
            where.append(f"{col} = @{key}")
            params[key] = filters[key]
    if filters.get("cache_hit") is not None:
        where.append("cache_hit = @cache_hit")
        params["cache_hit"] = bool(filters["cache_hit"])
    sql = (
        f"SELECT {_CONTENT_BASE_COLS} FROM {RAW_TABLE} "
        f"WHERE {' AND '.join(where)} ORDER BY event_date DESC LIMIT {LIST_LIMIT}"
    )
    return sql, params


def build_detail_query(session_id: str, date: str,
                       keyword: Optional[str] = None,
                       exp_version: Optional[str] = None,
                       locale: Optional[str] = None) -> tuple[str, dict]:
    """明細 (content 列):keyword 為必填鎖定條件;uf/cf 在 recall 列,由
    get_event() 二段回查補上 (content 事件本身沒有 uf,spec 2.3)。"""
    _require_cluster_key({"keyword": keyword})
    params: dict[str, Any] = {"session_id": session_id, "keyword": keyword}
    where = _day_where(date, params)
    where += ["event_type IN ('content', 'content.cache')",
              "JSON_VALUE(data, '$.query.keyword') = @keyword",
              "event_id = @session_id"]
    if exp_version:
        where.append("JSON_VALUE(data, '$.experiment.exp_version') = @exp_version")
        params["exp_version"] = exp_version
    if locale:
        where.append("JSON_VALUE(data, '$.query.locale') = @locale")
        params["locale"] = locale
    # prods 併進這支查詢一起抽 (2026-08-27 實測發現):event_id 已鎖定同一列,
    # 跟原本另外呼叫 build_prods_query() 掃的是同一天同一列資料,只是抓的欄位
    # 不同 —— 併進來可以省掉一支重複查詢的計費(實測單筆 10~32GB,4 支砍到 3 支)
    cols = (_CONTENT_BASE_COLS +
            ", JSON_VALUE(data, '$.ip') AS ip, "
            "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.filter')), 'null') AS filter_json, "
            "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.prods')), 'null') AS prods_json")
    sql = (f"SELECT {cols} FROM {RAW_TABLE} "
           f"WHERE {' AND '.join(where)} LIMIT 1")
    return sql, params


# recall 列欄位:cf/qu/uf 只掛在 recall (spec 2.3,100% 覆蓋);uf_intent/
# uf_profile/uf_profile_version 也在此列,content 列沒有 uf。cf_raw 原始表可直接
# 整包抽取 (不像 flat 表需要拆欄重組)。
_RECALL_JSON_COLS = (
    "event_id, "
    "JSON_VALUE(data, '$.cf.platform') AS cf_platform, "
    # ✓ 實測修正 (2026-08-27,event_date=2026-08-24 真資料):cf.hour/cf.weekday
    # 不存在,實際巢狀在 cf.time_context 底下 (sqlx 原稿路徑是錯的)
    "SAFE_CAST(JSON_VALUE(data, '$.cf.time_context.hour') AS INT64) AS cf_hour, "
    "SAFE_CAST(JSON_VALUE(data, '$.cf.time_context.weekday') AS INT64) AS cf_weekday, "
    "JSON_VALUE(data, '$.cf.query.final') AS cf_query_final, "
    "ARRAY(SELECT JSON_VALUE(t) FROM UNNEST("
    "JSON_QUERY_ARRAY(data, '$.cf.query.tokens')) t) AS cf_query_tokens, "
    "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.cf')), 'null') AS cf_raw, "
    "JSON_VALUE(data, '$.query_understanding.normalized_keyword') AS qu_normalized_keyword, "
    "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.uf.intent')), 'null') AS uf_intent, "
    "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.uf.profile')), 'null') AS uf_profile, "
    "JSON_VALUE(data, '$.uf.profile_version') AS uf_profile_version, "
    # ✓ 實測修正 (2026-08-27,event_date=2026-08-24 真資料):不是獨立欄位,是
    # uf.profile 這個 {feature_name:{d,v,t}} 扁平特徵表裡兩個具名 feature 的
    # 值 (跟 spec 3.1「原樣保留,不展平」的其他 uf.profile.* 特徵同構);第一輪
    # 掃到的 20 筆樣本剛好都沒算出這兩個特徵 (per-user 特徵覆蓋率各自獨立,
    # 不是欄位不存在),用了有訂單歷史的使用者重測才驗到。
    "JSON_VALUE(data, '$.uf.profile.uf_user_type.d') AS uf_user_type, "
    "JSON_VALUE(data, '$.uf.profile.uf_membership_tier.d') AS uf_membership_tier, "
    "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.uf.lbs')), 'null') AS uf_lbs"
)


def build_recall_query(recall_event_id: str, date: str, kkud: str,
                       keyword: str) -> tuple[str, dict]:
    """recall 列回查 (uf/cf/qu):kkud + keyword 縮小範圍、event_id 結果過濾。
    keyword/kkud 在此不是實體叢集鍵,不保證降低掃描量,只是鎖定正確那一筆。"""
    _require_cluster_key({"keyword": keyword, "kkud": kkud})
    params: dict[str, Any] = {"event_id": recall_event_id,
                              "kkud": kkud, "keyword": keyword}
    where = _day_where(date, params)
    where += ["event_type IN ('recall', 'recall.cache')",
              "JSON_VALUE(data, '$.kkud') = @kkud",
              "JSON_VALUE(data, '$.query.keyword') = @keyword",
              "event_id = @event_id"]
    sql = (f"SELECT {_RECALL_JSON_COLS} FROM {RAW_TABLE} "
           f"WHERE {' AND '.join(where)} LIMIT 1")
    return sql, params


def build_prods_query(date: str, keyword: str, locale: Optional[str],
                      exp_version: str,
                      session_id: Optional[str] = None) -> tuple[str, dict]:
    """prods 在 content 列的 JSON 陣列 — 取回後由 repo 解析展開。
    session_id 帶入時鎖定單一事件 (同天同 keyword+exp 可能多個 session)。"""
    _require_cluster_key({"keyword": keyword})
    params: dict[str, Any] = {"keyword": keyword, "exp_version": exp_version}
    where = _day_where(date, params)
    where += ["event_type IN ('content', 'content.cache')",
              "JSON_VALUE(data, '$.query.keyword') = @keyword",
              "JSON_VALUE(data, '$.experiment.exp_version') = @exp_version"]
    if locale:
        where.append("JSON_VALUE(data, '$.query.locale') = @locale")
        params["locale"] = locale
    if session_id:
        where.append("event_id = @session_id")
        params["session_id"] = session_id
    sql = (
        "SELECT event_id, "
        "SAFE_CAST(JSON_VALUE(data, '$.pagination.start') AS INT64) AS pagination_start, "
        "NULLIF(TO_JSON_STRING(JSON_QUERY(data, '$.prods')), 'null') AS prods "
        f"FROM {RAW_TABLE} WHERE {' AND '.join(where)} "
        "ORDER BY event_date DESC LIMIT 1"
    )
    return sql, params


def parse_prods(prods_json: Optional[str], page_start: Optional[int]) -> list[dict]:
    """content 列的 prods (JSON 字串) → prod dict list。
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


class BigQueryEventRepo:
    """原始表實作。client 延遲建立,測試不需要 GCP 憑證。"""

    def __init__(self) -> None:
        self._client = None
        self._bytes_billed = 0   # 見 last_query_bytes();每個公開方法入口先 reset

    def _bq(self):
        if self._client is None:
            from google.cloud import bigquery
            self._client = bigquery.Client(project=BQ_BILLING_PROJECT)
        return self._client

    def _reset_cost(self) -> None:
        self._bytes_billed = 0

    def last_query_bytes(self) -> int:
        return self._bytes_billed

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
        job_config = bigquery.QueryJobConfig(query_parameters=job_params)
        # None = 不設上限。注意不能傳 maximum_bytes_billed=None 給 QueryJobConfig
        # —— client 會把它序列化成字串 "None" 送出,BigQuery 回 400
        # (Invalid value ... (TYPE_INT64), "None")。只有設了才掛上屬性。
        if MAX_BYTES_BILLED_PER_QUERY is not None:
            job_config.maximum_bytes_billed = MAX_BYTES_BILLED_PER_QUERY
        try:
            job = self._bq().query(sql, job_config=job_config)
            rows = [dict(row) for row in job.result()]
        except Exception as e:
            if _is_bytes_billed_limit_error(e):
                _cap = (
                    f"({MAX_BYTES_BILLED_PER_QUERY / 1024 ** 3:.0f}GB)"
                    if MAX_BYTES_BILLED_PER_QUERY else "(BQ_MAX_BYTES_BILLED)"
                )
                raise QueryTooExpensive(
                    f"單次查詢預估掃描量超過上限 {_cap},"
                    f"BigQuery 拒絕執行 —— 通常是缺 keyword/kkud 縮小範圍。"
                    f"原始錯誤:{e}"
                ) from e
            raise
        self._bytes_billed += job.total_bytes_billed or 0
        return rows

    def list_events(self, date: str, filters: dict[str, Any]) -> list[dict]:
        self._reset_cost()
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
        self._reset_cost()
        row = self._content_row(session_id, date, keyword, exp_version, locale)
        if not row:
            return None
        row["ip_masked"] = mask_ip_to_24(row.pop("ip", None))
        # prods 已併在 build_detail_query 裡一起抽 (省掉一支重複查詢,見該函式註解)
        row["prods"] = parse_prods(row.pop("prods_json", None), row.get("page_start"))
        # uf/cf/qu 只掛在 recall 列 (content 事件本身沒有 uf,spec 2.3) — 二段回查
        recall = self._recall_row(row, date)
        if recall:
            row["normalized_keyword"] = recall.get("qu_normalized_keyword")
            row["cf_platform"] = recall.get("cf_platform")
            row["cf_hour"] = recall.get("cf_hour")
            row["cf_weekday"] = recall.get("cf_weekday")
            row["cf_query_final"] = recall.get("cf_query_final")
            row["cf_query_tokens"] = list(recall.get("cf_query_tokens") or []) or None
            row["uf_intent"] = recall.get("uf_intent")
            row["uf_profile"] = recall.get("uf_profile")
            row["uf_profile_version"] = recall.get("uf_profile_version")
            row["uf_user_type"] = recall.get("uf_user_type")
            row["uf_membership_tier"] = recall.get("uf_membership_tier")
            row["uf_lbs"] = recall.get("uf_lbs")
            # 串到 recall,但上游沒推 uf (spec 3.1 uf_absent 定義)
            row["uf_absent"] = (recall.get("uf_intent") is None
                                and recall.get("uf_profile") is None
                                and recall.get("uf_lbs") is None)
        else:
            # 串不回 recall (含跨日 cache 超出單日窗) → join_failed
            row["join_failed"] = True
            row["normalized_keyword"] = None
            row["uf_absent"] = None   # 不知道 —— 根本沒查到 recall,跟「查到但沒推 uf」不同
            for k in ("cf_platform", "cf_hour", "cf_weekday", "cf_query_final",
                      "cf_query_tokens", "uf_intent", "uf_profile",
                      "uf_profile_version", "uf_user_type", "uf_membership_tier",
                      "uf_lbs"):
                row[k] = None
        row["ltr_features_recovered"] = False   # 原始表無 donor 概念
        return row

    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]:
        self._reset_cost()
        row = self._content_row(session_id, date, keyword, exp_version, locale)
        if not row:
            return None
        recall = self._recall_row(row, date)
        return recall.get("cf_raw") if recall else None

    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]:
        self._reset_cost()
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
