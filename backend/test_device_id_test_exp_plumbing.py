"""
平台驗收 — device_id 參數化 + test_exp 10 碼(字串)化的接通測試
================================================================

驗證點:
1. fetch_kkday_products_v3 把 device_id 寫進 v3 body;未帶時 fallback 預設值
2. test_exp 一律以字串送出,前導零不被吃掉;舊呼叫端帶 int 也相容
3. /api/unified-search 把 device_id + 字串 version 傳到 fetch 層
4. /api/ab-check/start 把 device_id 傳進 start_run;int version 被 coerce 成 str
5. ab_check_runs DB 以 TEXT 存 version(前導零保留)並存 device_id
6. resume 沿用 parent 的 device_id(無視 caller 傳入值)

走 FastAPI TestClient + monkeypatch,完全不打外網。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# 確保 import 從 backend 目錄走
sys.path.insert(0, str(Path(__file__).resolve().parent))

import kkday_api
import main


def _fake_get_factory(captured_body):
    def fake_get(url, headers=None, json=None, timeout=None):
        captured_body.update(json or {})
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": {"prods": []},
            "metadata": {"pagination": {"total_count": 0}},
        }
        return mock_resp
    return fake_get


# ── 1+2. fetch_kkday_products_v3:device_id / test_exp 落到 request body ──────

def test_v3_body_carries_device_id():
    captured_body = {}
    with patch("kkday_api.requests.get", side_effect=_fake_get_factory(captured_body)):
        kkday_api.fetch_kkday_products_v3(
            keyword="test", env="stage", cookie="dummy", row_count=10,
            test_exp="3", device_id="my-custom-device",
        )
    assert captured_body["device_id"] == "my-custom-device"


def test_v3_body_device_id_falls_back_to_default():
    """device_id 未帶 / 空字串時,fallback 到 DEFAULT_DEVICE_ID(舊行為)。"""
    for missing in (None, ""):
        captured_body = {}
        with patch("kkday_api.requests.get", side_effect=_fake_get_factory(captured_body)):
            kkday_api.fetch_kkday_products_v3(
                keyword="test", env="stage", cookie="dummy", row_count=10,
                test_exp="3", device_id=missing,
            )
        assert captured_body["device_id"] == kkday_api.DEFAULT_DEVICE_ID


def test_v3_body_test_exp_string_keeps_leading_zeros():
    """10 碼 test_exp 可能有前導零 — body 必須原樣送出字串。"""
    captured_body = {}
    with patch("kkday_api.requests.get", side_effect=_fake_get_factory(captured_body)):
        kkday_api.fetch_kkday_products_v3(
            keyword="test", env="stage", cookie="dummy", row_count=10,
            test_exp="0000000001",
        )
    assert captured_body["test_exp"] == "0000000001"


def test_v3_body_test_exp_int_coerced_to_str():
    """舊呼叫端帶 int 時轉成字串送出(相容)。"""
    captured_body = {}
    with patch("kkday_api.requests.get", side_effect=_fake_get_factory(captured_body)):
        kkday_api.fetch_kkday_products_v3(
            keyword="test", env="stage", cookie="dummy", row_count=10,
            test_exp=3,
        )
    assert captured_body["test_exp"] == "3"


# ── 3. /api/unified-search 把 device_id + 字串 version 傳到 fetch_fn ──────────

@pytest.fixture
def client():
    return TestClient(main.app)


def _bypass_pipeline(monkeypatch, captured):
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


def test_unified_search_forwards_device_id_and_str_version(client, monkeypatch):
    captured = []
    _bypass_pipeline(monkeypatch, captured)

    resp = client.post("/api/unified-search", json={
        "keyword": "ramen", "cookie": "c", "count": 5,
        "search_api": "v3", "version_a": "0000000001", "version_b": None,
        "device_id": "dev-xyz",
    })
    assert resp.status_code == 200, resp.text
    assert captured[0]["test_exp"] == "0000000001", "前導零不可弄丟"
    assert captured[0]["device_id"] == "dev-xyz"
    # response echo 也要是原字串
    assert resp.json()["version_a"]["test_exp"] == "0000000001"


def test_unified_search_int_version_still_accepted(client, monkeypatch):
    """舊 client 送 int version 時,Pydantic BeforeValidator 應 coerce 成 str。"""
    captured = []
    _bypass_pipeline(monkeypatch, captured)

    resp = client.post("/api/unified-search", json={
        "keyword": "esim", "cookie": "c", "count": 5,
        "search_api": "v3", "version_a": 0,
    })
    assert resp.status_code == 200, resp.text
    assert captured[0]["test_exp"] == "0"
    assert captured[0]["device_id"] is None, "未帶 device_id 時應為 None(後端 fallback)"


# ── 4. /api/ab-check/start 傳遞 device_id ─────────────────────────────────────

def test_ab_check_start_forwards_device_id(client, monkeypatch):
    captured = []

    def fake_start_run(**kwargs):
        captured.append(kwargs)
        return "run-id-abc"

    fake_run = {"status": "running", "total_queries": 0}
    monkeypatch.setattr(main.ab_check_runner, "start_run", fake_start_run)
    monkeypatch.setattr(main.ab_check_runner, "get_run", lambda _rid: fake_run)

    resp = client.post("/api/ab-check/start", json={
        "type": "precise", "version_a": "0000000001", "version_b": 1,
        "cookie": "c", "device_id": "dev-abc",
    })
    assert resp.status_code == 200, resp.text
    assert captured[0]["version_a"] == "0000000001"
    assert captured[0]["version_b"] == "1", "int 應被 coerce 成 str"
    assert captured[0]["device_id"] == "dev-abc"


# ── 5+6. DB persist + resume 沿用 ─────────────────────────────────────────────

def _isolated_runner(tmp_path, monkeypatch, db_name):
    import ab_check_runner
    import baseline_service

    monkeypatch.setattr(ab_check_runner, "DB_PATH", str(tmp_path / db_name))
    monkeypatch.setattr(
        baseline_service.baseline_service, "_precise",
        {"ramen": {"query": "ramen", "top1_prod_mid": 12345, "top2_prod_mid": None}},
    )
    monkeypatch.setattr(baseline_service.baseline_service, "_broad", {})
    monkeypatch.setattr("ab_check.process_one_precise_query", lambda *a, **kw: [])
    return ab_check_runner


def test_run_persists_str_versions_and_device_id(tmp_path, monkeypatch):
    runner = _isolated_runner(tmp_path, monkeypatch, "hist-devid.db")

    run_id = runner.start_run(
        type_="precise", version_a="0000000001", version_b="1234567890",
        cookie="c", limit=1, sync=True, device_id="dev-abc",
    )
    run = runner.get_run(run_id)
    assert run["version_a"] == "0000000001", f"前導零不可弄丟 (got {run['version_a']!r})"
    assert run["version_b"] == "1234567890"
    assert run["device_id"] == "dev-abc"


def test_run_empty_device_id_stored_as_null(tmp_path, monkeypatch):
    """device_id 空字串視同未指定 → DB 存 NULL = 用後端預設。"""
    runner = _isolated_runner(tmp_path, monkeypatch, "hist-devid-null.db")

    run_id = runner.start_run(
        type_="precise", version_a="0", version_b="1",
        cookie="c", limit=1, sync=True, device_id="",
    )
    assert runner.get_run(run_id)["device_id"] is None


def test_resume_inherits_parent_device_id(tmp_path, monkeypatch):
    """續跑必須沿用 parent 的 device_id — 個性化結果跟 device 綁定,
    跨 device 混合 ok rows 跟跨 locale 混合是同一種錯。"""
    runner = _isolated_runner(tmp_path, monkeypatch, "hist-devid-resume.db")

    parent_id = runner.start_run(
        type_="precise", version_a="0", version_b="1",
        cookie="c", limit=1, sync=True, device_id="dev-parent",
    )
    resume_id = runner.start_run(
        type_="precise", version_a="0", version_b="1",
        cookie="c", limit=1, sync=True,
        resume_run_id=parent_id, device_id="dev-other",
    )
    resumed = runner.get_run(resume_id)
    assert resumed["device_id"] == "dev-parent", "resume 必須無視 caller 的 device_id,沿用 parent"
    assert resumed["parent_run_id"] == parent_id


def test_init_schema_migrates_int_versions_with_backup(tmp_path, monkeypatch):
    """舊 INTEGER schema → init_schema() 自動 rebuild 成 TEXT:
    - 舊 rows CAST 保留、前導零之後存得住
    - rebuild 前先寫檔案級備份 history.db.pre-text-migration.bak(單向 DROP 的保險)
    - idempotent:再跑一次不動備份、不再 rebuild"""
    import sqlite3
    import ab_check_runner as runner

    tmp_db = tmp_path / "hist-mig.db"
    monkeypatch.setattr(runner, "DB_PATH", str(tmp_db))

    # 建「舊版」schema(INTEGER version,無 device_id / lang / locale / channel)
    conn = sqlite3.connect(tmp_db)
    conn.executescript("""
        CREATE TABLE ab_check_runs (
          run_id TEXT PRIMARY KEY, type TEXT NOT NULL, status TEXT NOT NULL,
          version_a INTEGER NOT NULL, version_b INTEGER NOT NULL,
          limit_n INTEGER, total_queries INTEGER NOT NULL, done_count INTEGER DEFAULT 0,
          baseline_version TEXT NOT NULL, error_msg TEXT, started_at TEXT NOT NULL,
          finished_at TEXT, summary_json TEXT, parent_run_id TEXT
        );
        INSERT INTO ab_check_runs (run_id,type,status,version_a,version_b,total_queries,baseline_version,started_at)
        VALUES ('old1','precise','done',0,1,10,'bl-x','2026-01-01T00:00:00');
    """)
    conn.commit()
    conn.close()

    runner.init_schema()

    # 備份檔存在且含舊 row(INTEGER 原樣)
    bak_path = f"{runner.DB_PATH}.pre-text-migration.bak"
    assert os.path.exists(bak_path), "rebuild 前必須寫檔案級備份"
    with sqlite3.connect(bak_path) as bak:
        assert bak.execute("SELECT version_a FROM ab_check_runs WHERE run_id='old1'").fetchone() == (0,)
    bak.close()

    # 主 DB:TEXT affinity + 舊 row 轉字串保留 + 舊表已 DROP
    with sqlite3.connect(tmp_db) as conn:
        cols = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(ab_check_runs)")}
        assert cols["version_a"] == "TEXT" and cols["version_b"] == "TEXT"
        assert "device_id" in cols
        assert conn.execute("SELECT version_a, version_b FROM ab_check_runs WHERE run_id='old1'").fetchone() == ("0", "1")
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='ab_check_runs_int_ver'").fetchone()
    conn.close()

    # idempotent:再跑一次不炸,備份不被覆寫
    mtime = os.path.getmtime(bak_path)
    runner.init_schema()
    assert os.path.getmtime(bak_path) == mtime, "備份是一次性的,不可被後續啟動覆寫"


def test_resume_copies_parent_rows_across_int_str_versions(tmp_path, monkeypatch):
    """TEXT 遷移前的舊 run(int version)續跑新 code(str version)時,
    _copy_parent_done_rows 的 A/B 比對要 str-normalize,不可誤判成跨版本。"""
    import sqlite3
    runner = _isolated_runner(tmp_path, monkeypatch, "hist-intstr-resume.db")

    parent_id = runner.start_run(
        type_="precise", version_a="0", version_b="1",
        cookie="c", limit=1, sync=True,
    )
    # 模擬舊 DB:把 parent 的 version 改回 int 存法
    with sqlite3.connect(runner.DB_PATH) as conn:
        conn.execute("UPDATE ab_check_runs SET version_a=0, version_b=1 WHERE run_id=?", (parent_id,))

    resume_id = runner.start_run(
        type_="precise", version_a="0", version_b="1",
        cookie="c", limit=1, sync=True, resume_run_id=parent_id,
    )
    resumed = runner.get_run(resume_id)
    # parent 全部跑完(1/1 ok),resume 應複製 → done_count 直接 = 1
    assert resumed["done_count"] == 1, "int/str 版本比對誤判 → parent ok rows 沒被複製"
