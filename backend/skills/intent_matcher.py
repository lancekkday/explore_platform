import json
import re
import os
from loguru import logger

# Helper class to match keywords and destination/categories based on PRD logic
class IntentMatcher:
    def __init__(self, dest_dump_dir):
        """
        初始化比對器。載入目的地 mapping 與 Category mapping。
        """
        self.dest_dump_dir = dest_dump_dir
        self.dest_codes = set()
        self.load_destinations()
        
        # PRD mappings
        self.CATEGORY_MAPPING = {
            "一日遊": "CATEGORY_020",
            "半日遊": "CATEGORY_021",
            "多日遊": "CATEGORY_022",
            "觀光行程": "CATEGORY_019",
            "景點門票": "CATEGORY_001",
            "行程": "CATEGORY_018",
            "體驗": "CATEGORY_018",
            "美食": "CATEGORY_125",
            "自助餐": "CATEGORY_134",
            "esim": "CATEGORY_081", # Updated based on actual API data
            "sim": "CATEGORY_081",
            "wifi": "CATEGORY_081"
        }
        
        # Broad category expansions logic
        self.BROAD_CATEGORIES = {
            "一日遊": ["CATEGORY_021", "CATEGORY_022", "CATEGORY_019"], # Related tours
            "自助餐": ["CATEGORY_125"], # Food
        }

    def load_destinations(self):
        dest_file = os.path.join(self.dest_dump_dir, 'destination_code.json')
        if os.path.exists(dest_file):
            try:
                with open(dest_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Parse all valid code and names, simplistic for now
                for item in data.get('data', []):
                    # We would map Chinese names -> code in an ideal case
                    pass
            except Exception as e:
                logger.error(f"Failed to load destinations: {e}")

    def verify(self, product, keyword, ai_metadata=None):
        """
        驗證單個商品的邏輯
        """
        # --- 解析 keyword 的預期地點 & 分類 ---
        if ai_metadata and ai_metadata.get("item"):
             # 使用 AI 解析出來的結果
             expected_cat_name = ai_metadata.get("category")
             expected_dest_name = ai_metadata.get("location")
        else:
             # 原有 Rule-based 解析 (待優化)
             expected_cat_name = None
             for cat in self.CATEGORY_MAPPING.keys():
                 if cat in keyword:
                     expected_cat_name = cat
                     break
             expected_dest_name = keyword.replace(expected_cat_name, "").strip() if expected_cat_name else keyword.strip()

        # --- 商品屬性 ---
        prod_destinations = [d.get("name", "") for d in product.get("destinations", [])]
        prod_main_cat     = product.get("product_category", {}).get("main") or ""
        # 更加強健的提取邏輯：檢查 Root, product_category.key 以及 product_category.main (如果是 CATEGORY_ 開頭)
        prod_cat_key = product.get("main_cat_key") or ""
        pc = product.get("product_category") or {}
        if not prod_cat_key and pc:
            if isinstance(pc.get("main"), str) and pc["main"].startswith("CATEGORY_"):
                prod_cat_key = pc["main"]
            elif pc.get("key"):
                prod_cat_key = pc["key"]

        # --- 地點比對 ---
        dest_match = any(expected_dest_name in d for d in prod_destinations) if expected_dest_name else True

        # --- 分類比對 ---
        cat_match = "n/a"
        is_exact_cat = False
        is_broad_cat = False
        if expected_cat_name:
            exact_cat_code = self.CATEGORY_MAPPING.get(expected_cat_name)
            is_exact_cat = (bool(exact_cat_code) and prod_cat_key == exact_cat_code) or (expected_cat_name in prod_main_cat)
            broad_cats = self.BROAD_CATEGORIES.get(expected_cat_name, [])
            is_broad_cat = prod_cat_key in broad_cats


            if is_exact_cat:
                cat_match = "exact"
            elif is_broad_cat:
                cat_match = "broad"
            else:
                cat_match = "none"

        # --- Tier 判定 ---
        tier = None
        
        # 關鍵字顯性檢查 (Relevance Check)
        # 如果商品標題與簡介完全沒有出現核心關鍵字，強制判定為 Mismatch (或最低 Tier)
        title_intro = (product.get("name", "") + " " + product.get("introduction", "")).lower()
        keyword_low = keyword.lower()
        
        # 如果有 AI 提供的核心產品名詞，優先查核心名詞
        is_keyword_present = keyword_low in title_intro
        
        if expected_cat_name:
            if dest_match and is_exact_cat:
                tier = 1
            elif dest_match and is_broad_cat:
                tier = 2
            elif dest_match:
                tier = 3
        else:
            if dest_match:
                tier = 3

        # --- 強關聯過濾 (針對 esim 等關鍵詞) ---
        # 如果是明確搜尋某個名詞 (如 esim)，但標題完全沒提到，降級為 Mismatch
        if not is_keyword_present and not is_exact_cat:
            tier = None

        # 標題比對 fallback (若原本沒中，但標題有中，至少給 T3)
        if tier is None and is_keyword_present:
            tier = 3
            dest_match = True 

        # --- 組裝 mismatch_reasons ---
        mismatch_reasons = []
        if not dest_match:
            mismatch_reasons.append(f"地點不符 (預期: {expected_dest_name or '—'}, 實際: {', '.join(prod_destinations) or '無'})")
        if cat_match == "none":
            expected_cat_code = self.CATEGORY_MAPPING.get(expected_cat_name, "—")
            mismatch_reasons.append(f"分類不符 (預期: {expected_cat_name}/{expected_cat_code}, 實際: {prod_cat_key or '—'})")

        return {
            "tier": tier,
            "dest_match": dest_match,
            "cat_match": cat_match,
            "mismatch_reasons": mismatch_reasons,
            "expected_dest": expected_dest_name,
            "expected_cat": expected_cat_name or "",
        }
