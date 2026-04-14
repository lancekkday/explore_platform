import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

TZ_TAIPEI = timezone(timedelta(hours=8))
from loguru import logger

DATA_DIR = "backend/data"
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")

class CalibrationManager:
    """
    Manages the persistence of manual product quality ratings (Tiers). 
    Used to correct automated judgments and provide human ground truth.
    """
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.feedback = self.load_feedback()

    def load_feedback(self) -> Dict[str, Dict[str, Any]]:
        """
        Loads the saved calibration feedback from disk.
        Returns: 
            Dict { keyword: { product_id: { user_tier, comment, timestamp } } }
        """
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load feedback: {e}")
                return {}
        return {}

    def save_feedback(self, keyword: str, product_id: str, user_tier: int, comment: str) -> bool:
        """
        Saves a manual correction for a specific (Keyword, Product) pair.
        
        Args:
            keyword: Original search query.
            product_id: Product identifier (OID or search item ID).
            user_tier: Human-assigned quality tier (0 for Miss, 1 for T1, 2 for T2, 3 for T3).
            comment: Reasoning for the manual correction.
            
        Returns:
            Boolean success status.
        """
        if keyword not in self.feedback:
            self.feedback[keyword] = {}
        
        self.feedback[keyword][product_id] = {
            "user_tier": user_tier,
            "comment": comment,
            "timestamp": datetime.now(TZ_TAIPEI).isoformat()
        }
        
        try:
            with open(FEEDBACK_FILE, "w") as f:
                json.dump(self.feedback, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save feedback: {e}")
            return False

    def get_correction(self, keyword: str, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves human correction entry if it exists.
        
        Args:
            keyword: The original search term.
            product_id: The ID of the item being judged.
            
        Returns:
            Dictionary with calibration info or None.
        """
        return self.feedback.get(keyword, {}).get(str(product_id))

    def apply_overrides(self, keyword: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Injects manual calibrations into a result list to override automated results.
        Input: List of slimmed product results.
        Modifies results in-place.
        
        Args:
            keyword: Search term being reviewed.
            results: List of search result dictionaries.
            
        Returns:
            The augmented list of results with is_calibrated=True for specific items.
        """
        kw_feedback = self.feedback.get(keyword, {})
        if not kw_feedback:
            return results

        for p in results:
            pid = str(p.get("id"))
            if pid in kw_feedback:
                fb = kw_feedback[pid]
                p["original_tier"] = p["tier"]
                p["tier"] = fb["user_tier"]
                p["user_comment"] = fb["comment"]
                p["is_calibrated"] = True
                
                # Prepend the manual reason to mismatch indicators
                if "mismatch_reasons" not in p:
                    p["mismatch_reasons"] = []
                p["mismatch_reasons"].insert(0, f"👨‍💻 人工校正: {fb['comment']}")
        
        return results

calibration_manager = CalibrationManager()
