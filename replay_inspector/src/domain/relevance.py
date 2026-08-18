"""spec 4.1 — relevance_status_code 六碼解碼。

集中一處的純函式:spec §9.1–9.3 未決事項(第 4 位語意 / 值域 / 第 1 位方向)
答案回來只改這個檔案 —— 呼叫端一律吃解碼後的 dict,不碰原始字串。
"""
from __future__ import annotations

# 由左至右每位的維度 (spec 4.1 表格)。
# ⚠ 第 4 位 "ip" 的語意待搜尋 RD 確認 (spec 9.1):
#   - 若為「使用者 IP 地理」→ 六碼中唯一 user × 商品維度,前端獨立標色 (現行做法)
#   - 若為「IP 聯名內容」→ 改與 theme 同性質,只需改前端配色,本檔不動
RELEVANCE_DIMS = ["sellable", "location", "category", "ip", "theme", "text"]

_CODE_LEN = len(RELEVANCE_DIMS)


def decode_relevance(code) -> dict[str, int | None]:
    """'000220' -> {'sellable':0,'location':0,'category':0,'ip':2,'theme':2,'text':0}

    非預期格式(None / 長度不對 / 非 ASCII 數字 / 非字串)一律回 all-None,
    不猜值、不丟例外 (驗收條件 5) — UI 據此顯示「未知」。

    isascii() 檢查是必要的:全形數字 '０' 的 isdigit() 是 True、int() 也吃,
    但那是非預期格式,照「不猜」原則回 None。
    """
    if (
        not isinstance(code, str)
        or len(code) != _CODE_LEN
        or not code.isascii()
        or not code.isdigit()
    ):
        return {d: None for d in RELEVANCE_DIMS}
    return dict(zip(RELEVANCE_DIMS, (int(c) for c in code)))
