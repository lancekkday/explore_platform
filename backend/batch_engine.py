import json
import os
import threading
import time
from datetime import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

from kkday_api import fetch_kkday_products
from skills.metrics import compute_ndcg, compute_recall_stats, compute_category_distribution
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager

# ─── Configuration ──────────────────────────────────────────────────────────
DATA_DIR = "backend/data"
os.makedirs(DATA_DIR, exist_ok=True)
BATCH_STATE_FILE = os.path.join(DATA_DIR, "batch_state.json")
KEYWORDS_FILE = os.path.join(DATA_DIR, "keywords.json")


class BatchEngine:
    def __init__(self):
        self.is_running = False
        self.progress = 0  # 0 to 100
        self.current_job = None
        self.results = {}  # keyword -> results
        self.keyword_list = []
        self.load_keywords()
        self.load_state()

    def load_keywords(self):
        if os.path.exists(KEYWORDS_FILE):
            try:
                with open(KEYWORDS_FILE, "r") as f:
                    self.keyword_list = json.load(f)
            except:
                self.keyword_list = []

    def save_keywords(self, keywords):
        # 傳入的是清單 (可以是字串清單或物件清單)
        new_list = []
        for kw in keywords:
            if isinstance(kw, str):
                # 簡單自動偵測：無地點關鍵字預設啟動 AI
                # 使用 IntentMatcher 快速判斷，或直接交給 AI
                new_list.append({"keyword": kw, "ai_enabled": True})
            else:
                new_list.append(kw)
        
        self.keyword_list = new_list
        with open(KEYWORDS_FILE, "w") as f:
            json.dump(new_list, f, indent=2, ensure_ascii=False)

    def load_state(self):
        if os.path.exists(BATCH_STATE_FILE):
            try:
                with open(BATCH_STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.results = data.get("results", {})
                    self.progress = data.get("progress", 0)
            except:
                pass

    def save_state(self):
        with open(BATCH_STATE_FILE, "w") as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "progress": self.progress,
                "results": self.results
            }, f, indent=2, ensure_ascii=False)

    def _slim_for_batch(self, p, rank, result):
        """用於 Bulk 視圖的極簡結構，只存關鍵指標"""
        pc = p.get("product_category") or {}
        cat_code = p.get("main_cat_key") or ""
        if not cat_code and pc:
            if isinstance(pc.get("main"), str) and pc["main"].startswith("CATEGORY_"):
                cat_code = pc["main"]
            elif pc.get("key"):
                cat_code = pc["key"]
        
        # 僅保留核心比對結果，不存 Name/IMG/URL 以節省大量空間
        return {
            "id": str(p.get("oid") or p.get("product_id") or rank),
            "tier": result["tier"],
            "main_cat_key": cat_code,
        }

    def process_keyword(self, keyword_obj, cookie):
        keyword = keyword_obj["keyword"]
        ai_enabled = keyword_obj.get("ai_enabled", False)
        
        logger.info(f"[Batch] Processing: {keyword} (AI: {ai_enabled})")
        
        ai_metadata = judger.get_ai_metadata(keyword, ai_enabled=ai_enabled)

        try:
            # Fetch Both 
            s_prods, s_total, _ = fetch_kkday_products(keyword, "stage",      cookie, 300)
            p_prods, p_total, _ = fetch_kkday_products(keyword, "production", cookie, 300)

            # Build slim results
            s_res = []
            for i, p in enumerate(s_prods):
                # We use judge_product here because _slim_for_batch is specific to BatchEngine
                judgement = judger.judge_product(p, keyword, ai_metadata)
                s_res.append(self._slim_for_batch(p, i+1, judgement))
                
            p_res = []
            for i, p in enumerate(p_prods):
                judgement = judger.judge_product(p, keyword, ai_metadata)
                p_res.append(self._slim_for_batch(p, i+1, judgement))

            # IMPORTANT: Apply Manual Calibration Overrides BEFORE computing metrics
            calibration_manager.apply_overrides(keyword, s_res)
            calibration_manager.apply_overrides(keyword, p_res)

            # Compute Summary Metrics (based on calibrated tiers)
            res = {
                "keyword": keyword,
                "ai_enabled": ai_enabled,
                "timestamp": datetime.now().isoformat(),
                "stage": {
                    "total": s_total,
                    "ndcg_10": compute_ndcg(s_res, 10),
                    "ndcg_50": compute_ndcg(s_res, 50),
                    "ndcg_300": compute_ndcg(s_res, 300),
                    "mismatch_rate": compute_recall_stats(s_res)["mismatch_rate"]
                },
                "production": {
                    "total": p_total,
                    "ndcg_10": compute_ndcg(p_res, 10),
                    "ndcg_50": compute_ndcg(p_res, 50),
                    "ndcg_300": compute_ndcg(p_res, 300),
                    "mismatch_rate": compute_recall_stats(p_res)["mismatch_rate"]
                }
            }
            return res
        except Exception as e:
            logger.error(f"[Batch] Failed: {keyword} -> {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def run_batch(self, cookie):
        if self.is_running:
            return
        
        def _worker():
            self.is_running = True
            self.progress = 0
            total_count = len(self.keyword_list)
            
            if total_count == 0:
                self.is_running = False
                return

            for i, kw_obj in enumerate(self.keyword_list):
                if not self.is_running: break
                
                kw_str = kw_obj["keyword"]
                res = self.process_keyword(kw_obj, cookie)
                if res:
                    self.results[kw_str] = res
                
                self.progress = int(((i + 1) / total_count) * 100)
                self.save_state()
                
                # Small gap to avoid WAF
                time.sleep(1)

            self.is_running = False
            logger.info("[Batch] Completed all keywords")

        threading.Thread(target=_worker, daemon=True).start()

    def stop_batch(self):
        self.is_running = False

engine = BatchEngine()
