import pytest
from skills.intent_matcher import IntentMatcher

@pytest.fixture
def matcher():
    # Provide a dummy directory, the init function doesn't crash if it doesn't find the json file
    return IntentMatcher(dest_dump_dir=".")

def test_tier_1_exact_match(matcher):
    """
    Tier 1 (精準比對)：地點相符且主分類精確相符。
    """
    keyword = "北海道一日遊"
    product = {
        "name": "超讚北海道一日遊套裝",
        "destinations": [{"name": "北海道"}],
        "main_cat_key": "CATEGORY_020",
        "product_category": {"main": "一日遊"}
    }
    assert matcher.verify(product, keyword) == 1

def test_tier_2_broad_match(matcher):
    """
    Tier 2 (相關/廣泛比對)：地點相符且主分類被歸類在相關寬泛分類中（如多日遊、半日遊等）。
    """
    keyword = "北海道一日遊"
    product = {
        "name": "北海道多日遊浪漫之旅",
        "destinations": [{"name": "北海道"}],
        "main_cat_key": "CATEGORY_022", # 多日遊
        "product_category": {"main": "多日遊"}
    }
    assert matcher.verify(product, keyword) == 2

def test_tier_3_location_only(matcher):
    """
    Tier 3 (僅地點相符)：地點相符，但分類無關。
    """
    keyword = "北海道一日遊"
    product = {
        "name": "北海道拉麵美食饗宴",
        "destinations": [{"name": "北海道"}],
        "main_cat_key": "CATEGORY_125", # 美食
        "product_category": {"main": "美食"}
    }
    assert matcher.verify(product, keyword) == 3

def test_mismatch_location(matcher):
    """
    Mismatch (不符)：地點不相符。
    """
    keyword = "北海道一日遊"
    product = {
        "name": "東京精選一日遊",
        "destinations": [{"name": "東京"}],
        "main_cat_key": "CATEGORY_020",
        "product_category": {"main": "一日遊"}
    }
    # Should return None (Mismatch)
    assert matcher.verify(product, keyword) is None

def test_tier_3_keyword_in_title(matcher):
    """
    Tier 3 (關鍵字符合)：即使地點本身未在 Destinations 中直接出現，若完整關鍵字有出現在商品標題，降級至 Tier 3。
    """
    keyword = "東京迪士尼"
    product = {
        "name": "超值折扣！東京迪士尼度假區通票",
        # 假設該商品的詳細地點只有配到「千葉縣」，沒有配到「東京」字眼
        "destinations": [{"name": "千葉縣"}], 
        "main_cat_key": "CATEGORY_001",
        "product_category": {"main": "景點門票"}
    }
    assert matcher.verify(product, keyword) == 3
