import glob
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
            # 住宿 / 旅館（CATEGORY_078）
            "住宿": "CATEGORY_078",
            "旅館": "CATEGORY_078",
            "飯店": "CATEGORY_078",
            "民宿": "CATEGORY_078",
            "酒店": "CATEGORY_078",
            "hotel": "CATEGORY_078",
            "villa": "CATEGORY_078",
            # 高鐵假期套裝（CATEGORY_057）—— 長詞需在「高鐵」之前，sorted by len 已保證
            "高鐵假期": "CATEGORY_057",
            "高鐵旅遊": "CATEGORY_057",
            "高鐵套票": "CATEGORY_057",
            "高鐵套裝": "CATEGORY_057",
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
        # 當搜尋 category 不完全符合但「語意相關」時，給 T2 而非 T3
        self.BROAD_CATEGORIES = {
            "一日遊": ["CATEGORY_021", "CATEGORY_022", "CATEGORY_019"],
            "自助餐": ["CATEGORY_079"],
            # 住宿：高鐵假期（CATEGORY_057）含住宿元素，搜「台中住宿」出現屬合理相關
            "住宿":   ["CATEGORY_057"],
            "旅館":   ["CATEGORY_057"],
            "飯店":   ["CATEGORY_057"],
            "民宿":   ["CATEGORY_057"],
            "酒店":   ["CATEGORY_057"],
        }

    # 國家名稱 → ISO 代碼（用於 country-level dest 比對，搜「日本」命中所有日本商品）
    COUNTRY_ISO_MAP = {
        "日本": "JP", "台灣": "TW", "台湾": "TW", "韓國": "KR", "韓国": "KR",
        "泰國": "TH", "泰国": "TH", "新加坡": "SG", "馬來西亞": "MY", "馬来西亚": "MY",
        "香港": "HK", "澳門": "MO", "澳门": "MO", "越南": "VN", "菲律賓": "PH", "菲律宾": "PH",
        "印尼": "ID", "印度": "IN", "美國": "US", "英國": "GB", "法國": "FR",
        "德國": "DE", "義大利": "IT", "西班牙": "ES", "葡萄牙": "PT",
        "澳洲": "AU", "紐西蘭": "NZ", "中國": "CN", "中国": "CN",
    }

    # 城市名稱 → ISO 代碼（僅用於 same_country 同國異城偵測，不影響 dest_match）
    # 補充 unified_destinations 缺少中文 mapping 的常見城市
    CITY_ISO_MAP = {
        # 韓國
        "首爾": "KR", "釜山": "KR", "濟州": "KR", "濟州島": "KR",
        "仁川": "KR", "大邱": "KR", "光州": "KR", "大田": "KR",
        # 泰國
        "曼谷": "TH", "清邁": "TH", "普吉": "TH", "芭提雅": "TH", "清萊": "TH",
        # 越南
        "河內": "VN", "胡志明市": "VN", "峴港": "VN", "芽莊": "VN", "會安": "VN",
        # 菲律賓
        "馬尼拉": "PH", "宿霧": "PH", "長灘島": "PH", "薄荷島": "PH",
        # 印尼
        "峇里島": "ID", "巴里島": "ID", "雅加達": "ID", "日惹": "ID",
        # 馬來西亞
        "吉隆坡": "MY", "檳城": "MY", "古晉": "MY", "亞庇": "MY", "蘭卡威": "MY",
    }

    def load_destinations(self):
        """
        載入目的地資料：
        1. unified_destinations.json (name → code 快速查詢)
        2. be2_destinations_dump/my_run JSONL (建立 code_to_parent 階層樹 + code_to_iso，
           用於比對「同國家 ancestor」邏輯)
        """
        # ── 1. unified name→code mapping ──────────────────────────────────
        unified_file = os.path.join(self.dest_dump_dir, "unified_destinations.json")
        self.name_to_code = {}

        if os.path.exists(unified_file):
            try:
                with open(unified_file, 'r', encoding='utf-8') as f:
                    self.name_to_code = json.load(f)
                logger.info(f"Matcher loaded {len(self.name_to_code)} unified destinations.")
            except Exception as e:
                logger.error(f"Failed to load unified destinations: {e}")

        # ── 2. 階層 code_to_parent + code_to_iso（從 JSONL dump 建立）──────
        self.code_to_parent: dict[str, str] = {}
        self.code_to_iso: dict[str, str] = {}
        dump_base = os.path.join(self.dest_dump_dir, "be2_destinations_dump", "my_run")
        if os.path.exists(dump_base):
            jsonl_files = glob.glob(os.path.join(dump_base, "**", "destinations.jsonl"), recursive=True)
            loaded = 0
            for path in jsonl_files:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            obj = json.loads(line)
                            code   = obj.get("code")
                            parent = obj.get("parentCode")
                            iso    = obj.get("isoCountryCode")
                            if code and parent:
                                self.code_to_parent[code] = parent
                            if code and iso:
                                self.code_to_iso[code] = iso
                            loaded += 1
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
            logger.info(f"Matcher loaded hierarchy: {len(self.code_to_parent)} parent links, "
                        f"{len(self.code_to_iso)} ISO mappings from {len(jsonl_files)} JSONL files.")
        else:
            logger.warning(f"Destination dump not found at {dump_base}; hierarchy matching disabled.")

        # 內建幾個絕對關鍵的關聯 (避免數據漏失)
        self.name_to_code.update({
            "阿里山": "A01-002-00008", # 嘉義
            "太魯閣": "A01-002-00003", # 花蓮
            "九份":   "A01-002-00001", # 新北
        })

        # 子字串 fallback 用的排序 key 列表：長名稱優先，確保「北海道」先於「海道」命中
        # 只在 load_destinations 結束時建立一次（O(N log N)），之後 _resolve_search_code 直接用
        self._sorted_dest_names: list[str] = sorted(
            self.name_to_code.keys(), key=len, reverse=True
        )

        # search_code 解析結果快取（effective_dest → code）
        # 同一個搜尋詞在 300 個商品的批次中只需計算一次
        self._search_code_cache: dict[str, str | None] = {}

    def _resolve_search_code(self, effective_dest: str) -> str | None:
        """
        將搜尋地點詞解析為 destination code，結果快取避免重複 O(N) 遍歷。

        查找順序：
        1. 快取命中 → 直接回傳
        2. name_to_code 直接 lookup（O(1)）
        3. 子字串 fallback：找 name_to_code 中是 effective_dest 子字串的 key（O(N)，只跑一次）
           例：「濟州島」→ 找到「濟州」→ 回傳其 code
        """
        if effective_dest in self._search_code_cache:
            return self._search_code_cache[effective_dest]

        code = self.name_to_code.get(effective_dest)
        if not code:
            # 按長度降序遍歷，確保最長（最具體）地名優先命中
            for name in self._sorted_dest_names:
                if len(name) >= 2 and name in effective_dest:
                    code = self.name_to_code[name]
                    break

        self._search_code_cache[effective_dest] = code
        return code

    def _get_ancestors(self, code: str) -> set:
        """回傳某 code 的所有 ancestor codes（向上走到 root）。"""
        ancestors = set()
        current = self.code_to_parent.get(code)
        seen = set()
        while current and current not in seen:
            seen.add(current)
            ancestors.add(current)
            current = self.code_to_parent.get(current)
        return ancestors

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
        title_intro_for_dest = product.get("name", "").lower() + " " + product.get("introduction", "").lower()
        dest_match = (
            any(target_loc in n for n in actual_dest_names)
            # 反向子字串：destination name 是搜尋詞的子集（如搜「濟州島」，dest 為「濟州」）
            or any(n in target_loc for n in actual_dest_names if len(n) >= 2)
            or self.name_to_code.get(effective_dest) in actual_dest_codes
            or "glb" in actual_dest_codes
            # 商品名稱或描述中直接包含目標地點（例如搜尋「日本」可命中「KDDI 日本 eSIM」）
            or target_loc in title_intro_for_dest
        )

        # ── 階層式地點比對 + 同國異城偵測 ────────────────────────────────
        # Case A：product destination 是搜尋地點的 ancestor（product 範圍較廣，含搜尋城市）
        # Case B：搜尋地點是 product destination 的 ancestor（搜尋範圍較廣，product 在其下）
        # Case C：搜尋詞是國家名稱（如「日本」），用 ISO code 對比商品所在國是否相同
        # Case D：同國異城（如搜「濟州島」出現首爾）→ same_country=True，最終給 T3
        same_country = False  # 同國異城旗標
        if not dest_match and actual_dest_codes:
            search_code = self._resolve_search_code(effective_dest)

            if search_code:
                search_ancestors = self._get_ancestors(search_code)
                for prod_code in actual_dest_codes:
                    if not prod_code:
                        continue
                    if prod_code in search_ancestors:
                        dest_match = True
                        break
                    if search_code in self._get_ancestors(prod_code):
                        dest_match = True
                        break
                # hierarchy 仍失敗 → 檢查是否同國（同 ISO code）→ 降級 T3
                if not dest_match:
                    search_iso = self.code_to_iso.get(search_code)
                    if search_iso:
                        for prod_code in actual_dest_codes:
                            if self.code_to_iso.get(prod_code) == search_iso:
                                same_country = True
                                break
            else:
                # search_code 查不到
                # 1. 嘗試用國家 ISO code 比對（例：日本 → JP）→ dest_match=True
                search_iso = self.COUNTRY_ISO_MAP.get(effective_dest)
                if search_iso:
                    for prod_code in actual_dest_codes:
                        if self.code_to_iso.get(prod_code) == search_iso:
                            dest_match = True
                            break
                # 2. 嘗試城市 ISO map（例：濟州島 → KR）→ 只設 same_country，不影響 dest_match
                if not dest_match:
                    search_iso = self.CITY_ISO_MAP.get(effective_dest)
                    if search_iso:
                        for prod_code in actual_dest_codes:
                            if self.code_to_iso.get(prod_code) == search_iso:
                                same_country = True
                                break

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

        # ── Broad category 比對（語意相關，非完全符合）──────────────────────
        broad_cats = self.BROAD_CATEGORIES.get(effective_cat, []) if effective_cat else []
        is_broad_cat = prod_cat_code in broad_cats

        # ── Tier 判定 ──────────────────────────────────────────────────────
        if dest_match:
            if effective_cat and is_exact_cat:
                # Route B：destination + category 完全符合
                tier = 1
            elif effective_cat and is_broad_cat:
                # Route B'：destination ✓ + 寬鬆相關 category（如搜住宿出現高鐵假期）→ T2
                tier = 2
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
            elif same_country:
                tier = 3  # 同國異城（如搜濟州出現首爾、搜台中出現台南）→ 鬆散相關
            else:
                tier = 0

        # 反向校正：已知誤判規則
        # 阿里山搜尋會因 destination code 命中嘉義，導致「台北西門町」商品被錯誤拉高 tier。
        # 排除條件：商品提及西門町但未提及環島（環島行程可能合理途經嘉義/阿里山）。
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
