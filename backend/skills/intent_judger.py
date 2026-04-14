import sqlite3
import os
from datetime import datetime, timedelta, timezone

TZ_TAIPEI = timezone(timedelta(hours=8))
from typing import Optional, Dict, List, Any, TypedDict
from skills.ai_agent import parse_intent_with_ai
from skills.intent_matcher import IntentMatcher
from skills.calibration_manager import calibration_manager
from loguru import logger

# Initialize underlying rule-based matcher
# DEST_DUMP_DIR: local dev points to Search_data dump; Docker uses /app/data
DEST_DUMP_DIR = os.getenv("DEST_DUMP_DIR", os.path.join(os.path.dirname(__file__), "../../data"))
MATCHER = IntentMatcher(DEST_DUMP_DIR)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "history.db")

class VerificationResult(TypedDict):
    """Result of search intent verification."""
    tier: int
    mismatch_reasons: List[str]
    cat_match: str
    dest_match: bool
    expected_dest: Optional[str]
    actual_dest: List[str]

class IntentJudger:
    def __init__(self):
        self.matcher = MATCHER
        self._ensure_usage_table()

    def _ensure_usage_table(self):
        """Create ai_usage_log table if it doesn't exist."""
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ai_usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to create ai_usage_log table: {e}")

    def _log_ai_usage(self, keyword: str, trigger_reason: str, usage: dict):
        """Persist one AI call's usage to the database."""
        if usage.get("total_tokens", 0) == 0:
            return  # Skip logging failed / zero-usage calls
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO ai_usage_log (timestamp, keyword, trigger_reason, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd) VALUES (?,?,?,?,?,?,?)",
                (
                    datetime.now(TZ_TAIPEI).isoformat(),
                    keyword,
                    trigger_reason,
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                    usage["total_tokens"],
                    usage["estimated_cost_usd"],
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to log AI usage: {e}")

    def _rules_can_handle(self, keyword: str) -> bool:
        """
        Returns True if the rule-based system can fully resolve this keyword
        without AI assistance:
          - Pure category keyword (esim, wifi, 門票, jr pass …)
          - Compound keyword that _extract_compound_intent can split
          - Pure destination keyword (anything >= 2 chars that maps to a dest)
        AI is only needed when the keyword is ambiguous / unknown to the rules.
        """
        kw = keyword.strip().lower()
        if kw in self.matcher.CATEGORY_MAPPING:
            return True
        dest, cat, theme = self.matcher._extract_compound_intent(kw)
        if dest:
            return True
        # Pure destination: at least 2 chars, treat as handleable by dest-route
        if len(kw) >= 2:
            return True
        return False

    def get_ai_metadata(self, keyword: str, ai_enabled: bool = False) -> Optional[Dict[str, Any]]:
        """
        Parses a keyword using AI to extract semantic intent.

        Auto-escalates to AI when rules cannot resolve the keyword,
        regardless of the ai_enabled flag.

        Args:
            keyword: The search query string.
            ai_enabled: Explicit opt-in (e.g. from keyword config or UI toggle).

        Returns:
            Dictionary with 'item', 'location', 'category', 'theme' if AI ran, else None.
        """
        rules_ok = self._rules_can_handle(keyword)
        should_use_ai = ai_enabled or not rules_ok

        if not should_use_ai:
            return None

        trigger_reason = "explicit" if ai_enabled else "auto_fallback"

        try:
            ai_res, usage = parse_intent_with_ai(keyword)
            self._log_ai_usage(keyword, trigger_reason, usage)
            return {
                "item": ai_res.core_product,
                "location": ai_res.location,
                "category": ai_res.category,
                "theme": ai_res.theme,
            }
        except Exception as e:
            logger.error(f"AI Parse failed for [{keyword}]: {e}")
            return None

    def judge_product(self, p: Dict[str, Any], keyword: str, ai_metadata: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        Main judgment function for a single product.
        Combines rule-based matching with optional AI intent metadata.
        """
        return self.matcher.verify(p, keyword, ai_metadata)

    def process_and_calibrate(self, p: Dict[str, Any], rank: int, keyword: str, ai_metadata: Optional[Dict[str, Any]], slim_func: Any) -> Dict[str, Any]:
        """
        High-level wrapper for single product processing in the Discovery UI.
        Handles judgment, slimming, and applying manual human calibrations.
        """
        result = self.judge_product(p, keyword, ai_metadata)
        slimmed = slim_func(p, rank, result, keyword)

        fb = calibration_manager.get_correction(keyword, slimmed["id"])
        if fb:
            slimmed["original_tier"] = slimmed["tier"]
            slimmed["tier"] = fb["user_tier"]
            slimmed["user_comment"] = fb["comment"]
            slimmed["is_calibrated"] = True

            if "mismatch_reasons" not in slimmed:
                slimmed["mismatch_reasons"] = []
            slimmed["mismatch_reasons"].insert(0, f"👨‍💻 人工校正: {fb['comment']}")

        return slimmed

judger = IntentJudger()
