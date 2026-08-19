"""spec 4.3 — 對照判讀 (treatment vs control)。

verdict / personalization_strength / 門檻警示 / A∪B 合併列(5.5 rows 契約)。
"""
from __future__ import annotations

from .relevance import decode_relevance
from .tie_band import assign_tie_bands

# spec 4.3 門檻,V1 先用,之後校準
STRENGTH_LOW = 0.05    # < 5% 疑似個性化未生效 (紅)
STRENGTH_HIGH = 0.60   # > 60% 疑似個性化過度 (黃)


def verdict(a_rank, b_rank, a_band, b_band) -> str:
    if a_rank is not None and b_rank is None:
        return "only_a"          # 個性化的實質證據
    if a_rank is None and b_rank is not None:
        return "only_b"
    if a_rank == b_rank:
        return "identical"
    if a_band == b_band:
        return "tie_unresolvable"   # 同分帶內位移,不可判讀
    return "real_move"              # 跨同分帶,真實排序變動


def personalization_strength(a_top: list[str], b_top: list[str], k: int = 10) -> float:
    """Top-k 不重疊率。分母取 min(k, 較長一側長度):照 spec 公式除以固定 k
    會讓短結果列表(如各只有 3 筆且完全相同)算出 0.7 的假「過度個性化」。"""
    k_eff = min(k, max(len(a_top), len(b_top)))
    if k_eff == 0:
        return 0.0
    overlap = len(set(a_top[:k]) & set(b_top[:k]))
    return 1 - overlap / k_eff


def strength_warning(strength: float) -> str | None:
    """回傳警示代碼;正常區間回 None (spec 4.3 門檻表)。"""
    if strength < STRENGTH_LOW:
        return "suspect_inactive"
    if strength > STRENGTH_HIGH:
        return "suspect_excessive"
    return None


def _index_side(prods: list[dict]) -> tuple[dict[str, dict], dict[int, int]]:
    """回傳 (prod_mid → row, rank → band)。prods 需依 rank 升冪。"""
    ordered = sorted(prods, key=lambda p: p["rank"])
    bands = assign_tie_bands([p.get("ltr_score") for p in ordered])
    by_mid = {p["prod_mid"]: p for p in ordered}
    band_by_rank = {p["rank"]: b for p, b in zip(ordered, bands)}
    return by_mid, band_by_rank


def _movement_bands(rank_a, rank_b, bands_a: dict[int, int],
                    bands_b: dict[int, int]) -> tuple[int | None, int | None]:
    """給 verdict 比對用的 (band_x, band_y)。

    兩側的帶號是各自獨立編號的 — 直接拿「商品在 A 的帶號」對「商品在 B 的
    帶號」比相等,只要任一側多一顆商品帶號就整組位移,相等與否毫無意義。
    正確語意是「rank_a → rank_b 這段位移是否落在同一個同分帶內」:
    優先用 treatment (A) 的分數結構同時查兩個位置的帶號;A 蓋不住就退用 B;
    兩邊都蓋不住 → 回 (0, 1) 讓 verdict 判 real_move(無法歸因於分數噪音,
    寧可顯示真實變動也不假稱不可判讀)。
    """
    for band_map in (bands_a, bands_b):
        if rank_a in band_map and rank_b in band_map:
            return band_map[rank_a], band_map[rank_b]
    return 0, 1


def merge_rows(a_prods: list[dict], b_prods: list[dict]) -> list[dict]:
    """A ∪ B 合併 (spec 5.5):依 rank_a 升冪、缺值排後。

    每側輸入為 prod dict list,至少含:
    prod_mid / rank / ltr_score / relevance_status_code / in_rerank_scope / is_ad
    """
    a_by_mid, a_bands = _index_side(a_prods)
    b_by_mid, b_bands = _index_side(b_prods)

    rows: list[dict] = []
    for mid in a_by_mid.keys() | b_by_mid.keys():
        a, b = a_by_mid.get(mid), b_by_mid.get(mid)
        rank_a = a["rank"] if a else None
        rank_b = b["rank"] if b else None
        if rank_a is not None and rank_b is not None:
            band_a, band_b = _movement_bands(rank_a, rank_b, a_bands, b_bands)
        else:
            band_a = a_bands.get(rank_a) if rank_a is not None else None
            band_b = b_bands.get(rank_b) if rank_b is not None else None

        rel_a = decode_relevance(a["relevance_status_code"]) if a else None
        rel_b = decode_relevance(b["relevance_status_code"]) if b else None
        # 不變量:diff_dims 只在兩側都有六碼時計算 — 資料流層面保證 ui-spec §6.3
        # 的觸發條件 (only_* 單側缺碼,永遠拿不到差異位後綴;spec 描述的是結果,
        # 這裡是原因)。
        diff_dims = (
            [d for d in rel_a if rel_a[d] != rel_b[d]] if rel_a and rel_b else []
        )

        # in_rerank_scope / is_ad 以 A(treatment)側為準,A 缺席才取 B
        src = a or b
        rows.append({
            "prod_mid": mid,
            "prod_name": src.get("prod_name"),
            "rank_a": rank_a, "rank_b": rank_b,
            "ltr_score_a": a.get("ltr_score") if a else None,
            "band_a": band_a, "band_b": band_b,
            "verdict": verdict(rank_a, rank_b, band_a, band_b),
            "relevance_a": rel_a,
            "relevance_b": rel_b,
            "relevance_diff_dims": diff_dims,
            "in_rerank_scope": bool(src.get("in_rerank_scope")),
            "is_ad": bool(src.get("is_ad")),
        })

    # rank_a 升冪、缺值排後;缺 rank_a 者以 rank_b 次序穩定排列
    rows.sort(key=lambda r: (r["rank_a"] is None,
                             r["rank_a"] if r["rank_a"] is not None else 0,
                             r["rank_b"] if r["rank_b"] is not None else 0))
    return rows
