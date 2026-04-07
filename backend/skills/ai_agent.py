import os
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

class SearchIntent(BaseModel):
    """Semantic breakdown of a search keyword."""
    core_product: str
    location: Optional[str]
    category: Optional[str]
    theme: Optional[str]
    reason: str

def parse_intent_with_ai(keyword: str) -> tuple[SearchIntent, dict]:
    """
    Analyzes a raw search keyword using GPT-4o-mini to extract intent parameters.

    Args:
        keyword: The user's search string.

    Returns:
        Tuple of (SearchIntent, usage_dict). usage_dict contains prompt_tokens,
        completion_tokens, total_tokens, and estimated_cost_usd.
        On failure, returns fallback SearchIntent and zeroed usage.
    """
    prompt = f"""
    你是 KKDay 的搜尋意圖分析專家。
    分析關鍵字: "{keyword}"

    請萃取出以下資訊:
    1. core_product: 使用者真正想要的產品核心名詞 (例如: esim, 一日遊, 門票, 租車)。
    2. location: 提到的具體地點 (例如: 日本, 東京, 九份)。若無則 null。
    3. category: 根據以下規則映射分類代碼:
       - 門票/景點: CATEGORY_001
       - SIM卡/eSIM/WIFI: CATEGORY_081
       - 一日遊/行程/tour: CATEGORY_020
       - 美食/餐廳: CATEGORY_125
       - 自助餐/buffet: CATEGORY_134
       - 交通/接送/新幹線/JR: CATEGORY_120
       若不確定則提供最接近的代碼或 null。
    4. theme: 活動主題標籤，若關鍵字含有季節性/活動性主題則填入，例如:
       滑雪、溫泉、賞花、賞櫻、漂流、泛舟、親子、樂園、潛水、衝浪、露營、健行、登山
       若無明確主題則 null。
    5. reason: 簡短解釋判定邏輯。

    請以繁體中文思考，並返回 JSON 格式。
    """

    _zero_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一位專業的電商搜尋意圖分析師。"},
                {"role": "user", "content": prompt}
            ],
            response_format=SearchIntent,
        )
        res = completion.choices[0].message.parsed

        # gpt-4o-mini pricing: $0.150/1M input, $0.600/1M output (as of 2025-04)
        usage = completion.usage
        cost = (usage.prompt_tokens * 0.150 + usage.completion_tokens * 0.600) / 1_000_000
        usage_dict = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "estimated_cost_usd": round(cost, 8),
        }

        logger.info(f"AI parsed '{keyword}' -> {res} | tokens={usage.total_tokens} cost=${cost:.6f}")
        return res, usage_dict
    except Exception as e:
        logger.error(f"AI parsing failed for keyword '{keyword}': {e}")
        return SearchIntent(core_product=keyword, location=None, category=None, theme=None, reason="Fallback due to API error"), _zero_usage
