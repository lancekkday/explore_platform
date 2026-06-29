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


# ── 4. ab_check_runs DB schema persists lang/locale/channel ─────────────────

def test_ab_check_run_persists_locale_metadata(tmp_path, monkeypatch):
    """start_run 寫進 ab_check_runs 的 row 必須含 lang/locale/channel,
    讓歷史紀錄看得到、未來 resume 守門邏輯有資料可比對。"""
    import ab_check_runner
    import baseline_service

    # 切到隔離的 sqlite 檔案,不污染真實 history.db
    tmp_db = tmp_path / "history-test.db"
    monkeypatch.setattr(ab_check_runner, "DB_PATH", str(tmp_db))
    # 假 baseline:一個精準詞,避免 queue 為空導致沒 row 可看
    monkeypatch.setattr(
        baseline_service.baseline_service, "_precise",
        {"ramen": {"query": "ramen", "top1_prod_mid": 12345, "top2_prod_mid": None}},
    )
    monkeypatch.setattr(
        baseline_service.baseline_service, "_broad", {}
    )
    # 阻止 daemon thread 真的去打 API:start_run(sync=False) 仍會起 thread,
    # 但 process_one_precise_query 會被 patch 掉。
    monkeypatch.setattr(
        "ab_check.process_one_precise_query",
        lambda *a, **kw: [],
    )

    run_id = ab_check_runner.start_run(
        type_="precise", version_a=0, version_b=1, cookie="c",
        limit=1, sync=True,
        lang="ja", locale="jp", channel="android",
    )

    run = ab_check_runner.get_run(run_id)
    assert run is not None, "start_run 應寫進 DB"
    assert run["lang"] == "ja", f"lang 沒存進 DB (got {run.get('lang')!r})"
    assert run["locale"] == "jp", f"locale 沒存進 DB (got {run.get('locale')!r})"
    assert run["channel"] == "android", f"channel 沒存進 DB (got {run.get('channel')!r})"


def test_ab_check_run_default_locale_when_omitted(tmp_path, monkeypatch):
    """沒帶 lang/locale/channel 時,DB row 寫入預設值 zh-tw / tw / ios。"""
    import ab_check_runner
    import baseline_service

    tmp_db = tmp_path / "history-test-default.db"
    monkeypatch.setattr(ab_check_runner, "DB_PATH", str(tmp_db))
    monkeypatch.setattr(
        baseline_service.baseline_service, "_precise",
        {"ramen": {"query": "ramen", "top1_prod_mid": 12345, "top2_prod_mid": None}},
    )
    monkeypatch.setattr(
        baseline_service.baseline_service, "_broad", {}
    )
    monkeypatch.setattr(
        "ab_check.process_one_precise_query",
        lambda *a, **kw: [],
    )

    run_id = ab_check_runner.start_run(
        type_="precise", version_a=0, version_b=1, cookie="c",
        limit=1, sync=True,
    )

    run = ab_check_runner.get_run(run_id)
    assert run["lang"] == "zh-tw"
    assert run["locale"] == "tw"
    assert run["channel"] == "ios"


def test_resume_inherits_parent_locale(tmp_path, monkeypatch):
    """續跑時 start_run 必須無視 caller 傳入的 lang/locale/channel,改用 parent 的。
    這條 run 的 locale 在第一次起跑就釘住,換 locale 等於開新 run。"""
    import ab_check_runner
    import baseline_service

    tmp_db = tmp_path / "history-test-resume.db"
    monkeypatch.setattr(ab_check_runner, "DB_PATH", str(tmp_db))
    monkeypatch.setattr(
        baseline_service.baseline_service, "_precise",
        {"ramen": {"query": "ramen", "top1_prod_mid": 12345, "top2_prod_mid": None}},
    )
    monkeypatch.setattr(
        baseline_service.baseline_service, "_broad", {}
    )
    monkeypatch.setattr(
        "ab_check.process_one_precise_query",
        lambda *a, **kw: [],
    )

    # Parent run with lang=zh-tw
    parent_id = ab_check_runner.start_run(
        type_="precise", version_a=0, version_b=1, cookie="c",
        limit=1, sync=True,
        lang="zh-tw", locale="tw", channel="ios",
    )
    parent = ab_check_runner.get_run(parent_id)
    assert parent["lang"] == "zh-tw"

    # 使用者下拉切到 ja/jp/android 後點「續跑」— caller 帶 ja,但 parent 是 zh-tw
    resume_id = ab_check_runner.start_run(
        type_="precise", version_a=0, version_b=1, cookie="c",
        limit=1, sync=True,
        resume_run_id=parent_id,
        lang="ja", locale="jp", channel="android",
    )

    resumed = ab_check_runner.get_run(resume_id)
    assert resumed["lang"] == "zh-tw", "resume 必須無視 caller 的 ja,沿用 parent 的 zh-tw"
    assert resumed["locale"] == "tw"
    assert resumed["channel"] == "ios"
    assert resumed["parent_run_id"] == parent_id
