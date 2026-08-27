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


# ── 驗收 1:成本紅線 guard ────────────────────────────────────────────────────

def test_raw_table_guard():
    from src.repo.bigquery import assert_no_raw_table
    # 新名 (2026-08-19 更正:dw_analysis_record.stream_search_record)
    with pytest.raises(RuntimeError):
        assert_no_raw_table("SELECT * FROM `kkday-data-dap.dw_analysis_record.stream_search_record`")
    # 舊文件用名也擋 (spec 早期版本寫 dl_base.ar-stream_search_record)
    with pytest.raises(RuntimeError):
        assert_no_raw_table("SELECT * FROM `kkday-data-dap.dl_base.ar-stream_search_record`")
    with pytest.raises(RuntimeError):
        assert_no_raw_table("select data from dl_base.ar_stream_search_record")
    # 自家落表在同 dataset,表名不含 stream — 不得誤傷
    assert_no_raw_table("SELECT 1 FROM `kkday-data-dap.dw_analysis_record.search_event_daily`")


def test_no_source_file_references_raw_table():
    """驗收 1 的靜態面:src/ 與 app/ 不得出現原表名(sql/ 的 dataform 除外)。"""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for folder in ("src", "app"):
        for p in (root / folder).rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            # 拿掉 guard 自己的 pattern 定義與註解列
            for line in text.splitlines():
                stripped = line.strip()
                if (stripped.startswith("#") or "_RAW_TABLE_PATTERN" in line
                        or "cost guard" in line):
                    continue
                if "stream_search_record_flat" in line:
                    continue   # flat 中繼表是平台的合法資料源
                if ("ar-stream_search_record" in line or "ar_stream_search_record" in line
                        or "stream_search_record" in line):
                    offenders.append(f"{p}: {stripped[:80]}")
    assert not offenders, offenders


# ── 分區時間窗換算 (5.1) ──────────────────────────────────────────────────────

def test_local_date_to_utc_range_buffer():
    from src.repo.bigquery import local_date_to_utc_range
    start, end = local_date_to_utc_range("2026-08-13")
    # 本地日窗 [08-12 16:00Z, 08-13 16:00Z) 前後各展 8h
    assert start.isoformat() == "2026-08-12T08:00:00+00:00"
    assert end.isoformat() == "2026-08-14T00:00:00+00:00"


def test_point_queries_require_cluster_key():
    """flat 表叢集鍵 (event_type, kkud, query_keyword):detail 點查缺 keyword
    直接丟 ClusterKeyRequired — event_id-only 會掃全天分區 (實測 21GB)。"""
    from src.repo.bigquery import ClusterKeyRequired, build_detail_query, build_recall_query
    sql, params = build_detail_query("sess-x", DEMO_DATE,
                                     keyword="福岡", exp_version="exp_a", locale="tw")
    assert "query_keyword = @keyword" in sql and "event_id = @session_id" in sql
    assert params["keyword"] == "福岡"
    with pytest.raises(ClusterKeyRequired):
        build_detail_query("sess-x", DEMO_DATE)   # 缺 keyword → 不准出查詢
    # recall 回查:kkud + keyword 雙叢集鍵 + event_id 結果過濾 (實測 10.5MB)
    sql2, _ = build_recall_query("recall-1", DEMO_DATE, kkud="k-1", keyword="福岡")
    assert "kkud = @kkud" in sql2 and "query_keyword = @keyword" in sql2
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


def test_raw_stream_blocked_flat_allowed():
    """紅線:原始事件流 (無 _flat) 一律擋;stream_search_record_flat 是
    合法叢集中繼表放行。(2026-08 教訓:原始流 per-path 計費 = path × 分區,
    「單筆」回查實測 14~36GB。)"""
    from src.repo.bigquery import assert_no_raw_table
    with pytest.raises(RuntimeError):
        assert_no_raw_table(
            "SELECT keyword FROM `kkday-data-dap.dw_analysis_record.stream_search_record`")
    with pytest.raises(RuntimeError):
        assert_no_raw_table("SELECT * FROM `kkday-data-dap.dl_base.ar-stream_search_record`")
    assert_no_raw_table(
        "SELECT 1 FROM `kkday-data-dap.dw_analysis_record.stream_search_record_flat`")


def test_prods_query_can_lock_session():
    """同天同 keyword+exp 可能多個 session — prod 查詢必須能鎖定單一事件;
    prods 是 content 列的 JSON 欄,取單列由 parse_prods 展開。"""
    from src.repo.bigquery import build_prods_query, parse_prods
    sql, params = build_prods_query(DEMO_DATE, "福岡", None, "exp_a",
                                    session_id="sess-x")
    assert "event_id = @session_id" in sql
    assert "query_keyword = @keyword" in sql and "prods" in sql
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
