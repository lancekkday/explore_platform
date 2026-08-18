"""spec 4.3 — 對照判讀 verdict / 個性化強度 / 合併列。"""
from src.domain.compare import (
    merge_rows,
    personalization_strength,
    strength_warning,
    verdict,
)


# ── verdict ───────────────────────────────────────────────────────────────────

def test_verdict_only_a_and_only_b():
    assert verdict(3, None, 0, None) == "only_a"
    assert verdict(None, 3, None, 0) == "only_b"


def test_verdict_identical():
    assert verdict(2, 2, 0, 1) == "identical"   # rank 相同即 identical,band 不看


def test_verdict_tie_unresolvable():
    # 同分帶內位移 → 不可判讀 (驗收 4:不能顯示 Δ=-1)
    assert verdict(1, 2, 0, 0) == "tie_unresolvable"


def test_verdict_real_move():
    assert verdict(1, 5, 0, 2) == "real_move"


# ── personalization_strength ─────────────────────────────────────────────────

def test_strength_identical_lists_is_zero():
    top = [str(i) for i in range(10)]
    assert personalization_strength(top, top) == 0.0


def test_strength_disjoint_lists_is_one():
    a = [str(i) for i in range(10)]
    b = [str(i + 100) for i in range(10)]
    assert personalization_strength(a, b) == 1.0


def test_strength_spec_example():
    # top10 重疊 8 → 強度 0.2 (spec 5.5 範例)。1 - 8/10 有浮點尾數,用 approx
    import pytest
    a = [str(i) for i in range(10)]
    b = [str(i) for i in range(8)] + ["x", "y"]
    assert personalization_strength(a, b) == pytest.approx(0.2)


def test_strength_order_insensitive_within_topk():
    a = [str(i) for i in range(10)]
    b = list(reversed(a))
    assert personalization_strength(a, b) == 0.0


# ── strength_warning (4.3 門檻) ───────────────────────────────────────────────

def test_warning_thresholds():
    assert strength_warning(0.0) == "suspect_inactive"     # < 5% 紅
    assert strength_warning(0.049) == "suspect_inactive"
    assert strength_warning(0.05) is None                  # 5%–60% 正常
    assert strength_warning(0.6) is None
    assert strength_warning(0.61) == "suspect_excessive"   # > 60% 黃


# ── merge_rows (5.5 rows 契約) ────────────────────────────────────────────────

def _prod(mid, rank, score, code="000000", in_scope=True, is_ad=False):
    return {
        "prod_mid": mid, "rank": rank, "ltr_score": score,
        "relevance_status_code": code, "in_rerank_scope": in_scope, "is_ad": is_ad,
    }


def test_merge_rows_union_and_order():
    a = [_prod("p1", 1, 110.9975), _prod("p2", 2, 110.9974)]
    b = [_prod("p2", 1, 110.9975), _prod("p3", 2, 110.9974)]
    rows = merge_rows(a, b)
    mids = [r["prod_mid"] for r in rows]
    # A∪B;rank_a 升冪,缺 rank_a (only_b) 排最後
    assert mids == ["p1", "p2", "p3"]
    assert rows[0]["verdict"] == "only_a"
    assert rows[2]["verdict"] == "only_b"


def test_merge_rows_tie_unresolvable_from_bands():
    # p1/p2 在 A 組同分帶內互換 → tie_unresolvable
    a = [_prod("p1", 1, 110.99751), _prod("p2", 2, 110.99750)]
    b = [_prod("p2", 1, 110.99751), _prod("p1", 2, 110.99750)]
    rows = merge_rows(a, b)
    by_mid = {r["prod_mid"]: r for r in rows}
    assert by_mid["p1"]["verdict"] == "tie_unresolvable"
    assert by_mid["p2"]["verdict"] == "tie_unresolvable"


def test_merge_rows_relevance_diff_dims():
    a = [_prod("p1", 1, 100.0, code="000220")]
    b = [_prod("p1", 1, 100.0, code="000020")]
    rows = merge_rows(a, b)
    assert rows[0]["verdict"] == "identical"
    assert rows[0]["relevance_diff_dims"] == ["ip"]


def test_merge_rows_decodes_relevance():
    a = [_prod("p1", 1, 100.0, code="000220")]
    rows = merge_rows(a, [])
    assert rows[0]["relevance_a"]["ip"] == 2
    assert rows[0]["relevance_b"] is None


def test_merge_rows_carries_scope_and_ad():
    a = [_prod("p1", 101, None, in_scope=False, is_ad=True)]
    rows = merge_rows(a, [])
    assert rows[0]["in_rerank_scope"] is False
    assert rows[0]["is_ad"] is True


def test_merge_rows_carries_ltr_score_a():
    a = [_prod("p1", 1, 110.5)]
    rows = merge_rows(a, [_prod("p1", 2, 99.0)])
    assert rows[0]["ltr_score_a"] == 110.5
    only_b = merge_rows([], [_prod("p2", 1, 99.0)])
    assert only_b[0]["ltr_score_a"] is None


def test_merge_rows_band_shift_regression():
    """帶號是各側獨立編號 — A 側多一顆自成一帶的商品把帶號整組位移時,
    帶內互換仍必須判 tie_unresolvable (以位移區間是否落在同帶判定,
    不是拿兩側帶號比相等)。"""
    # A: q 在 rank1 自成一帶 (分數拉開),p1/p2 在 rank2/3 同帶
    a = [
        _prod("q", 1, 200.0),
        _prod("p1", 2, 110.99751),
        _prod("p2", 3, 110.99750),
    ]
    # B: 沒有 q;p1/p2 帶內互換,佔 rank1/2 (B 側帶號從 0 起算)
    b = [
        _prod("p2", 1, 110.99751),
        _prod("p1", 2, 110.99750),
    ]
    by_mid = {r["prod_mid"]: r for r in merge_rows(a, b)}
    # p1: rank 2→2 = identical;p2: rank 3→1,位移區間 [1,3] 在 A 結構跨過 q
    # 的帶 → real_move (合理:它跳過了一個分數明確較高的商品)
    assert by_mid["p1"]["verdict"] == "identical"
    assert by_mid["p2"]["verdict"] == "real_move"
    # p3/p4 帶內互換,兩側帶號不同 (A: band1, B: band0) — 舊實作拿帶號比相等
    # 會誤判 real_move
    a2 = [
        _prod("q", 1, 200.0),
        _prod("p3", 2, 110.99751),
        _prod("p4", 3, 110.99750),
    ]
    b2 = [
        _prod("x", 1, 200.0),
        _prod("p4", 2, 110.99751),
        _prod("p3", 3, 110.99750),
    ]
    by_mid2 = {r["prod_mid"]: r for r in merge_rows(a2, b2)}
    assert by_mid2["p3"]["verdict"] == "tie_unresolvable"
    assert by_mid2["p4"]["verdict"] == "tie_unresolvable"


def test_strength_short_lists_not_inflated():
    """兩側各只有 3 筆且完全相同 → 強度必須是 0,不能因固定除以 k=10 而虛報 0.7。"""
    top = ["a", "b", "c"]
    assert personalization_strength(top, top) == 0.0
    assert personalization_strength([], []) == 0.0
