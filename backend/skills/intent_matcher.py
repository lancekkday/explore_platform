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
            "esim": "CATEGORY_015" # Assuming some default if not found
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

    def verify(self, product, keyword):
        """
        驗證單個商品的邏輯
        回傳 dict:
          tier: 1 / 2 / 3 / None
          dest_match: bool
          cat_match: 'exact' / 'broad' / 'none' / 'n/a'
          mismatch_reasons: list of str  (空表示完全符合)
          expected_dest: str
          expected_cat: str
        """
        # --- 解析 keyword 的預期地點 & 分類 ---
        expected_cat_name = None
        for cat in self.CATEGORY_MAPPING.keys():
            if cat in keyword:
                expected_cat_name = cat
                break

        expected_dest_name = keyword.replace(expected_cat_name, "").strip() if expected_cat_name else keyword.strip()

        # --- 商品屬性 ---
        prod_destinations = [d.get("name", "") for d in product.get("destinations", [])]
        prod_main_cat     = product.get("product_category", {}).get("main") or ""
        prod_cat_key      = product.get("main_cat_key") or ""

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

        # 標題比對 fallback
        if tier is None and keyword in product.get("name", ""):
            tier = 3
            dest_match = True  # keyword 出現在標題視為隱性地點命中

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
