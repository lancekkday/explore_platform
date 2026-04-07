"""
IntentMatcher 單元測試
涵蓋：
  - 地點型 keyword（原有邏輯）
  - 純 category keyword（esim / sim / wifi）
  - destination+category 複合詞（泰國esim / 東京一日遊）
  - destination+theme 複合詞（北海道滑雪 / 日本賞花）
  - CATEGORY_MAPPING 擴充（交通/接送/JR）
  - AI metadata 流程
"""
import pytest
from skills.intent_matcher import IntentMatcher


@pytest.fixture
def m():
    return IntentMatcher(dest_dump_dir=".")


def tier(result):
    """取出 verify() 回傳 dict 中的 tier 值。"""
    return result["tier"]


# ─────────────────────────────────────────────
# 原有：地點型 keyword
# ─────────────────────────────────────────────

class TestLocationKeyword:
    def test_t1_dest_and_cat_match(self, m):
        """dest ✓ + 精確 category → T1"""
        r = m.verify(
            {"name": "超讚北海道一日遊套裝", "introduction": "",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道一日遊"
        )
        assert tier(r) == 1

    def test_t2_dest_match_kw_in_title(self, m):
        """dest ✓ + 無明確 category + keyword 在標題 → T2"""
        r = m.verify(
            {"name": "北海道精選旅遊套裝", "introduction": "",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_022"}},   # 多日遊，非 一日遊
            "北海道一日遊"
        )
        assert tier(r) == 2

    def test_t2_dest_match_wrong_cat_kw_in_title(self, m):
        """dest ✓ + category 不符 + 地點詞在標題 → T2
        複合拆解後 target_loc='北海道'，'北海道' 出現在標題，故為 T2 而非 T3"""
        r = m.verify(
            {"name": "北海道拉麵美食饗宴", "introduction": "",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_079"}},
            "北海道一日遊"
        )
        assert tier(r) == 2

    def test_t2_dest_mismatch_cat_exact(self, m):
        """dest ✗ + category 完全符合 → T2（對的商品類型，錯的地點）
        例：搜尋北海道一日遊，出現東京一日遊 — 類型對但地點錯"""
        r = m.verify(
            {"name": "東京精選一日遊", "introduction": "",
             "destinations": [{"name": "東京"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道一日遊"
        )
        assert tier(r) == 2

    def test_t3_kw_in_title_dest_mismatch(self, m):
        """dest ✗ 但 keyword 在標題 → T3（東京迪士尼 案例）"""
        r = m.verify(
            {"name": "超值折扣！東京迪士尼度假區通票", "introduction": "",
             "destinations": [{"name": "千葉縣"}],
             "product_category": {"main": "CATEGORY_001"}},
            "東京迪士尼"
        )
        assert tier(r) == 3


# ─────────────────────────────────────────────
# 純 category keyword（esim / wifi 等）
# ─────────────────────────────────────────────

class TestPureCategoryKeyword:
    def test_esim_t1(self, m):
        """category ✓ + keyword 在標題 → T1"""
        r = m.verify(
            {"name": "日本eSIM 7天無限流量", "introduction": "esim上網方案",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_081"}},
            "esim"
        )
        assert tier(r) == 1

    def test_esim_t2_cat_only(self, m):
        """category ✓ 但 keyword 不在標題 → T2"""
        r = m.verify(
            {"name": "日本 SIM 卡 7天方案", "introduction": "適用日本上網",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_081"}},
            "esim"
        )
        assert tier(r) == 2

    def test_esim_t2_kw_in_title_wrong_cat(self, m):
        """keyword 在標題但 category 不符 → T2"""
        r = m.verify(
            {"name": "esim 教學行程一日遊", "introduction": "",
             "destinations": [{"name": "台北"}],
             "product_category": {"main": "CATEGORY_020"}},
            "esim"
        )
        assert tier(r) == 2

    def test_esim_t0_miss(self, m):
        """category ✗ + keyword 完全未提及 → T0"""
        r = m.verify(
            {"name": "台北一日遊行程", "introduction": "帶你遊台北",
             "destinations": [{"name": "台北"}],
             "product_category": {"main": "CATEGORY_020"}},
            "esim"
        )
        assert tier(r) == 0

    def test_wifi_routes_to_product_mode(self, m):
        """wifi 也走 pure category 路徑，不被誤判為地點"""
        r = m.verify(
            {"name": "韓國WiFi分享器 4G無限", "introduction": "",
             "destinations": [{"name": "韓國"}],
             "product_category": {"main": "CATEGORY_081"}},
            "wifi"
        )
        assert tier(r) == 1
        assert r["expected_dest"] is None   # 純 category 模式不應有 dest


# ─────────────────────────────────────────────
# destination + category 複合詞
# ─────────────────────────────────────────────

class TestCompoundDestinationCategory:
    def test_compound_split_cases(self, m):
        """_extract_compound_intent 拆解正確性"""
        assert m._extract_compound_intent("泰國esim")  == ("泰國", "esim", None)
        assert m._extract_compound_intent("東京一日遊") == ("東京", "一日遊", None)
        assert m._extract_compound_intent("香港自助餐") == ("香港", "自助餐", None)
        assert m._extract_compound_intent("沖繩包車")   == ("沖繩", "包車", None)
        assert m._extract_compound_intent("esim")      == (None, None, None)   # 純 category，不拆
        assert m._extract_compound_intent("日本")      == (None, None, None)   # 純 dest，不拆

    def test_thailand_esim_t1(self, m):
        """泰國esim：dest=泰國 + cat=CATEGORY_081 → T1"""
        r = m.verify(
            {"name": "泰國eSIM 5G 10天無限流量", "introduction": "",
             "destinations": [{"name": "泰國"}],
             "product_category": {"main": "CATEGORY_081"}},
            "泰國esim"
        )
        assert tier(r) == 1
        assert r["expected_dest"] == "泰國"
        assert r["expected_cat"]  == "esim"

    def test_thailand_esim_t0_wrong_dest(self, m):
        """泰國esim：dest=日本（不符）+ cat 正確 → T2（有 category 分不應直接 T0）"""
        r = m.verify(
            {"name": "日本eSIM 7天", "introduction": "",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_081"}},
            "泰國esim"
        )
        assert tier(r) == 2   # dest ✗ 但 category 正確 → T2

    def test_tokyo_day_tour_t1(self, m):
        """東京一日遊：dest=東京 + cat=CATEGORY_020 → T1"""
        r = m.verify(
            {"name": "東京精選一日遊：淺草+上野", "introduction": "",
             "destinations": [{"name": "東京"}],
             "product_category": {"main": "CATEGORY_020"}},
            "東京一日遊"
        )
        assert tier(r) == 1

    def test_hong_kong_buffet_t1(self, m):
        """香港自助餐：dest=香港 + cat=CATEGORY_079（production 實測確認）→ T1"""
        r = m.verify(
            {"name": "香港五星飯店自助餐下午茶", "introduction": "",
             "destinations": [{"name": "香港"}],
             "product_category": {"main": "CATEGORY_079"}},
            "香港自助餐"
        )
        assert tier(r) == 1


# ─────────────────────────────────────────────
# destination + theme 複合詞
# ─────────────────────────────────────────────

class TestCompoundDestinationTheme:
    def test_compound_theme_split(self, m):
        """_extract_compound_intent 正確拆解 theme"""
        assert m._extract_compound_intent("北海道滑雪") == ("北海道", None, "滑雪")
        assert m._extract_compound_intent("日本賞花")   == ("日本", None, "賞花")
        assert m._extract_compound_intent("台灣溫泉")   == ("台灣", None, "溫泉")

    def test_ski_t1_theme_in_title(self, m):
        """北海道滑雪：dest ✓ + '滑雪' 在標題 → T1"""
        r = m.verify(
            {"name": "北海道二世谷滑雪一日體驗", "introduction": "北海道最棒雪場",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道滑雪"
        )
        assert tier(r) == 1
        assert r["expected_theme"] == "滑雪"

    def test_ski_t2_theme_in_intro(self, m):
        """北海道滑雪：dest ✓ + '滑雪' 只在描述 → T2"""
        r = m.verify(
            {"name": "北海道冬季套裝行程", "introduction": "包含滑雪體驗課程",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道滑雪"
        )
        assert tier(r) == 2

    def test_ski_t3_no_theme_mention(self, m):
        """北海道滑雪：dest ✓ 但 theme 完全未提及 → T3"""
        r = m.verify(
            {"name": "北海道美食溫泉之旅", "introduction": "北海道道地料理",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道滑雪"
        )
        assert tier(r) == 3
        assert any("主題不符" in reason for reason in r["mismatch_reasons"])

    def test_ski_t0_wrong_dest(self, m):
        """北海道滑雪：dest=東京（不符）+ theme 不在文中 → T0"""
        r = m.verify(
            {"name": "東京觀光一日遊", "introduction": "",
             "destinations": [{"name": "東京"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道滑雪"
        )
        assert tier(r) == 0

    def test_sakura_english_alias(self, m):
        """賞花主題詞含英文 alias（sakura）應能匹配"""
        r = m.verify(
            {"name": "日本 Cherry Blossom Viewing Tour", "introduction": "sakura season",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_020"}},
            "日本賞花"
        )
        assert tier(r) >= 1   # sakura 在標題或描述


# ─────────────────────────────────────────────
# 擴充的 CATEGORY_MAPPING（交通類）
# ─────────────────────────────────────────────

class TestExpandedCategoryMapping:
    def test_transport_keywords_mapped(self, m):
        """交通相關關鍵字應都映射到 CATEGORY_120"""
        transport_kws = ["交通", "接送", "接送機", "包車", "新幹線", "jr pass", "jr", "高鐵"]
        for kw in transport_kws:
            assert m.CATEGORY_MAPPING.get(kw) == "CATEGORY_120", f"{kw} 應映射到 CATEGORY_120"

    def test_okinawa_car_t1(self, m):
        """沖繩包車：dest=沖繩 + cat=CATEGORY_120 → T1"""
        r = m.verify(
            {"name": "沖繩包車一日遊（司機導覽）", "introduction": "",
             "destinations": [{"name": "沖繩"}],
             "product_category": {"main": "CATEGORY_120"}},
            "沖繩包車"
        )
        assert tier(r) == 1

    def test_jr_pass_pure_category(self, m):
        """jr pass 是純 category keyword，走 product keyword 路徑"""
        r = m.verify(
            {"name": "日本 JR Pass 7日券", "introduction": "jr pass 全線適用",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_120"}},
            "jr pass"
        )
        assert tier(r) == 1
        assert r["expected_dest"] is None


# ─────────────────────────────────────────────
# AI metadata 流程
# ─────────────────────────────────────────────

class TestAIMetadata:
    def test_ai_location_overrides_rule_split(self, m):
        """有 AI location 時，應優先使用 AI 結果而非規則拆解"""
        ai_meta = {"location": "泰國", "category": "CATEGORY_081", "theme": None}
        r = m.verify(
            {"name": "泰國eSIM 5G", "introduction": "",
             "destinations": [{"name": "泰國"}],
             "product_category": {"main": "CATEGORY_081"}},
            "泰國esim",
            ai_metadata=ai_meta
        )
        assert tier(r) == 1

    def test_ai_theme_used_for_judgment(self, m):
        """AI 提供 theme 時，應用 theme 判斷邏輯"""
        ai_meta = {"location": "北海道", "category": "CATEGORY_020", "theme": "滑雪"}
        r = m.verify(
            {"name": "北海道滑雪一日遊", "introduction": "",
             "destinations": [{"name": "北海道"}],
             "product_category": {"main": "CATEGORY_020"}},
            "北海道滑雪",
            ai_metadata=ai_meta
        )
        assert tier(r) == 1
        assert r["expected_theme"] == "滑雪"

    def test_pure_category_with_ai_no_location(self, m):
        """AI 解析 esim 無地點，category code 直接使用"""
        ai_meta = {"location": None, "category": "CATEGORY_081", "theme": None}
        r = m.verify(
            {"name": "日本esim 7天", "introduction": "",
             "destinations": [{"name": "日本"}],
             "product_category": {"main": "CATEGORY_081"}},
            "esim",
            ai_metadata=ai_meta
        )
        assert tier(r) == 1
