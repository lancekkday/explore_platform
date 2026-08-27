"""ui-spec §9.2 — 呈現層共用純函式。

判讀文字、燈號映射、分數前綴計算放 domain,Streamlit 與未來的 TCMS 移植
共用同一份,不各自維護。
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .relevance import RELEVANCE_DIMS

_CIRCLED = "①②③④⑤⑥"


def _diff_suffix(diff_dims: list[str] | None) -> str:
    # 差異位語意 (RD 2026-08-19 定案:④=品牌 IP → 六位全是 query × 商品維度):
    #   同 query 同商品在 treatment/control 間,任何位的差異都不該來自個性化 —
    #   ① 可能是兩事件的時間差 (商品狀態變了);其餘位 = 異常訊號
    #   (normalized_keyword 不同 / index shard 傾斜 / 快取陳舊),
    #   即資料一致性檢查。ui-spec §2.1 明定 --alert 不用於排序表,
    #   故維持灰色呈現,判讀交給使用者 (hover 有逐位數值)。
    idx = [RELEVANCE_DIMS.index(d) for d in (diff_dims or []) if d in RELEVANCE_DIMS]
    if not idx:
        return ""
    return " · " + "".join(_CIRCLED[i] for i in sorted(idx)) + " 差異"


def verdict_text(verdict: str, rank_a: Optional[int], rank_b: Optional[int],
                 diff_dims: list[str] | None) -> str:
    """ui-spec §6.3 判讀欄文字。

    - 差異位後綴 (` · ④ 差異`) 的觸發條件只有一個:兩側皆有六碼且碼不同,
      因此只出現在 real_move 與 tie_unresolvable。tie 也接是刻意的 —
      分數同帶排序不可判讀,但六碼不同代表相關性維度確實不一樣,是唯一
      「可忽略排序、但不該忽略該列」的情況。
      (修正註:初版把差異位接在 only_* 上 — 接錯狀態,已修正。)
    - only_* 文案帶「前 10」限定詞:判定是在 top-10 視窗內做的,不是完整
      結果集 — 查不到不等於不存在 (可能排在第 340 名)。**不接**差異位,
      對側沒有六碼,任何補法都是編造 (spec §6.3 / §10 反模式)。
    - real_move 帶幅度:`跨帶 ↓3` (B 名次比 A 大 = 往後掉 = ↓)
    - identical → `—` (不顯示文字,視覺退場)
    """
    if verdict == "identical":
        return "—"
    if verdict == "tie_unresolvable":
        return "同帶內位移" + _diff_suffix(diff_dims)
    if verdict == "real_move":
        delta = (rank_b or 0) - (rank_a or 0)
        arrow = "↓" if delta > 0 else "↑"
        return f"跨帶 {arrow}{abs(delta)}" + _diff_suffix(diff_dims)
    return "僅 A 前 10" if verdict == "only_a" else "僅 B 前 10"


def lamp_level(value: Optional[int]) -> Optional[int]:
    """ui-spec §6.4 值→ink 色階:0→0(rule 灰), 1→1(25%), 2→2(50%), 3→3(75%), ≥4→4(100%)。
    None 保持 None (解碼失敗,六個空心框 + ?)。

    語意 (RD 定案「數字越小越相關」):0 = 通過/最相關 → 淡;值越大 = 該維度
    偏離越多 → 越深。深色格 = 值得看的異常,全 0 的列自然退場 — 與 ui-spec
    色彩紀律同向,故映射不倒轉。"""
    if value is None:
        return None
    return 0 if value <= 0 else min(int(value), 4)


def common_prefix_len(score_strs: list[str]) -> int:
    """ui-spec §2.3 — 當前可見列分數字串的最長共同前綴長度。

    <2 筆沒有「共同」可言 → 0。前綴淡化讓眼睛落在唯一有資訊的位數上。
    """
    strs = [s for s in score_strs if s]
    if len(strs) < 2:
        return 0
    first = strs[0]
    n = 0
    for i, ch in enumerate(first):
        if all(len(s) > i and s[i] == ch for s in strs[1:]):
            n = i + 1
        else:
            break
    return n


def band_gap(prev_score: Optional[float], next_score: Optional[float]) -> Optional[dict]:
    """ui-spec §6.1 帶邊界標籤:兩個相鄰同分帶之間的間距與 ULP 換算。
    「分隔列上的間距值是這個分組成立的理由,必須顯示」。"""
    if prev_score is None or next_score is None:
        return None
    gap = abs(prev_score - next_score)
    ulp = float(np.spacing(np.float32(prev_score)))
    return {"gap": gap, "ulp": (gap / ulp) if ulp else None}
