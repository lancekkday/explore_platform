"""ui-spec §6.3/§6.4/§2.3 — 呈現層純函式。"""
from src.domain.presentation import band_gap, common_prefix_len, lamp_level, verdict_text


def test_verdict_text_states():
    assert verdict_text("identical", 3, 3, []) == "—"
    assert verdict_text("tie_unresolvable", 1, 2, []) == "同帶內位移"
    assert verdict_text("real_move", 1, 4, []) == "跨帶 ↓3"
    assert verdict_text("real_move", 5, 2, []) == "跨帶 ↑3"
    assert verdict_text("only_a", 6, None, []) == "僅 A"
    assert verdict_text("only_b", None, 9, []) == "僅 B"


def test_verdict_text_only_with_diff_dims():
    # ip 是第 4 位 → ④
    assert verdict_text("only_a", 6, None, ["ip"]) == "僅 A · ④ 差異"
    assert verdict_text("only_b", None, 9, ["location", "category"]) == "僅 B · ②③ 差異"


def test_lamp_level_mapping():
    assert lamp_level(0) == 0
    assert lamp_level(1) == 1
    assert lamp_level(3) == 3
    assert lamp_level(7) == 4     # ≥4 → 100%
    assert lamp_level(None) is None


def test_common_prefix_len():
    # '110.99' 共同 → 6
    assert common_prefix_len(["110.99751", "110.99677", "110.99650"]) == 6
    assert common_prefix_len(["110.99751", "110.99677"]) == 6
    assert common_prefix_len(["110.99751"]) == 0          # 單筆無共同前綴
    assert common_prefix_len([]) == 0
    assert common_prefix_len(["1.5", "2.5"]) == 0          # 首字即異


def test_band_gap():
    g = band_gap(110.99751, 110.99650)
    assert g["gap"] > 0 and g["ulp"] > 1
    assert band_gap(None, 1.0) is None
