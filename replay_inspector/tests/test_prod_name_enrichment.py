"""API 層商品名稱補值 — repo 沒填的 prod_name 由 name_lookup 補上,
已有名稱(demo fixture / flat 表未來若補資料)的不重查。
唯讀,dependency override 掉 name_lookup,不打真的 kkday.com。
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, get_product_name_lookup
from src.repo.bigquery import get_repo


class _StubRepo:
    """單一 session、prod_name 缺值的最小 repo — 不共用 fake.py 的既有 fixture,
    避免污染其他測試對 FakeEventRepo 命名固定內容的假設。"""

    def __init__(self, prods):
        self._prods = prods
        self.query_count = 0

    def list_events(self, date, filters):
        self.query_count += 1
        return []

    def get_event(self, session_id, date, keyword=None, exp_version=None, locale=None):
        self.query_count += 1
        if session_id != "sess-noname":
            return None
        return {
            "session_id": "sess-noname", "event_date": None, "event_type": "content",
            "cache_hit": False, "keyword": "測試詞", "normalized_keyword": "測試詞",
            "lang": "zh-tw", "locale": "tw", "currency": "TWD", "exp_version": "exp_a",
            "source": "web", "kkud": "kkud-x", "ip_masked": None,
            "page_start": 0, "page_count": 10, "total_count": 10, "prod_cnt": 10,
            "uf_intent": None, "uf_profile": None, "uf_profile_version": None,
            "uf_lbs": None, "cf_platform": None, "cf_hour": None, "cf_weekday": None,
            "cf_query_final": None, "cf_query_tokens": None,
            "join_failed": False, "uf_absent": False, "ltr_features_recovered": False,
        }

    def get_cf_raw(self, session_id, date, keyword=None, exp_version=None, locale=None):
        self.query_count += 1
        return None

    def get_prods(self, date, keyword, locale, exp_version, session_id=None):
        self.query_count += 1
        return [dict(p) for p in self._prods]


@pytest.fixture()
def name_lookup_mock():
    m = MagicMock()
    m.lookup_many.return_value = {"999001": "測試商品名稱"}
    return m


@pytest.fixture()
def client_with_stub(name_lookup_mock):
    repo = _StubRepo([
        {"session_id": "sess-noname", "rank": 1, "prod_mid": "999001", "prod_oid": "999001",
         "prod_name": None, "is_ad": False, "ltr_score": 111.0,
         "relevance_status_code": "000200", "in_rerank_scope": True},
    ])
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_product_name_lookup] = lambda: name_lookup_mock
    yield TestClient(app), name_lookup_mock
    app.dependency_overrides.clear()


def test_detail_fills_missing_prod_name_via_lookup(client_with_stub):
    client, mock = client_with_stub
    r = client.get("/api/events/sess-noname", params={"date": "2026-08-25"})
    assert r.status_code == 200
    body = r.json()
    assert body["prods"][0]["prod_name"] == "測試商品名稱"
    mock.lookup_many.assert_called_once_with(["999001"])


def test_detail_skips_lookup_when_name_already_present():
    repo = _StubRepo([
        {"session_id": "sess-noname", "rank": 1, "prod_mid": "999001", "prod_oid": "999001",
         "prod_name": "已經有名字", "is_ad": False, "ltr_score": 111.0,
         "relevance_status_code": "000200", "in_rerank_scope": True},
    ])
    mock = MagicMock()
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_product_name_lookup] = lambda: mock
    try:
        client = TestClient(app)
        r = client.get("/api/events/sess-noname", params={"date": "2026-08-25"})
        assert r.status_code == 200
        assert r.json()["prods"][0]["prod_name"] == "已經有名字"
        mock.lookup_many.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_detail_lookup_miss_leaves_name_none(client_with_stub):
    client, mock = client_with_stub
    mock.lookup_many.return_value = {"999001": None}
    r = client.get("/api/events/sess-noname", params={"date": "2026-08-25"})
    assert r.json()["prods"][0]["prod_name"] is None
