"""spec 4.2 — 同分帶 (tie band),float32 ULP 邊界。

驗收條件 8:含 float32 邊界案例。
"""
import numpy as np

from src.domain.tie_band import TIE_ULP_THRESHOLD, assign_tie_bands, dispersion_stats

# spec 4.2 實測:福岡前十筆全落在 110.99571 ~ 110.99751 量級,相鄰差 7~15 ULP。
# 用 ULP 精確建構(而非手抄近似值),讓「哪些相鄰對落在 threshold=10 之內」可控:
# 8 ULP 的對同帶、14 ULP 的對分帶。
_BASE = 110.99571
_ULP = float(np.spacing(np.float32(_BASE)))
_GAPS_ULP = [8, 14, 8, 8, 14, 8, 14, 8, 8]   # 3 個 >10 的間隙 → 應切成 4 帶

def _build_fukuoka() -> list[float]:
    asc = [_BASE]
    for g in _GAPS_ULP:
        asc.append(asc[-1] + g * _ULP)
    return list(reversed(asc))   # 降冪

FUKUOKA_SCORES = _build_fukuoka()


def test_empty_and_single():
    assert assign_tie_bands([]) == []
    assert assign_tie_bands([110.5]) == [0]


def test_identical_scores_same_band():
    assert assign_tie_bands([1.0, 1.0, 1.0]) == [0, 0, 0]


def test_clearly_distinct_scores_get_new_bands():
    assert assign_tie_bands([100.0, 50.0, 10.0]) == [0, 1, 2]


def test_float32_ulp_adjacent_same_band():
    # 相鄰差 1 個 float32 ULP → 必屬同帶
    base = np.float32(110.99571)
    nxt = float(np.nextafter(base, np.float32(200.0)))
    bands = assign_tie_bands([nxt, float(base)])
    assert bands == [0, 0]


def test_float32_ulp_far_apart_new_band():
    # 相鄰差遠超過 TIE_ULP_THRESHOLD 個 ULP → 分帶
    ulp = float(np.spacing(np.float32(110.99571)))
    hi = 110.99571 + ulp * (TIE_ULP_THRESHOLD * 50)
    bands = assign_tie_bands([hi, 110.99571])
    assert bands == [0, 1]


def test_fukuoka_top10_mostly_unresolvable():
    # 相鄰 7~15 ULP 的福岡情境:threshold=10 下,8 ULP 同帶、14 ULP 分帶
    bands = assign_tie_bands(FUKUOKA_SCORES)
    assert len(bands) == 10
    assert bands == sorted(bands)          # 帶號單調不減
    assert bands[-1] + 1 == 4, "3 個 >threshold 間隙應切出恰好 4 帶"


def test_none_scores_break_band():
    # None(如未進精排)不可與任何人同帶
    bands = assign_tie_bands([110.5, None, 110.5])
    assert bands == [0, 1, 2]


def test_band_is_transitive_chain():
    # A~B 同帶、B~C 同帶 ⇒ A、C 同帶(鏈式),即使 A-C 差 > threshold
    ulp = float(np.spacing(np.float32(100.0)))
    scores = [100.0 + ulp * 8 * i for i in range(5)][::-1]  # 相鄰 8 ULP,首尾 32 ULP
    bands = assign_tie_bands(scores)
    assert bands == [0, 0, 0, 0, 0]


def test_dispersion_stats_fukuoka():
    s = dispersion_stats(FUKUOKA_SCORES)
    assert s["range"] > 0
    assert 0 < s["relative_range"] < 1e-4          # spec:相對差異 1.6e-5 量級
    assert s["min_adjacent_gap"] > 0
    # 建構時最小相鄰間隙 = 8 ULP;容許 float 誤差 ±1
    assert 7 < s["min_adjacent_gap_ulp"] < 9


def test_dispersion_stats_degenerate():
    assert dispersion_stats([]) == {
        "range": None, "relative_range": None,
        "min_adjacent_gap": None, "min_adjacent_gap_ulp": None,
    }
    one = dispersion_stats([5.0])
    assert one["range"] == 0.0
    assert one["min_adjacent_gap"] is None
