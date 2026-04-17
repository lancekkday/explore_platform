"""
熱搜詞意圖判斷驗收測試
─────────────────────────────────────────────────────────
直接呼叫 kkday_api（production）+ IntentMatcher，無須 stage 環境。
Cookie 從 /tmp/prod_cookie.txt 讀取（由 /api/guest-cookie 取得）。

執行：
    pytest test_hotword_validation.py -v --tb=short
"""
import os
import pytest
from collections import Counter
from kkday_api import fetch_kkday_products
from skills.intent_matcher import IntentMatcher

COOKIE_FILE = "/tmp/prod_cookie.txt"
FETCH_COUNT = 30   # 每個關鍵字只取前 30 筆，節省時間

# ── 測試關鍵字清單 ────────────────────────────────────────
# 格式：(keyword, query_type, min_t1t2_rate, min_relevant_rate)
#
# min_t1t2_rate  : T1+T2 佔前 30 名的最低比例（category 型主要指標）
# min_relevant_rate: T1+T2+T3 的最低比例（destination 型主要指標）
#
# [Known limitation] destination 父子層級缺失：
#   "日本" 搜尋的商品 destination 是城市級（東京、大阪），不含 "日本" 字串，
#   導致 dest_match=False → 被降至 T3。T3 表示 keyword 出現於標題，屬有效召回。
#   待補充 destination 層級查詢後可提高 T1+T2 threshold。
HOTWORDS = [
    # keyword,       query_type,   t1t2, relevant
    # 純 category（T1+T2 是主要指標，商品類型判斷準確）
    ("esim",        "category",   0.80,  0.95),
    ("wifi",        "category",   0.80,  0.85),
    ("門票",        "category",   0.60,  0.90),
    ("jr pass",     "category",   0.40,  0.80),
    ("下午茶",      "category",   0.40,  0.80),
    # 純 destination（T1+T2 較低屬 known limitation，用 relevant rate 驗收）
    ("日本",        "destination",0.00,  0.70),
    ("東京",        "destination",0.10,  0.70),
    ("九份",        "destination",0.00,  0.50),
    ("阿里山",      "destination",0.20,  0.60),
    # destination + category（T1+T2 為主）
    ("泰國esim",    "dest+cat",   0.60,  0.95),
    ("東京一日遊",  "dest+cat",   0.50,  0.90),
    ("香港自助餐",  "dest+cat",   0.20,  0.60),
    ("沖繩包車",    "dest+cat",   0.20,  0.70),
    # destination + theme（dest 層級問題 + theme 要求，threshold 較寬鬆）
    ("北海道滑雪",  "dest+theme", 0.10,  0.60),
    ("日本賞花",    "dest+theme", 0.00,  0.30),
    # edge case（POI 型，T3 是預期行為）
    ("東京迪士尼",  "dest+kw",    0.05,  0.70),
]


@pytest.fixture(scope="session")
def cookie():
    if not os.path.exists(COOKIE_FILE):
        pytest.skip(f"Cookie file not found: {COOKIE_FILE}. Run: curl http://localhost:19426/api/guest-cookie?env=production | python3 -c \"import sys,json;print(json.load(sys.stdin)['cookie'])\" > {COOKIE_FILE}")
    with open(COOKIE_FILE) as f:
        c = f.read().strip()
    if not c:
        pytest.skip("Cookie file is empty.")
    return c


@pytest.fixture(scope="session")
def matcher():
    return IntentMatcher(dest_dump_dir=".")


def fetch_and_judge(keyword, cookie, matcher, count=FETCH_COUNT):
    """Fetch products from production and run intent judgment. Returns list of tier results."""
    try:
        products, total, _ = fetch_kkday_products(keyword, "production", cookie, count)
    except Exception as e:
        return None, str(e)

    results = []
    for i, p in enumerate(products):
        r = matcher.verify(p, keyword)
        results.append({
            "rank": i + 1,
            "name": p.get("name", "")[:40],
            "tier": r["tier"],
            "dest_match": r["dest_match"],
            "cat_match": r["cat_match"],
            "expected_dest": r.get("expected_dest"),
            "expected_cat": r.get("expected_cat"),
            "expected_theme": r.get("expected_theme"),
            "reasons": r["mismatch_reasons"],
        })
    return results, None


# ── 基本 API 健康檢查 ─────────────────────────────────────

def test_fetch_esim_returns_results(cookie, matcher):
    """Production API 可以正常取到 esim 商品"""
    products, err = fetch_and_judge("esim", cookie, matcher)
    assert err is None, f"API error: {err}"
    assert products and len(products) > 0, "No products returned"


