"""spec 4.1 — relevance_status_code 六碼解碼。

集中一處的純函式:spec §9.1–9.3 未決事項(第 4 位語意 / 值域 / 第 1 位方向)
答案回來只改這個檔案 —— 呼叫端一律吃解碼後的 dict,不碰原始字串。
"""
from __future__ import annotations

# 由左至右每位的維度。RD 已全數確認 (Joyce 2026-08-17 位置序;2026-08-19 語意):
#   可售/地點/類目/IP/主題/文本 — 與 spec 4.1 一致
#   第 4 位 IP = 品牌 IP (聯名內容,如吉卜力),與 theme 同性質 (spec 9.1 定案)
#   值語意:「數字越小越相關」→ 0 = 最相關/通過 (spec 9.2/9.3 定案;
#   '000220' 第 1 位 0 = 可售,所以能曝光)。燈號視覺:值越大顏色越深 =
#   「該維度偏離越多」,全 0 的列自然淡出 — 與 ui-spec 色彩紀律一致。
#   ⇒ 六位全部是 query × 商品維度,treatment/control 間任何位的差異都
#   不該來自個性化 (見 presentation._diff_suffix 的異常訊號註記)。
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
