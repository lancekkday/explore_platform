"""API 契約測試 — TestClient + FakeEventRepo,對映 spec §8 驗收條件。"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.repo.bigquery import get_repo
from src.repo.fake import DEMO_DATE, FakeEventRepo


@pytest.fixture()
def repo():
    return FakeEventRepo()


@pytest.fixture()
def client(repo):
    app.dependency_overrides[get_repo] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


# ── 驗收 2:缺 date → 400 且不送查詢 ──────────────────────────────────────────

def test_missing_date_returns_400_without_query(client, repo):
    r = client.get("/api/events", params={"keyword": "福岡"})
    assert r.status_code == 400
    assert repo.query_count == 0, "缺分區條件時查詢不得送出"


def test_bad_date_format_400(client, repo):
    r = client.get("/api/events", params={"date": "08/13/2026", "keyword": "福岡"})
    assert r.status_code == 400
    assert repo.query_count == 0


def test_detail_and_cf_also_require_date(client, repo):
    assert client.get("/api/events/sess-fukuoka-treatment").status_code == 400
    assert client.get("/api/events/sess-fukuoka-treatment/cf").status_code == 400
    assert repo.query_count == 0


# ── 5.2 filter 四選一 ─────────────────────────────────────────────────────────

def test_list_requires_at_least_one_filter(client, repo):
    r = client.get("/api/events", params={"date": DEMO_DATE})
    assert r.status_code == 400
    assert repo.query_count == 0


def test_list_by_keyword(client):
    r = client.get("/api/events", params={"date": DEMO_DATE, "keyword": "福岡"})
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert {row["exp_version"] for row in rows} == {"exp_a", "exp_b"}
    assert all("event_date_local" in row for row in rows)


# ── PII 不進 URL query string (5.1) ──────────────────────────────────────────

def test_member_uuid_in_query_string_rejected(client, repo):
    r = client.get("/api/events", params={"date": DEMO_DATE, "member_uuid": "m-123"})
    assert r.status_code == 400
    assert "query string" in r.json()["detail"]
    assert repo.query_count == 0


def test_pii_in_query_string_rejected_on_all_get_endpoints(client, repo):
    """cf / detail / compare 一樣不准 PII 進 query string (5.1)。"""
    for path in ("/api/events/sess-fukuoka-treatment",
                 "/api/events/sess-fukuoka-treatment/cf",
                 "/api/compare"):
        r = client.get(path, params={"date": DEMO_DATE, "user_id": "u-1"})
        assert r.status_code == 400, path
    assert repo.query_count == 0


def test_member_uuid_via_post_body_needs_cluster_key(client):
    """member_uuid 只能當附加過濾 — 單獨用會缺叢集鍵 (掃全天分區) → 400;
    搭配 keyword 即合法。"""
    r = client.post("/api/events/search", json={"date": DEMO_DATE, "member_uuid": "m-123"})
    assert r.status_code == 400
    r2 = client.post("/api/events/search",
                     json={"date": DEMO_DATE, "keyword": "福岡", "member_uuid": "m-123"})
    assert r2.status_code == 200     # 查無資料也回 200 空列表
    assert r2.json()["rows"] == []


# ── 驗收 7:列表無 cf_raw、ip 僅 /24 ──────────────────────────────────────────

def test_list_response_has_no_cf_raw_or_pii(client):
    r = client.get("/api/events", params={"date": DEMO_DATE, "keyword": "福岡"})
    for row in r.json()["rows"]:
        assert "cf_raw" not in row
        assert "member_uuid" not in row
        assert "user_id" not in row
        assert "ip_masked" not in row


def test_detail_ip_is_slash24(client):
    r = client.get("/api/events/sess-fukuoka-treatment", params={"date": DEMO_DATE})
    assert r.status_code == 200
    body = r.json()
    assert body["ip_masked"].endswith("/24")
    assert "cf_raw" not in body


# ── 5.3 明細組裝 ──────────────────────────────────────────────────────────────

def test_detail_contains_decoded_relevance_and_bands(client):
    body = client.get(
        "/api/events/sess-fukuoka-treatment", params={"date": DEMO_DATE}
    ).json()
    prods = body["prods"]
    assert prods[0]["relevance"]["ip"] == 2          # '000220' 第 4 位
    assert prods[0]["tie_band"] == 0
    # 前 6 名建構成同帶
    assert len({p["tie_band"] for p in prods[:6]}) == 1
    assert body["quality_flags"] == {
        "join_failed": False, "uf_absent": False, "ltr_features_recovered": False,
    }
    assert body["coverage_baseline"]["uf_lbs"] == pytest.approx(0.203)
    assert body["pagination"]["rerank_boundary"] == 100


def test_detail_join_failed_flag(client):
    # 驗收 6 的 API 面:旗標要正確送出,UI 據此置灰
    body = client.get("/api/events/sess-join-failed", params={"date": DEMO_DATE}).json()
    assert body["quality_flags"]["join_failed"] is True


def test_detail_404(client):
    assert client.get("/api/events/nope", params={"date": DEMO_DATE}).status_code == 404


# ── 5.4 cf 單筆 ──────────────────────────────────────────────────────────────

def test_cf_endpoint_returns_raw(client):
    r = client.get("/api/events/sess-fukuoka-treatment/cf", params={"date": DEMO_DATE})
    assert r.status_code == 200
    assert "cf_raw" in r.json()


# ── 驗收 3 + 4:compare 福岡 ──────────────────────────────────────────────────

def test_compare_fukuoka_strength_and_ties(client):
    r = client.get("/api/compare", params={
        "date": DEMO_DATE, "keyword": "福岡", "exp_a": "exp_a", "exp_b": "exp_b",
    })
    assert r.status_code == 200
    body = r.json()

    m = body["metrics"]
    # fixture:top10 重疊 8 (兩顆 only_a / only_b) → 強度 0.2,正常區間無警示
    assert m["top10_overlap"] == 8
    assert m["personalization_strength"] == pytest.approx(0.2)
    assert m["warning"] is None

    by_mid = {row["prod_mid"]: row for row in body["rows"]}
    # 帶內互換的前兩名 → 「同分帶,不可判讀」而非 Δ=-1 (驗收 4)
    assert by_mid["248950"]["verdict"] == "tie_unresolvable"
    assert by_mid["131075"]["verdict"] == "tie_unresolvable"
    # 單側出現 → 個性化實質證據
    assert by_mid["144906"]["verdict"] == "only_a"
    assert by_mid["907001"]["verdict"] == "only_b"

    # rows 依 rank_a 升冪、缺值排後 (5.5)
    ranks = [row["rank_a"] for row in body["rows"]]
    non_null = [x for x in ranks if x is not None]
    assert non_null == sorted(non_null)
    assert all(x is None for x in ranks[len(non_null):])


def test_compare_requires_keyword(client, repo):
    r = client.get("/api/compare", params={"date": DEMO_DATE})
    assert r.status_code == 400
    assert repo.query_count == 0


def test_compare_auto_detects_experiments(client):
    """exp_a/exp_b 可省略 — 自動從當日事件偵測兩組 (升冪:A=較小編號=treatment
    慣例);表格 meta.a/b 帶回各側 exp / lang / locale / cf。"""
    r = client.get("/api/compare", params={"date": DEMO_DATE, "keyword": "福岡"})
    assert r.status_code == 200, r.text
    meta = r.json()["meta"]
    assert meta["exp_a"] == "exp_a" and meta["exp_b"] == "exp_b"
    assert meta["a"]["exp_version"] == "exp_a"
    assert meta["a"]["lang"] == "zh-tw" and meta["a"]["locale"] == "tw"
    assert meta["a"]["cf"]["platform"] == "web"
    assert meta["b"]["exp_version"] == "exp_b"
    # 指標與顯式指定時一致
    assert r.json()["metrics"]["top10_overlap"] == 8


# ── 驗收 1(2026-08-27 改回原始表後失效,見下方 test_raw_table_is_query_source)──

def test_raw_table_is_query_source():
    """2026-08-27 定案(跟 RD 討論後改回去):平台直查原始表
    `stream_search_record`,不再是 `_flat` 中繼表;帳單 project 指到
    kkday-data-dap-ui(跟主平台 backend 的 -sit 隔開)。"""
    from src.repo import bigquery
    assert bigquery.RAW_TABLE == "`kkday-data-dap.dw_analysis_record.stream_search_record`"
    assert not hasattr(bigquery, "assert_no_raw_table"), \
        "成本紅線已撤除 (2026-08-27) — 若還存在代表改回去的動作沒做乾淨"
    assert bigquery.BQ_BILLING_PROJECT == "kkday-data-dap-ui"


# ── repo 層例外一律轉 400,不得漏接變成未處理的 500(2026-08-27 code review)──
# 起因:event_detail/event_cf 原本各自寫 try/except 只接 QueryTooExpensive,
# 漏了 ClusterKeyRequired;main._repo_call 統一處理後在此鎖住四個端點,
# 避免以後又有端點漏接其中一種。

class _RaisingRepo:
    """故意讓每個方法丟指定例外的 stub — 只驗證 main.py 的例外轉換,
    不需要真的連 BigQuery。"""

    def __init__(self, exc):
        self._exc = exc

    def list_events(self, date, filters):
        raise self._exc

    def get_event(self, session_id, date, keyword=None, exp_version=None, locale=None):
        raise self._exc

    def get_cf_raw(self, session_id, date, keyword=None, exp_version=None, locale=None):
        raise self._exc

    def get_prods(self, date, keyword, locale, exp_version, session_id=None):
        raise self._exc

    def last_query_bytes(self):
        return 0


@pytest.fixture(params=["cluster_key", "too_expensive"])
def raising_client(request):
    from src.repo.bigquery import ClusterKeyRequired, QueryTooExpensive
    exc = (ClusterKeyRequired("missing keyword") if request.param == "cluster_key"
           else QueryTooExpensive("scan too large"))
    app.dependency_overrides[get_repo] = lambda: _RaisingRepo(exc)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_events_repo_exceptions_become_400(raising_client):
    r = raising_client.get("/api/events", params={"date": DEMO_DATE, "keyword": "福岡"})
    assert r.status_code == 400


def test_event_detail_repo_exceptions_become_400(raising_client):
    r = raising_client.get("/api/events/sess-x", params={"date": DEMO_DATE})
    assert r.status_code == 400


def test_event_cf_repo_exceptions_become_400(raising_client):
    r = raising_client.get("/api/events/sess-x/cf", params={"date": DEMO_DATE})
    assert r.status_code == 400


class _RepoMissingProds:
    """EventRepo.get_event() 契約要求回傳 dict 必須含 "prods" key(見
    bigquery.EventRepo.get_event docstring)——這支 stub 故意漏掉,驗證
    event_detail 對這種情境的實際行為(2026-08-27 code review 抓到:
    這個「必須含 prods」的隱性契約完全沒有測試逼過,忘記塞的話會靜默
    回空清單,跟「這個事件真的沒有商品」無法區分)。"""

    def get_event(self, session_id, date, keyword=None, exp_version=None, locale=None):
        return {
            "session_id": session_id, "event_date": None, "event_type": "content",
            "cache_hit": False, "keyword": "測試詞", "normalized_keyword": "測試詞",
            "lang": "zh-tw", "locale": "tw", "currency": "TWD", "exp_version": "exp_a",
            "source": "web", "kkud": "kkud-x", "ip_masked": None,
            "page_start": 0, "page_count": 10, "total_count": 10, "prod_cnt": 10,
            "uf_intent": None, "uf_profile": None, "uf_profile_version": None,
            "uf_lbs": None, "cf_platform": None, "cf_hour": None, "cf_weekday": None,
            "cf_query_final": None, "cf_query_tokens": None,
            "join_failed": False, "uf_absent": False, "ltr_features_recovered": False,
            # 故意不帶 "prods" key
        }

    def get_cf_raw(self, *a, **kw):
        return None

    def get_prods(self, *a, **kw):
        return []

    def last_query_bytes(self):
        return 0


def test_event_detail_tolerates_repo_missing_prods_key():
    """記錄現況行為:回傳空商品列表 + 200,不是報錯。這是刻意接受的
    contract 缺口(見 EventRepo.get_event docstring)—— 這個測試存在的
    目的不是宣告這個行為理想,是確保有人改動時看得到「原本會靜默改變」。"""
    app.dependency_overrides[get_repo] = lambda: _RepoMissingProds()
    try:
        c = TestClient(app)
        r = c.get("/api/events/sess-x", params={"date": DEMO_DATE})
        assert r.status_code == 200
        assert r.json()["prods"] == []
    finally:
        app.dependency_overrides.clear()


def test_compare_repo_exceptions_become_400(raising_client):
    r = raising_client.get("/api/compare", params={
        "date": DEMO_DATE, "keyword": "福岡", "exp_a": "a", "exp_b": "b",
    })
    assert r.status_code == 400


def test_is_bytes_billed_limit_error_reads_structured_reason():
    """實測 (2026-08-27) google-api-core 對這個錯誤的真實形狀:
    InternalServerError.errors == [{'reason': 'bytesBilledLimitExceeded', ...}]。
    結構化欄位優先於字串比對(code review 抓到原本只做字串比對,SDK 措辭一變
    就會悄悄失效)。"""
    from src.repo.bigquery import _is_bytes_billed_limit_error

    class _FakeApiError(Exception):
        def __init__(self, errors):
            super().__init__("some wording that does not mention bytes at all")
            self.errors = errors

    hit = _FakeApiError([{"reason": "bytesBilledLimitExceeded", "message": "..."}])
    assert _is_bytes_billed_limit_error(hit) is True

    miss = _FakeApiError([{"reason": "invalidQuery", "message": "..."}])
    assert _is_bytes_billed_limit_error(miss) is False


def test_is_bytes_billed_limit_error_falls_back_to_string_match():
    """沒有 .errors 屬性(例如非 GoogleAPICallError 的一般例外)時,
    退回字串比對當備援,不要整個判斷失效。"""
    from src.repo.bigquery import _is_bytes_billed_limit_error

    assert _is_bytes_billed_limit_error(RuntimeError("Query exceeded limit for bytes billed")) is True
    assert _is_bytes_billed_limit_error(RuntimeError("connection reset")) is False


# ── 分區時間窗換算 (5.1) ──────────────────────────────────────────────────────

def test_local_date_to_utc_range_buffer():
    from src.repo.bigquery import local_date_to_utc_range
    start, end = local_date_to_utc_range("2026-08-13")
    # 本地日窗 [08-12 16:00Z, 08-13 16:00Z) 前後各展 8h
    assert start.isoformat() == "2026-08-12T08:00:00+00:00"
    assert end.isoformat() == "2026-08-14T00:00:00+00:00"


def test_point_queries_require_cluster_key():
    """detail 點查缺 keyword 直接丟 ClusterKeyRequired — 原始表無實體叢集,
    這條規則現在保的是正確性(鎖定唯一事件),不是省成本。"""
    from src.repo.bigquery import ClusterKeyRequired, build_detail_query, build_recall_query
    sql, params = build_detail_query("sess-x", DEMO_DATE,
                                     keyword="福岡", exp_version="exp_a", locale="tw")
    assert "JSON_VALUE(data, '$.query.keyword') = @keyword" in sql
    assert "event_id = @session_id" in sql
    assert params["keyword"] == "福岡"
    with pytest.raises(ClusterKeyRequired):
        build_detail_query("sess-x", DEMO_DATE)   # 缺 keyword → 不准出查詢
    # recall 回查:kkud + keyword 縮小範圍 + event_id 結果過濾
    sql2, _ = build_recall_query("recall-1", DEMO_DATE, kkud="k-1", keyword="福岡")
    assert "JSON_VALUE(data, '$.kkud') = @kkud" in sql2
    assert "JSON_VALUE(data, '$.query.keyword') = @keyword" in sql2
    assert "event_id = @event_id" in sql2 and "LIMIT 1" in sql2


def test_compare_respects_cache_hit_filter(client, repo):
    """compare 選 session 時必須尊重 cache_hit 條件 — fixture 的 control 是
    cache 事件,cache_hit=false 下 B 側應選不到任何 session。"""
    r = client.get("/api/compare", params={
        "date": DEMO_DATE, "keyword": "福岡",
        "exp_a": "exp_a", "exp_b": "exp_b", "cache_hit": "false",
    })
    assert r.status_code == 200
    body = r.json()
    # B 側 (cache 事件被濾掉) 全部變 only_a
    assert all(row["rank_b"] is None for row in body["rows"])
    assert all(row["verdict"] == "only_a" for row in body["rows"])


def test_prods_query_can_lock_session():
    """同天同 keyword+exp 可能多個 session — prod 查詢必須能鎖定單一事件;
    prods 是 content 列的 JSON 陣列,取單列由 parse_prods 展開。"""
    from src.repo.bigquery import build_prods_query, parse_prods
    sql, params = build_prods_query(DEMO_DATE, "福岡", None, "exp_a",
                                    session_id="sess-x")
    assert "event_id = @session_id" in sql
    assert "JSON_VALUE(data, '$.query.keyword') = @keyword" in sql and "prods" in sql
    assert params["session_id"] == "sess-x"
    # parse_prods:rank = pagination_start + offset + 1;payload 無商品名
    prods = parse_prods(
        '[{"prod_mid":"123","prod_oid":"123","is_ad":false,'
        '"ltr_score":110.5,"relevance_status_code":"000200"}]', 10)
    assert prods[0]["rank"] == 11 and prods[0]["prod_mid"] == "123"
    assert prods[0]["prod_name"] is None and prods[0]["in_rerank_scope"] is True
    assert parse_prods(None, 0) == [] and parse_prods("not json", 0) == []


def test_detail_prods_scoped_to_session(client, repo):
    body = client.get(
        "/api/events/sess-fukuoka-treatment", params={"date": DEMO_DATE}
    ).json()
    # FakeRepo 的 prod rows 都掛 session_id;detail 只能拿到本事件的
    assert len(body["prods"]) == 10


def test_list_returns_logged_in_not_member_uuid(client):
    rows = client.get(
        "/api/events", params={"date": DEMO_DATE, "keyword": "福岡"}
    ).json()["rows"]
    by_exp = {r["exp_version"]: r for r in rows}
    assert by_exp["exp_a"]["logged_in"] is True    # fixture 有 member_uuid
    assert by_exp["exp_b"]["logged_in"] is False
    assert all("member_uuid" not in r for r in rows)


def test_mask_ip_to_24():
    from src.repo.bigquery import mask_ip_to_24
    assert mask_ip_to_24("61.216.159.42") == "61.216.159.0/24"
    assert mask_ip_to_24("61.216.159.0/24") == "61.216.159.0/24"
    assert mask_ip_to_24("not-an-ip") is None
    assert mask_ip_to_24(None) is None