# ── 逐關鍵字驗收 ─────────────────────────────────────────

@pytest.mark.parametrize("keyword,query_type,min_t1t2,min_relevant", HOTWORDS)
def test_hotword_tier_distribution(keyword, query_type, min_t1t2, min_relevant, cookie, matcher):
    """
    每個熱搜詞驗收：
    - category 型：T1+T2 rate ≥ min_t1t2（類型判斷準確）
    - destination 型：T1+T2+T3 rate ≥ min_relevant（有效召回率，含父子層級 known limitation）
    - 前 5 名不應全部是 T0
    """
    results, err = fetch_and_judge(keyword, cookie, matcher)
    assert err is None, f"[{keyword}] API error: {err}"
    assert results, f"[{keyword}] No products returned"

    tiers = [r["tier"] for r in results]
    counter = Counter(tiers)
    total = len(tiers)
    t1t2_rate     = (counter[1] + counter[2]) / total
    relevant_rate = (counter[1] + counter[2] + counter[3]) / total

    dist_str = " | ".join(f"T{k}:{v}" for k, v in sorted(counter.items()))
    print(f"\n  [{keyword}] ({query_type}) {dist_str}  T1+T2={t1t2_rate:.0%}  relevant={relevant_rate:.0%}")

    assert t1t2_rate >= min_t1t2, (
        f"[{keyword}] T1+T2={t1t2_rate:.0%} < {min_t1t2:.0%}. {dist_str}"
    )
    assert relevant_rate >= min_relevant, (
        f"[{keyword}] relevant={relevant_rate:.0%} < {min_relevant:.0%}. {dist_str}"
    )

    # 前 5 名不應全部是 T0（代表搜尋引擎嚴重失準）
    top5_tiers = [r["tier"] for r in results[:5]]
    assert any(t > 0 for t in top5_tiers), (
        f"[{keyword}] Top 5 products are ALL T0 (Miss). Possible search engine issue."
    )


# ── 複合詞拆解正確性驗收 ─────────────────────────────────

@pytest.mark.parametrize("keyword,exp_dest,exp_cat,exp_theme", [
    ("泰國esim",   "泰國",   "esim",   None),
    ("東京一日遊", "東京",   "一日遊", None),
    ("香港自助餐", "香港",   "自助餐", None),
    ("北海道滑雪", "北海道", None,    "滑雪"),
    ("日本賞花",   "日本",   None,    "賞花"),
    ("沖繩包車",   "沖繩",   "包車",  None),
])
def test_compound_split_accuracy(keyword, exp_dest, exp_cat, exp_theme, matcher):
    """規則拆解結果與預期完全一致（不需要 cookie）"""
    dest, cat, theme = matcher._extract_compound_intent(keyword)
    assert dest  == exp_dest,  f"[{keyword}] dest: got '{dest}' expected '{exp_dest}'"
    assert cat   == exp_cat,   f"[{keyword}] cat: got '{cat}' expected '{exp_cat}'"
    assert theme == exp_theme, f"[{keyword}] theme: got '{theme}' expected '{exp_theme}'"


# ── 個別商品 spot-check（明確應為 T1 的案例）───────────────

@pytest.mark.parametrize("keyword,must_match_name_fragment,expected_min_tier", [
    ("esim",   "esim",   1),   # 含 esim 字眼的 esim 商品應 T1
    ("東京一日遊", "東京", 2),  # 東京商品至少 T2
    ("北海道滑雪", "滑雪", 1),  # 含滑雪字眼的北海道商品應 T1
])
def test_spot_check_specific_products(keyword, must_match_name_fragment, expected_min_tier, cookie, matcher):
    """
    在搜尋結果前 30 名中，找出名稱含指定字串的商品，
    確認其 tier 達到預期下限。
    """
    results, err = fetch_and_judge(keyword, cookie, matcher)
    assert err is None

    matched = [r for r in results if must_match_name_fragment.lower() in r["name"].lower()]
    if not matched:
        pytest.skip(f"[{keyword}] No product with '{must_match_name_fragment}' in top {FETCH_COUNT}")

    for r in matched[:3]:  # 只看前 3 個符合的
        assert r["tier"] >= expected_min_tier, (
            f"[{keyword}] Product '{r['name']}' got T{r['tier']}, expected >= T{expected_min_tier}. "
            f"Reasons: {r['reasons']}"
        )
