"""
平台驗收 — lang / locale / channel API 欄位的接通測試
===========================================================

驗證點:
1. fetch_kkday_products_v3 把 lang/locale/channel 寫進 v3 search API request body
2. /api/unified-search 接受新欄位且傳遞到 fetch 層
3. /api/ab-check/start 接受新欄位
4. CompareRequest / UnifiedSearchRequest / ABCheckRequest / ABCheckStartRequest
   / BatchRunRequest 都帶上預設值 (zh-tw / tw / ios) 以兼容舊呼叫

走 FastAPI TestClient + monkeypatch fetch_kkday_products_v3,完全不打外網。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# 確保 import 從 backend 目錄走
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kkday_api
import main


# ── 1. fetch_kkday_products_v3:lang/locale/channel 落到 request body ────────

def test_v3_body_carries_new_fields():
    """fetch_kkday_products_v3 必須把 lang/locale/channel 寫進 v3 search API body。"""
    captured_body = {}

    def fake_get(url, headers=None, json=None, timeout=None):
        captured_body.update(json or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"prods": []},
            "metadata": {"pagination": {"total_count": 0}},
        }
        return mock_resp

    with patch("kkday_api.requests.get", side_effect=fake_get):
        kkday_api.fetch_kkday_products_v3(
            keyword="test", env="stage", cookie="dummy", row_count=10,
            test_exp=3, lang="ja", locale="jp", channel="android",
        )

    assert captured_body["lang"] == "ja"
    assert captured_body["locale"] == "jp"
    assert captured_body["channel"] == "android"
    assert captured_body["source"] == "android", "source 應跟 channel 同步"


def test_v3_body_defaults_match_legacy():
    """不帶新參數時,body 應退回原本 zh-tw / tw / ios 行為。"""
    captured_body = {}

    def fake_get(url, headers=None, json=None, timeout=None):
        captured_body.update(json or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"prods": []},
            "metadata": {"pagination": {"total_count": 0}},
        }
        return mock_resp

    with patch("kkday_api.requests.get", side_effect=fake_get):
        kkday_api.fetch_kkday_products_v3(
            keyword="test", env="stage", cookie="dummy", row_count=10, test_exp=3,
        )

    assert captured_body["lang"] == "zh-tw"
    assert captured_body["locale"] == "tw"
    assert captured_body["channel"] == "ios"
    assert captured_body["source"] == "ios"


# ── 2. /api/unified-search 把新欄位傳到 fetch_fn ───────────────────────────────

@pytest.fixture
def client():
    return TestClient(main.app)


def test_unified_search_forwards_new_fields(client, monkeypatch):
    """/api/unified-search lang/locale/channel 必須傳到 fetch_kkday_products_v3。"""
    captured = []

    def fake_fetch_v3(**kwargs):
        captured.append(kwargs)
        return ([], 0, 0)

    monkeypatch.setattr(main, "fetch_kkday_products_v3", fake_fetch_v3)
    # 旁路掉 baseline / judger,只在意 fetch 層收到什麼
    monkeypatch.setattr(main.baseline_service, "get_baseline",
                        lambda kw: {"has_data": False, "broad_products": []})
    monkeypatch.setattr(main.baseline_service, "annotate_products",
                        lambda kw, res: None)
    monkeypatch.setattr(main.baseline_service, "find_baseline_alerts",
                        lambda kw, res: [])
    monkeypatch.setattr(main.judger, "get_ai_metadata", lambda kw, ai_enabled: {})

    resp = client.post("/api/unified-search", json={
        "keyword": "ramen", "cookie": "c", "count": 5,
        "search_api": "v3", "version_a": 0, "version_b": None,
        "lang": "ja", "locale": "jp", "channel": "android",
    })
    assert resp.status_code == 200, resp.text
    assert captured, "fetch_kkday_products_v3 must be invoked"
    assert captured[0]["lang"] == "ja"
    assert captured[0]["locale"] == "jp"
    assert captured[0]["channel"] == "android"


def test_unified_search_omitted_fields_default(client, monkeypatch):
    """前端漏帶這些欄位時,要 fallback 到 zh-tw / tw / ios。"""
    captured = []

    def fake_fetch_v3(**kwargs):
        captured.append(kwargs)
        return ([], 0, 0)

    monkeypatch.setattr(main, "fetch_kkday_products_v3", fake_fetch_v3)
    monkeypatch.setattr(main.baseline_service, "get_baseline",
                        lambda kw: {"has_data": False, "broad_products": []})
    monkeypatch.setattr(main.baseline_service, "annotate_products",
                        lambda kw, res: None)
    monkeypatch.setattr(main.baseline_service, "find_baseline_alerts",
                        lambda kw, res: [])
    monkeypatch.setattr(main.judger, "get_ai_metadata", lambda kw, ai_enabled: {})

    resp = client.post("/api/unified-search", json={
        "keyword": "esim", "cookie": "c", "count": 5,
        "search_api": "v3", "version_a": 0,
    })
    assert resp.status_code == 200, resp.text
    assert captured[0]["lang"] == "zh-tw"
    assert captured[0]["locale"] == "tw"
    assert captured[0]["channel"] == "ios"


# ── 3. /api/ab-check/start 接受新欄位 ─────────────────────────────────────────

def test_ab_check_start_accepts_new_fields(client, monkeypatch):
    """/api/ab-check/start 必須接受新欄位並把它們塞進 start_run。"""
    captured = []

    def fake_start_run(**kwargs):
        captured.append(kwargs)
        return "run-id-abc"

    fake_run = {"status": "running", "total_queries": 0}
    monkeypatch.setattr(main.ab_check_runner, "start_run", fake_start_run)
    monkeypatch.setattr(main.ab_check_runner, "get_run", lambda _rid: fake_run)

    resp = client.post("/api/ab-check/start", json={
        "type": "precise", "version_a": 0, "version_b": 1, "cookie": "c",
        "lang": "en", "locale": "us", "channel": "web",
    })
    assert resp.status_code == 200, resp.text
    assert captured[0]["lang"] == "en"
    assert captured[0]["locale"] == "us"
    assert captured[0]["channel"] == "web"
