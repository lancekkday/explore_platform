from typing import Optional, Dict, List, Any, TypedDict
from skills.ai_agent import parse_intent_with_ai
from skills.intent_matcher import IntentMatcher
from skills.calibration_manager import calibration_manager
from loguru import logger

# Initialize underlying rule-based matcher
MATCHER = IntentMatcher("/Users/kkday_borrow_f/Documents/workspace/Search_data/be2_destinations_dump")

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

    def get_ai_metadata(self, keyword: str, ai_enabled: bool = False) -> Optional[Dict[str, Any]]:
        """
        Parses a keyword using AI to extract semantic intent.
        
        Args:
            keyword: The search query string.
            ai_enabled: Whether to trigger GPT-4o parsing.
            
        Returns:
            Dictionary with 'item', 'location', and 'category' if successful, else None.
        """
        if not ai_enabled:
            return None
        
        try:
            ai_res = parse_intent_with_ai(keyword)
            return {
                "item": ai_res.core_product,
                "location": ai_res.location,
                "category": ai_res.category
            }
        except Exception as e:
            logger.error(f"AI Parse failed for [{keyword}]: {e}")
            return None

    def judge_product(self, p: Dict[str, Any], keyword: str, ai_metadata: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        Main judgment function for a single product. 
        Combines rule-based matching with optional AI intent metadata.
        
        Args:
            p: Raw product dictionary from KKDay API.
            keyword: Original search query.
            ai_metadata: Optional pre-parsed intent data from get_ai_metadata.
            
        Returns:
            VerificationResult containing tier and mismatch details.
        """
        return self.matcher.verify(p, keyword, ai_metadata)

    def process_and_calibrate(self, p: Dict[str, Any], rank: int, keyword: str, ai_metadata: Optional[Dict[str, Any]], slim_func: Any) -> Dict[str, Any]:
        """
        High-level wrapper for single product processing in the Discovery UI.
        Handles judgment, slimming, and applying manual human calibrations.
        
        Args:
            p: Raw product dictionary.
            rank: Ranking position in search results.
            keyword: Original search query.
            ai_metadata: Pre-parsed AI intent.
            slim_func: Function to convert raw product to UI-friendly format.
            
        Returns:
            Slimmed product dictionary with intent verification and calibration data.
        """
        # 1. Rule/AI Judgment
        result = self.judge_product(p, keyword, ai_metadata)
        
        # 2. Base Slimming
        slimmed = slim_func(p, rank, result, keyword)
        
        # 3. Apply Calibration Overrides for this single product
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
