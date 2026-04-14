import json
import os
import threading
import time
import sqlite3
from datetime import datetime, timedelta, timezone
from loguru import logger

TZ_TAIPEI = timezone(timedelta(hours=8))  # UTC+8, no system tzdata needed

from kkday_api import fetch_kkday_products
from skills.metrics import compute_ndcg, compute_recall_stats, compute_category_distribution
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager
from skills.data_sanitizer import sanitizer

# ─── Configuration (STABLE PATHS) ───────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

BATCH_STATE_FILE = os.path.join(DATA_DIR, "batch_state.json")
KEYWORDS_FILE = os.path.join(DATA_DIR, "keywords.json")
DB_PATH = os.path.join(DATA_DIR, "history.db")


class BatchEngine:
    def __init__(self):
        self.is_running = False
        self.progress = 0  # 0 to 100
        self.current_keyword = None
        self.results = {}  # keyword -> results
        self.keyword_list = []
        self.load_keywords()
        self._init_db()
        self.load_state()

    def _init_db(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            # 批次會話表 (維持現狀用於回顧整批結果)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS inspection_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    keyword_count INTEGER,
                    avg_ndcg_10 REAL,
                    results_json TEXT,
                    keywords_json TEXT
                )
            ''')
            # 新增單次紀錄表 (記錄每一發手動點擊)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS single_inspections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT,
                    timestamp TEXT,
                    ndcg_10 REAL,
                    mismatch REAL,
                    data_json TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS batch_schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    freq TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    minute INTEGER NOT NULL DEFAULT 0,
                    day_of_week TEXT,
                    env TEXT DEFAULT 'stage',
                    ai_enabled INTEGER DEFAULT 0,
                    slack_notify INTEGER DEFAULT 0,
                    auto_diff INTEGER DEFAULT 0,
                    enabled INTEGER DEFAULT 1,
                    last_run TEXT,
                    next_run TEXT,
                    created_at TEXT,
                    keywords_json TEXT
                )
            ''')
            # Add keywords_json column if it doesn't exist (migration for existing DBs)
            try:
                cur.execute("ALTER TABLE batch_schedule ADD COLUMN keywords_json TEXT")
                conn.commit()
            except Exception:
                pass  # Column already exists
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB Init Failed: {e}")

    def save_single_record(self, keyword, results):
        """
        記錄單次手動巡檢到資料庫。
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            m = results.get("stage", {}).get("metrics", {}) or results.get("metrics", {})
            ndcg = m.get("ndcg_10") or m.get("ndcg_at_10") or 0
            mismatch = m.get("mismatch_rate") or 0
            
            cur.execute(
                "INSERT INTO single_inspections (keyword, timestamp, ndcg_10, mismatch, data_json) VALUES (?, ?, ?, ?, ?)",
                (keyword, datetime.now(TZ_TAIPEI).isoformat(), ndcg, mismatch, json.dumps(results, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Single Save Failed: {e}")

    def load_keywords(self):
        if os.path.exists(KEYWORDS_FILE):
            try:
                with open(KEYWORDS_FILE, "r") as f:
                    self.keyword_list = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load keywords from {KEYWORDS_FILE}: {e}")
                self.keyword_list = []

    def save_keywords(self, keywords):
        new_list = []
        for kw in keywords:
            if isinstance(kw, str):
                new_list.append({"keyword": kw, "ai_enabled": True})
            else:
                new_list.append(kw)
        
        self.keyword_list = new_list
        try:
            with open(KEYWORDS_FILE, "w") as f:
                json.dump(new_list, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save keywords: {e}")

    def load_state(self):
        if os.path.exists(BATCH_STATE_FILE):
            try:
                with open(BATCH_STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.results = data.get("results", {})
                    self.progress = data.get("progress", 0)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load batch state from {BATCH_STATE_FILE}: {e}")

    def save_state(self):
        try:
            with open(BATCH_STATE_FILE, "w") as f:
                json.dump({
                    "last_updated": datetime.now(TZ_TAIPEI).isoformat(),
                    "progress": self.progress,
                    "results": self.results
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save batch state: {e}")

    def _slim_for_batch(self, p, rank, judgement):
        """
        使用 DataSanitizer 將 API 回傳的原始商品數據進行結構化與清洗。
        """
        # 提取分類 code 與目的地
        cat_name = sanitizer.get_category_key(p)
        destinations = sanitizer.get_destinations(p)

        # 判定結果解構
        tier_val = 0
        mismatch_reasons = []
        if isinstance(judgement, dict):
            tier_val = judgement.get("tier", 0)
            mismatch_reasons = judgement.get("mismatch_reasons", [])

        return {
            "rank": rank,
            "id": str(p.get("prod_oid") or p.get("oid") or p.get("product_id") or rank),
            "name": p.get("name", ""),
            "img_url": p.get("img_url", ""),
            "url": p.get("url", ""),
            "tier": tier_val,
            "mismatch_reasons": mismatch_reasons,
            "main_cat_key": cat_name,
            "destinations": destinations,
            "rank_delta": None
        }

    def process_keyword(self, keyword_obj, cookie):
        keyword = keyword_obj["keyword"]
        ai_enabled = keyword_obj.get("ai_enabled", False)
        logger.info(f"[Batch] Starting Task: {keyword}")
        
        try:
            ai_metadata = judger.get_ai_metadata(keyword, ai_enabled=ai_enabled)
            s_prods, s_total, _ = fetch_kkday_products(keyword, "stage", cookie, 300)
            # Production disabled (Datadome blocks prod API)
            p_prods, p_total = [], 0

            s_res = []
            for i, p in enumerate(s_prods):
                try:
                    judgement = judger.judge_product(p, keyword, ai_metadata)
                    s_res.append(self._slim_for_batch(p, i+1, judgement))
                except Exception:
                    s_res.append(self._slim_for_batch(p, i+1, {"tier": 0}))

            p_res = []

            calibration_manager.apply_overrides(keyword, s_res)

            s_stats = compute_recall_stats(s_res)
            p_stats = compute_recall_stats(p_res)

            return {
                "keyword": keyword,
                "ai_enabled": ai_enabled,
                "timestamp": datetime.now(TZ_TAIPEI).isoformat(),
                "stage": {
                    "total": s_total,
                    "results": s_res,
                    "metrics": {
                        "ndcg_10": compute_ndcg(s_res, 10),
                        "ndcg_50": compute_ndcg(s_res, 50),
                        "ndcg_150": compute_ndcg(s_res, 150),
                        **s_stats,
                    }
                },
                "production": {
                    "total": p_total,
                    "results": p_res,
                    "metrics": {
                        "ndcg_10": compute_ndcg(p_res, 10),
                        "ndcg_50": compute_ndcg(p_res, 50),
                        "ndcg_150": compute_ndcg(p_res, 150),
                        **p_stats,
                    }
                }
            }
        except Exception as e:
            logger.error(f"[Batch] Error during {keyword}: {e}")
            return {
                "keyword": keyword, "error": str(e),
                "stage": {"total": 0, "results": [], "metrics": {"ndcg_10": 0, "mismatch_rate": 1.0}},
                "production": {"total": 0, "results": [], "metrics": {"ndcg_10": 0, "mismatch_rate": 1.0}}
            }

    def run_batch_sync(self, cookie, ai_enabled_override=None, keyword_list_override=None):
        """
        Run a batch synchronously in the calling thread.
        Used by APScheduler (which already provides a worker thread) so that
        post-batch actions (last_run update, Slack notify) only fire after
        the batch truly completes.
        Returns False if a batch is already running, True otherwise.
        """
        if self.is_running:
            return False
        self.is_running = True
        self.progress = 0
        self.results = {}
        self.save_state()
        active_list = keyword_list_override if keyword_list_override is not None else self.keyword_list
        total_count = len(active_list)
        if total_count == 0:
            self.is_running = False
            return True
        try:
            for i, kw_obj in enumerate(active_list):
                if not self.is_running:
                    break
                kw_str = kw_obj["keyword"]
                norm_key = kw_str.strip().lower()
                self.current_keyword = kw_str
                effective_kw_obj = kw_obj if ai_enabled_override is None else {**kw_obj, "ai_enabled": ai_enabled_override}
                res = self.process_keyword(effective_kw_obj, cookie)
                if res:
                    self.results[norm_key] = res
                self.progress = int(((i + 1) / total_count) * 100)
                self.save_state()
                time.sleep(0.5)
        finally:
            self.is_running = False
            self.current_keyword = None
        self.save_history_record()
        logger.info(f"[Batch] Finished {total_count} tasks. Saved record.")
        return True

    def run_batch(self, cookie, ai_enabled_override=None, keyword_list_override=None):
        """Start a batch in a background daemon thread (used by manual API trigger)."""
        if self.is_running:
            return
        threading.Thread(
            target=self.run_batch_sync,
            args=(cookie, ai_enabled_override, keyword_list_override),
            daemon=True,
        ).start()

    def save_history_record(self):
        if not self.results: return
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            kw_count = len(self.results)
            all_ndcg = [r.get("stage", {}).get("metrics", {}).get("ndcg_10", 0) for r in self.results.values()]
            avg_ndcg = sum(all_ndcg) / kw_count if kw_count > 0 else 0
            cur.execute(
                "INSERT INTO inspection_history (timestamp, keyword_count, avg_ndcg_10, results_json, keywords_json) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(TZ_TAIPEI).isoformat(), kw_count, avg_ndcg,
                 json.dumps(self.results, ensure_ascii=False),
                 json.dumps(list(self.results.keys()), ensure_ascii=False))
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Archive Failed: {e}")

    def get_history_list(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, timestamp, keyword_count, avg_ndcg_10, keywords_json FROM inspection_history ORDER BY id DESC LIMIT 50")
            rows = cur.fetchall()
            conn.close()
            result = []
            for r in rows:
                try:
                    keywords = json.loads(r[4] or "[]")
                except Exception:
                    keywords = []
                result.append({"id": r[0], "timestamp": r[1], "count": r[2], "avg_ndcg": r[3], "keywords": keywords})
            return result
        except Exception as e:
            logger.error(f"History Fetch Failed: {e}")
            return []

    def get_history_detail(self, history_id):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT results_json FROM inspection_history WHERE id=?", (history_id,))
            row = cur.fetchone()
            conn.close()
            return json.loads(row[0]) if row else None
        except Exception as e:
            logger.error(f"Detail Fetch Failed: {e}")
            return None

    def get_single_history(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, keyword, timestamp, ndcg_10, mismatch FROM single_inspections ORDER BY id DESC LIMIT 50")
            rows = cur.fetchall()
            conn.close()
            return [{"id": r[0], "keyword": r[1], "timestamp": r[2], "ndcg": r[3], "mismatch": r[4]} for r in rows]
        except Exception as e:
            logger.error(f"Single History Fetch Failed: {e}")
            return []

    def get_single_detail(self, inspection_id):
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT data_json FROM single_inspections WHERE id=?", (inspection_id,))
            row = cur.fetchone()
            conn.close()
            return json.loads(row[0]) if row else None
        except Exception as e:
            logger.error(f"Single Detail Fetch Failed: {e}")
            return None

    def stop_batch(self):
        self.is_running = False

    # ── Schedule CRUD ────────────────────────────────────────────────────────

    def list_schedules(self) -> list:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT id, freq, hour, minute, day_of_week, env, ai_enabled, slack_notify, auto_diff, enabled, last_run, next_run, created_at, keywords_json FROM batch_schedule ORDER BY id ASC")
            rows = cur.fetchall()
            conn.close()
            cols = ["id","freq","hour","minute","day_of_week","env","ai_enabled","slack_notify","auto_diff","enabled","last_run","next_run","created_at","keywords_json"]
            result = []
            for r in rows:
                d = dict(zip(cols, r))
                # Parse keywords_json into a list for convenience
                if d.get("keywords_json"):
                    try:
                        d["keywords"] = json.loads(d["keywords_json"])
                    except Exception:
                        d["keywords"] = []
                else:
                    d["keywords"] = []
                result.append(d)
            return result
        except Exception as e:
            logger.error(f"list_schedules failed: {e}")
            return []

    def add_schedule(self, freq, hour, minute, day_of_week, env, ai_enabled, slack_notify, auto_diff, keywords=None) -> int:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            kw_json = json.dumps(keywords, ensure_ascii=False) if keywords else None
            cur.execute(
                "INSERT INTO batch_schedule (freq, hour, minute, day_of_week, env, ai_enabled, slack_notify, auto_diff, enabled, created_at, keywords_json) VALUES (?,?,?,?,?,?,?,?,1,?,?)",
                (freq, hour, minute, day_of_week, env, int(ai_enabled), int(slack_notify), int(auto_diff), datetime.now(TZ_TAIPEI).isoformat(), kw_json)
            )
            new_id = cur.lastrowid
            conn.commit()
            conn.close()
            return new_id
        except Exception as e:
            logger.error(f"add_schedule failed: {e}")
            return -1

    def update_schedule(self, schedule_id: int, **fields) -> None:
        allowed = {"freq","hour","minute","day_of_week","env","ai_enabled","slack_notify","auto_diff","enabled","last_run","next_run","keywords_json"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        try:
            conn = sqlite3.connect(DB_PATH)
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE batch_schedule SET {set_clause} WHERE id=?", (*updates.values(), schedule_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"update_schedule failed: {e}")

    def delete_schedule(self, schedule_id: int) -> None:
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM batch_schedule WHERE id=?", (schedule_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"delete_schedule failed: {e}")

    def update_last_run(self, schedule_id: int, next_run: str) -> None:
        self.update_schedule(schedule_id, last_run=datetime.now(TZ_TAIPEI).isoformat(), next_run=next_run)

engine = BatchEngine()
