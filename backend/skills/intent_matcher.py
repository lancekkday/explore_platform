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
        
        # PRD category mappings: keyword → CATEGORY code
        self.CATEGORY_MAPPING = {
            # Tour / 行程
            "一日遊": "CATEGORY_020",
            "半日遊": "CATEGORY_021",
            "多日遊": "CATEGORY_022",
            "觀光行程": "CATEGORY_019",
            "行程": "CATEGORY_018",
            "體驗": "CATEGORY_018",
            "tour": "CATEGORY_020",
            # 門票
            "景點門票": "CATEGORY_001",
            "門票": "CATEGORY_001",
            "ticket": "CATEGORY_001",
            # 美食 / 餐飲（實際 API 資料為 CATEGORY_079）
            "美食": "CATEGORY_079",
            "餐廳": "CATEGORY_079",
            "自助餐": "CATEGORY_079",
            "buffet": "CATEGORY_079",
            "下午茶": "CATEGORY_079",
            # 交通
            "交通": "CATEGORY_120",
            "接送": "CATEGORY_120",
            "接送機": "CATEGORY_120",
            "包車": "CATEGORY_120",
            "新幹線": "CATEGORY_120",
            "jr pass": "CATEGORY_120",
            "jr": "CATEGORY_120",
            "高鐵": "CATEGORY_120",
            # eSIM / 網路
            "esim": "CATEGORY_081",
            "sim": "CATEGORY_081",
            "wifi": "CATEGORY_081",
            "上網": "CATEGORY_081",
        }

        # Theme keywords：主題型搜尋詞，無對應單一 category code，
        # 以名稱/描述中是否出現相關詞彙作為判斷依據
        # 格式：{ 主題詞: [擴展匹配詞列表] }
        self.THEME_KEYWORDS = {
            "滑雪":   ["滑雪", "ski", "雪場", "雪地", "snow"],
            "溫泉":   ["溫泉", "温泉", "露天風呂", "湯", "hot spring"],
            "賞花":   ["賞花", "赏花", "賞櫻", "桜", "sakura", "梅花", "紫藤", "花見"],
            "賞櫻":   ["賞櫻", "賞花", "桜", "sakura", "花見"],
            "漂流":   ["漂流", "泛舟", "泛筏", "激流", "rafting"],
            "泛舟":   ["泛舟", "漂流", "rafting", "kayak"],
            "親子":   ["親子", "兒童", "小孩", "家庭", "family", "kids"],
            "樂園":   ["樂園", "主題樂園", "遊樂園", "theme park", "amusement"],
            "潛水":   ["潛水", "浮潛", "diving", "snorkel"],
            "衝浪":   ["衝浪", "surfing", "surf"],
            "健行":   ["健行", "登山", "步道", "hiking", "trekking"],
            "登山":   ["登山", "健行", "步道", "hiking", "trekking"],
            "露營":   ["露營", "野營", "camping"],
            "夜市":   ["夜市", "night market"],
        }

        # Broad category expansions logic
        self.BROAD_CATEGORIES = {
            "一日遊": ["CATEGORY_021", "CATEGORY_022", "CATEGORY_019"],
            "自助餐": ["CATEGORY_125"],
        }

    def load_destinations(self):
        """
        載入由 JSONL 整合而成的全站目的地大表 (unified_destinations.json)。
        """
        unified_file = os.path.join(os.path.dirname(self.dest_dump_dir), "unified_destinations.json")
        self.name_to_code = {}
        
        if os.path.exists(unified_file):
            try:
                with open(unified_file, 'r', encoding='utf-8') as f:
                    self.name_to_code = json.load(f)
                logger.info(f"Matcher successfully loaded {len(self.name_to_code)} unified destinations.")
            except Exception as e:
                logger.error(f"Failed to load unified destinations: {e}")
        
        # 內建幾個絕對關鍵的關聯 (避免數據漏失)
        self.name_to_code.update({
            "阿里山": "A01-002-00008", # 阿里山門票/小火車 -> 嘉義 code
            "太魯閣": "A01-002-00003", # 花蓮
            "九份": "A01-002-00003",   # 新北/九份
        })

    def _extract_compound_intent(self, keyword):
        """
        嘗試從複合型關鍵字中拆解 destination + category 或 destination + theme。

        例如：
          "泰國esim"   → dest="泰國",  cat="esim",  theme=None
          "東京一日遊"  → dest="東京",  cat="一日遊", theme=None
          "北海道滑雪"  → dest="北海道", cat=None,   theme="滑雪"
          "香港自助餐"  → dest="香港",  cat="自助餐", theme=None

        回傳 (dest_part, cat_keyword, theme_keyword)；
        若無法拆解則回傳 (None, None, None)。
        """
        kw = keyword.strip()

        # 1. 先找 category keyword（從長到短，避免 "自助餐" 被 "餐廳" 誤截）
        for cat_kw in sorted(self.CATEGORY_MAPPING.keys(), key=len, reverse=True):
            if cat_kw in kw and kw != cat_kw:
                dest_part = kw.replace(cat_kw, "").strip()
                if len(dest_part) >= 2:  # 至少 2 字，避免 "esim" → "e" + "sim" 誤截
                    return dest_part, cat_kw, None

        # 2. 再找 theme keyword
        for theme_kw in sorted(self.THEME_KEYWORDS.keys(), key=len, reverse=True):
            if theme_kw in kw and kw != theme_kw:
                dest_part = kw.replace(theme_kw, "").strip()
                if len(dest_part) >= 2:
                    return dest_part, None, theme_kw

        return None, None, None

    def _get_product_cat_code(self, product):
        """從 raw product 正確取出 category code（相容兩種 API 格式）。"""
        pc = product.get("product_category") or {}
        return pc.get("main") or product.get("main_cat_key") or ""

    def _verify_product_keyword(self, product, keyword, ai_category_code=None):
        """
        純商品型關鍵字（esim、sim、wifi 等，不帶地點）的意圖驗證。
        以 category + 關鍵字出現位置 作為主要判斷依據。

        Tier 矩陣：
          T1：正確 category AND keyword 出現於商品名稱
          T2：正確 category 但 keyword 不在名稱，OR keyword 在名稱但 category 不符
          T3：keyword 只出現於描述（introduction）
          T0：keyword 完全未提及
        """
        prod_cat_code = self._get_product_cat_code(product)
        expected_cat_code = ai_category_code or self.CATEGORY_MAPPING.get(keyword, "")

        title = product.get("name", "").lower()
        intro = product.get("introduction", "").lower()

        cat_match = bool(expected_cat_code) and (prod_cat_code == expected_cat_code)
        kw_in_title = keyword in title
        kw_in_intro = keyword in intro

        if cat_match and kw_in_title:
            tier = 1
        elif cat_match or kw_in_title:
            tier = 2
        elif kw_in_intro:
            tier = 3
        else:
            tier = 0

        reasons = []
        if not cat_match and expected_cat_code:
            reasons.append(f"類別不符 (預期: {expected_cat_code}, 實際: {prod_cat_code or '未知'})")
        if not kw_in_title and not kw_in_intro:
            reasons.append(f"商品名稱與描述均未提及關鍵字 '{keyword}'")
        elif not kw_in_title:
            reasons.append(f"關鍵字 '{keyword}' 僅出現於描述中，未出現於商品名稱")

        return {
            "tier": tier,
            "dest_match": True,  # 商品型關鍵字不適用 destination 判斷
            "cat_match": "exact" if cat_match else "none",
            "mismatch_reasons": reasons,
            "expected_dest": None,
            "expected_cat": expected_cat_code,
        }

    def verify(self, product, keyword, ai_metadata=None):
        """
        主驗證入口，支援四種 query 類型：

        Route A — 純 category（esim、美食）：
            keyword 在 CATEGORY_MAPPING 且 AI 無 location → _verify_product_keyword

        Route B — destination + category（泰國esim、東京一日遊）：
            無 AI 時用 _extract_compound_intent 拆解；
            有 AI 且帶 location + category → 直接使用 AI 結果

        Route C — destination + theme（北海道滑雪）：
            無 AI 時拆解 theme；tier 判斷加入 theme 詞彙出現位置

        Route D — 純 destination（日本、九份）：
            原有 destination-based 邏輯
        """
        expected_cat_name = ai_metadata.get("category") if ai_metadata else None
        ai_location      = ai_metadata.get("location")  if ai_metadata else None
        ai_theme         = ai_metadata.get("theme")      if ai_metadata else None
        keyword_lower    = keyword.strip().lower()

        # ── Route A：純 category keyword ──────────────────────────────────
        if keyword_lower in self.CATEGORY_MAPPING and not ai_location:
            ai_cat_code = expected_cat_name if (expected_cat_name and expected_cat_name.startswith("CATEGORY_")) else None
            return self._verify_product_keyword(product, keyword_lower, ai_cat_code)

        # ── 解析 destination / category / theme ───────────────────────────
        if ai_location:
            # AI 已解析：直接使用
            effective_dest  = ai_location
            effective_cat   = expected_cat_name  # 可能是 CATEGORY_xxx 或文字
            effective_theme = ai_theme
        else:
            # 無 AI：嘗試規則拆解複合詞
            dest_part, cat_kw, theme_kw = self._extract_compound_intent(keyword_lower)
            if dest_part:
                effective_dest  = dest_part
                effective_cat   = cat_kw    # 文字 key，下方會轉 code
                effective_theme = theme_kw
            else:
                # 純 destination（無法拆解）
                effective_dest  = keyword_lower
                effective_cat   = None
                effective_theme = None

        # ── Destination 匹配 ───────────────────────────────────────────────
        dests = product.get("destinations") or []
        actual_dest_names, actual_dest_codes = [], []
        for d in dests:
            if isinstance(d, dict):
                actual_dest_names.append(d.get("name", "").lower())
                actual_dest_codes.append(d.get("code", ""))
            else:
                actual_dest_names.append(str(d).lower())

        target_loc = effective_dest.lower()
        dest_match = (
            any(target_loc in n for n in actual_dest_names)
            or self.name_to_code.get(effective_dest) in actual_dest_codes
            or "glb" in actual_dest_codes
        )

        # ── Category 匹配 ──────────────────────────────────────────────────
        prod_cat_code = self._get_product_cat_code(product)
        is_exact_cat  = False
        cat_match     = "n/a"
        if effective_cat:
            if effective_cat.startswith("CATEGORY_"):
                exact_cat_code = effective_cat
            else:
                exact_cat_code = self.CATEGORY_MAPPING.get(effective_cat, "")
            is_exact_cat = bool(exact_cat_code) and (prod_cat_code == exact_cat_code)
            cat_match = "exact" if is_exact_cat else "none"

        # ── Theme 匹配 ─────────────────────────────────────────────────────
        title = product.get("name", "").lower()
        intro = product.get("introduction", "").lower()
        title_intro = title + " " + intro

        theme_in_title = False
        theme_in_intro = False
        if effective_theme:
            theme_terms = self.THEME_KEYWORDS.get(effective_theme, [effective_theme])
            theme_in_title = any(t in title for t in theme_terms)
            theme_in_intro = any(t in intro for t in theme_terms)

        is_keyword_present = target_loc in title_intro

        # ── Tier 判定 ──────────────────────────────────────────────────────
        if dest_match:
            if effective_cat and is_exact_cat:
                # Route B：destination + category 完全符合
                tier = 1
            elif effective_theme:
                # Route C：destination + theme
                if theme_in_title:
                    tier = 1  # dest ✓ + theme 在標題
                elif theme_in_intro:
                    tier = 2  # dest ✓ + theme 在描述
                else:
                    tier = 3  # dest ✓ 但 theme 未提及
            elif is_keyword_present:
                tier = 2
            else:
                tier = 3
        else:
            # dest 不符
            if effective_cat and is_exact_cat:
                tier = 2  # 有正確 category 但地點不對，給 T2
            elif is_keyword_present:
                tier = 3
            else:
                tier = 0

        # 反向校正
        if target_loc == "阿里山" and "西門町" in title_intro and "環島" not in title_intro:
            tier = 0

        reasons = []
        if not dest_match:
            reasons.append(f"地點不符 (預期: {effective_dest}, 實際地點清單不含關鍵地區)")
        if cat_match == "none":
            reasons.append(f"類別不符 (預期: {effective_cat})")
        if effective_theme and not theme_in_title and not theme_in_intro:
            reasons.append(f"主題不符 (預期: {effective_theme}, 商品名稱與描述未提及)")

        return {
            "tier": tier,
            "dest_match": dest_match,
            "cat_match": cat_match,
            "mismatch_reasons": reasons,
            "expected_dest": effective_dest,
            "expected_cat": effective_cat,
            "expected_theme": effective_theme,
        }
