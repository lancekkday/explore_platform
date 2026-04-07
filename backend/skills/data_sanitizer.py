import os
import json
from loguru import logger

class DataSanitizer:
    def __init__(self, unified_file):
        self.code_to_name = {}
        if os.path.exists(unified_file):
            try:
                with open(unified_file, 'r', encoding='utf-8') as f:
                    name_to_code = json.load(f)
                    # 建立反向索引：Code -> Name (取第一個出現的)
                    for name, code in name_to_code.items():
                        if code not in self.code_to_name:
                            self.code_to_name[code] = name
                logger.info(f"Sanitizer loaded {len(self.code_to_name)} code-to-name mappings.")
            except Exception as e:
                logger.error(f"Sanitizer init failed: {e}")

    def get_destinations(self, p):
        """
        全方位目的地解析：解析物件、字串並進行代碼反查。
        """
        raw = p.get("destinations", [])
        if not raw:
            return [{"name": "GLOBAL"}]
            
        results = []
        for item in raw:
            # 模式 A: 已是物件
            if isinstance(item, dict):
                name = item.get("name") or item.get("city_name") or item.get("country_name")
                code = item.get("code") or item.get("city_code")
                # 如果名字沒了但有 code，嘗試反查
                if not name and code and code in self.code_to_name:
                    name = self.code_to_name[code]
                if name:
                    results.append({"name": name, "code": code or ""})
            
            # 模式 B: 純字串 (可能是代碼或名稱)
            elif isinstance(item, str):
                val = item.strip()
                if val:
                    # 如果長得很像代碼 (例如 D-TW-...)，嘗試反查
                    if val.startswith("D-") or "-" in val:
                         name = self.code_to_name.get(val, val)
                         results.append({"name": name, "code": val})
                    else:
                         results.append({"name": val, "code": ""})
                         
        return results if results else [{"name": "GLOBAL"}]

    def get_category(self, p):
        """
        智慧分類提取。
        """
        outer_name = p.get("main_cat_name")
        pc = p.get("product_category", {})
        inner_name = pc.get("name") if isinstance(pc, dict) else None
        
        # 優先回傳最具體的名字
        return inner_name or outer_name or p.get("main_cat_key") or "UNSPECIFIED"

# 初始化全局實例 (假設路徑)
sanitizer = DataSanitizer(os.path.join(os.path.dirname(__file__), "..", "data", "unified_destinations.json"))
