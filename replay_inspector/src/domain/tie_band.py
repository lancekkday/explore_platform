"""spec 4.2 — 同分帶 (tie band)。

ltr_score 原始為 float32;在 111 量級 ULP ≈ 7.6e-6,實測相鄰兩名差距僅
7~15 ULP → 相對順序不具統計意義。相鄰間距 <= TIE_ULP_THRESHOLD 個
float32 ULP 者視為同帶,帶內位移一律判「不可判讀」而非 Δrank。
"""
from __future__ import annotations

import numpy as np

# 可調參數,待與搜尋 RD 校準 (spec 9.4)
TIE_ULP_THRESHOLD = 10


def assign_tie_bands(scores: list[float | None]) -> list[int]:
    """scores 需為降冪排列。回傳每筆所屬的同分帶編號(從 0 開始)。

    - 相鄰間距 <= TIE_ULP_THRESHOLD 個 float32 ULP → 同帶(鏈式傳遞:
      A~B 同帶且 B~C 同帶 ⇒ A、C 同帶,即使 A-C 間距超標)
    - None(如未進精排、缺分)不與任何人同帶,自成一帶且切斷鏈
    """
    if not scores:
        return []
    bands = [0]
    for prev, cur in zip(scores, scores[1:]):
        if prev is None or cur is None:
            bands.append(bands[-1] + 1)
            continue
        ulp = float(np.spacing(np.float32(prev)))
        bands.append(bands[-1] if abs(prev - cur) <= TIE_ULP_THRESHOLD * ulp
                     else bands[-1] + 1)
    return bands


def dispersion_stats(scores: list[float | None]) -> dict[str, float | None]:
    """前端離散度指標 (spec 4.2):分數全距、相對差異、最小相鄰間距、換算 ULP 數。

    ULP 以最小相鄰間距所在的 prev 分數量級換算 — 回答「這個最小間距等於
    幾個 float32 可表示步長」,>threshold 才可能可判讀。
    """
    vals = [s for s in scores if s is not None]
    if not vals:
        return {"range": None, "relative_range": None,
                "min_adjacent_gap": None, "min_adjacent_gap_ulp": None}

    rng = max(vals) - min(vals)
    denom = max(abs(max(vals)), abs(min(vals)))
    rel = (rng / denom) if denom else 0.0

    min_gap: float | None = None
    min_gap_prev: float | None = None
    for prev, cur in zip(vals, vals[1:]):
        gap = abs(prev - cur)
        if min_gap is None or gap < min_gap:
            min_gap, min_gap_prev = gap, prev

    if min_gap is None:
        return {"range": rng, "relative_range": rel,
                "min_adjacent_gap": None, "min_adjacent_gap_ulp": None}

    ulp = float(np.spacing(np.float32(min_gap_prev)))
    return {
        "range": rng,
        "relative_range": rel,
        "min_adjacent_gap": min_gap,
        "min_adjacent_gap_ulp": (min_gap / ulp) if ulp else None,
    }
