"""
baseline_service.find_baseline_alerts 4-level status 單元測試
mock 掉 stage_checker.check_many,以確保測試不打網路、結果穩定。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from baseline_service import BaselineService


@pytest.fixture
def svc(tmp_path):
    """建一個 in-memory BaselineService,直接塞已知 baseline 進去,
    避開讀真正 CSV (避免測試耦合到當前資料)。"""
    s = BaselineService.__new__(BaselineService)  # bypass __init__
    s._precise = {
        "ktx": {
            "top1_prod_mid": 11111,
            "top1_prod_nm": "ktx top1",
            "top2_prod_mid": 22222,
            "top2_prod_nm": "ktx top2",
        },
    }
    s._broad = {
        "esim": [
            {"prod_mid": 33333, "prod_nm": "esim a", "profit_rank": 1, "profit": 100, "ctr": 1.0},
            {"prod_mid": 44444, "prod_nm": "esim b", "profit_rank": 2, "profit": 90, "ctr": 0.9},
        ],
    }
    return s


def _by_mid(alerts):
    return {a["prod_mid"]: a for a in alerts}


def test_all_present_no_stage_check(svc):
    """所有 baseline 商品都在前 300 內 → 不該呼叫 stage_checker"""
    products = [
        {"prod_mid": 11111, "rank": 1},
        {"prod_mid": 22222, "rank": 2},
    ]
    with patch("baseline_service.stage_checker.check_many") as m:
        alerts = svc.find_baseline_alerts("ktx", products)
    m.assert_not_called()
    by = _by_mid(alerts)
    assert by[11111]["status"] == "present"
    assert by[22222]["status"] == "present"
    assert by[11111]["stage_status"] is None  # 在前 300 內就不需要 stage


def test_rank_drop_within_window(svc):
    """top1 期望排名 1,實際 rank=10 (> 1×3=3) → rank_drop,不需 stage 檢查"""
    products = [
        {"prod_mid": 11111, "rank": 10},
        {"prod_mid": 22222, "rank": 2},
    ]
    with patch("baseline_service.stage_checker.check_many") as m:
        alerts = svc.find_baseline_alerts("ktx", products)
    m.assert_not_called()
    by = _by_mid(alerts)
    assert by[11111]["status"] == "rank_drop"
    assert by[11111]["stage_status"] is None


def test_absent_classified_by_stage(svc):
    """缺席商品的 status 由 stage_checker 決定"""
    products = []  # 都不在
    with patch(
        "baseline_service.stage_checker.check_many",
        return_value={11111: "removed", 22222: "exists"},
    ) as m:
        alerts = svc.find_baseline_alerts("ktx", products)
    m.assert_called_once_with([11111, 22222])
    by = _by_mid(alerts)
    assert by[11111]["status"] == "removed"
    assert by[11111]["stage_status"] == "removed"
    assert by[22222]["status"] == "out_of_window"
    assert by[22222]["stage_status"] == "exists"


def test_check_failed_fallback(svc):
    """stage_checker 沒回某個 mid (或回 check_failed) → status='check_failed'"""
    products = []
    with patch(
        "baseline_service.stage_checker.check_many",
        return_value={11111: "check_failed"},
    ):
        alerts = svc.find_baseline_alerts("ktx", products)
    by = _by_mid(alerts)
    assert by[11111]["status"] == "check_failed"
    assert by[22222]["status"] == "check_failed"  # 沒回的 mid 也視為 check_failed
    assert by[11111]["stage_status"] == "check_failed"


def test_broad_mixed(svc):
    """泛詞 baseline 兩支:一支在前 300 內(present)、一支下架(removed)"""
    products = [
        {"prod_mid": 33333, "rank": 2},
    ]
    with patch(
        "baseline_service.stage_checker.check_many",
        return_value={44444: "removed"},
    ) as m:
        alerts = svc.find_baseline_alerts("esim", products)
    m.assert_called_once_with([44444])
    by = _by_mid(alerts)
    assert by[33333]["status"] == "present"
    assert by[44444]["status"] == "removed"


def test_no_baseline_data_empty(svc):
    """非 baseline 的 keyword 不報任何 alert"""
    alerts = svc.find_baseline_alerts("沒這個 keyword", [])
    assert alerts == []
