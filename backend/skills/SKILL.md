---
name: Search Intent Evaluator
description: Use this skill to evaluate the relevance of KKDay products against a search keyword. Includes AI-driven intent parsing and human calibration support.
---

# Search Intent Evaluator Skill

This skill provides high-level functions for judging if a KKDay product (SearchResult) matches the user's search intent. It combines GPT-4o semantic parsing with strict business rules.

## Core Capabilities

1. **Intent Parsing**: Infers the core product, destination, and category from a loose keyword.
2. **Product Judgment**: Assigns a Quality Tier (T1-T3 or Miss) based on metadata and text similarity.
3. **Manual Calibration**: Persists human feedback to override automated results.

## Usage for AI Agents

### 1. Judge a Keyword (High-level)
To understand what a keyword really means before fetching products:
```python
from backend.skills.intent_judger import judger
metadata = judger.get_ai_metadata("esim", ai_enabled=True)
# Returns: {"item": "esim", "location": None, "category": "CATEGORY_081"}
```

### 2. Judge Search Results
To verify a list of products fetched from an API:
```python
from backend.skills.intent_judger import judger
# p is a product dict from KKDay API
result = judger.judge_product(p, "esim", ai_metadata=metadata)
# Returns: {"tier": 1, "mismatch_reasons": [], "cat_match": "exact", ...}
```

### 3. Save Human Calibration
To correct a result after finding a mistake:
```python
from backend.skills.calibration_manager import calibration_manager
calibration_manager.save_feedback(
    keyword="esim",
    product_id="12345",
    user_tier=1,
    comment="This is a valid eSIM product despite wrong category"
)
```

## Directory Structure
- `intent_judger.py`: Entry point for evaluation logic.
- `calibration_manager.py`: Handles `feedback.json` persistence.
- `ai_agent.py`: Low-level OpenAI API wrapper.
- `intent_matcher.py`: Core rule engine for location and category matching.
