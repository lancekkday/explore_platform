"""
巡檢核心邏輯單元測試
====================

不需要打真實 API,測試:
  - find_rank
  - check_ab_precise / check_ab_broad
  - check_a_health_precise / check_a_health_broad

跑法:
  pytest tests/test_check_logic.py -v
"""
from scripts.keyword_ab_check import (
    find_rank,
    check_ab_precise,
    check_ab_broad,
    check_a_health_precise,
    check_a_health_broad,
)


# ============================================================
# find_rank
# ============================================================
def test_find_rank_present():
    assert find_rank(123, (100, 123, 456)) == 2


def test_find_rank_first():
    assert find_rank(100, (100, 200, 300)) == 1


def test_find_rank_missing():
    assert find_rank(999, (100, 200, 300)) is None


def test_find_rank_empty():
    assert find_rank(123, ()) is None


# ============================================================
# 精準詞主告警
# ============================================================
def test_precise_a_missing_skips():
    """A 版本身找不到該商品 → 不算 B 的鍋,跳過"""
    assert check_ab_precise("query", 123, 1, a_rank=None, b_rank=5) is None


def test_precise_b_disappeared_top1_p0():
    alert = check_ab_precise("新幹線", 6681, 1, a_rank=1, b_rank=None)
    assert alert is not None
    assert alert.severity == "P0"
    assert "完全消失" in alert.reason


def test_precise_b_disappeared_top2_p1():
    alert = check_ab_precise("新幹線", 12345, 2, a_rank=2, b_rank=None)
    assert alert is not None
    assert alert.severity == "P1"


def test_precise_dropped_within_threshold():
    """掉 5 名 → 還可接受,不告警"""
    assert check_ab_precise("query", 123, 1, a_rank=1, b_rank=6) is None


def test_precise_dropped_over_threshold_top1_p1():
    """Top1 掉 6 名 → P1"""
    alert = check_ab_precise("query", 123, 1, a_rank=1, b_rank=7)
    assert alert is not None
    assert alert.severity == "P1"
    assert "掉 6 名" in alert.reason


def test_precise_dropped_over_threshold_top2_p2():
    alert = check_ab_precise("query", 123, 2, a_rank=2, b_rank=8)
    assert alert is not None
    assert alert.severity == "P2"


def test_precise_b_above_a_no_alert():
    """B 版排到更前面 → 不告警(精準詞 only 看下降)"""
    assert check_ab_precise("query", 123, 1, a_rank=5, b_rank=1) is None


# ============================================================
# 泛詞主告警
# ============================================================
def test_broad_a_missing_skips():
    assert check_ab_broad("query", 123, 1, a_rank=None, b_rank=10) is None


def test_broad_b_disappeared_top3_p1():
    alert = check_ab_broad("大阪", 2247, 1, a_rank=1, b_rank=None)
    assert alert is not None
    assert alert.severity == "P1"


def test_broad_b_disappeared_long_tail_p2():
    alert = check_ab_broad("大阪", 999, 8, a_rank=8, b_rank=None)
    assert alert is not None
    assert alert.severity == "P2"


def test_broad_within_threshold():
    """位置變動 5 名以內 → 不告警"""
    assert check_ab_broad("query", 123, 1, a_rank=1, b_rank=6) is None


def test_broad_dropped_over_threshold():
    alert = check_ab_broad("query", 123, 1, a_rank=1, b_rank=7)
    assert alert is not None
    assert alert.severity == "P1"
    assert "下降" in alert.reason


def test_broad_jumped_up_also_alerts():
    """雙向告警 — 大幅上升也告警"""
    alert = check_ab_broad("query", 123, 1, a_rank=10, b_rank=2)
    assert alert is not None
    assert "上升" in alert.reason


def test_broad_long_tail_severity_p2():
    """profit_rank ≥ 4 → P2"""
    alert = check_ab_broad("query", 123, 5, a_rank=5, b_rank=15)
    assert alert is not None
    assert alert.severity == "P2"


# ============================================================
# A 版穩定性旁路告警
# ============================================================
def test_side_precise_top1_a_missing():
    alert = check_a_health_precise("query", 123, 1, a_rank=None)
    assert alert is not None
    assert alert.severity == "INFO"
    assert alert.alert_type == "side"


def test_side_precise_top1_a_at_position_5_ok():
    """Top1 在 A 版第 5 位 → 還算正常"""
    assert check_a_health_precise("query", 123, 1, a_rank=5) is None


def test_side_precise_top1_a_too_far():
    """Top1 在 A 版第 11 位 → A 版可能不穩"""
    alert = check_a_health_precise("query", 123, 1, a_rank=11)
    assert alert is not None
    assert alert.severity == "INFO"


def test_side_precise_top2_threshold_higher():
    """Top2 閾值是 15"""
    assert check_a_health_precise("query", 123, 2, a_rank=14) is None
    alert = check_a_health_precise("query", 123, 2, a_rank=16)
    assert alert is not None


def test_side_broad_top1_a_missing():
    alert = check_a_health_broad("query", 123, 1, a_rank=None)
    assert alert is not None
    assert alert.severity == "INFO"


def test_side_broad_long_tail_a_missing_no_alert():
    """profit_rank ≥ 4 + A 版找不到 → 不告警(長尾本來就容易飄)"""
    assert check_a_health_broad("query", 123, 5, a_rank=None) is None


def test_side_broad_within_delta():
    """偏離 ≤ 20 名 → 不告警"""
    assert check_a_health_broad("query", 123, 1, a_rank=15) is None


def test_side_broad_over_delta():
    alert = check_a_health_broad("query", 123, 1, a_rank=25)
    assert alert is not None
    assert alert.severity == "INFO"
