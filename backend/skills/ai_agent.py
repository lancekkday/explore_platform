import os
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"))

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

class SearchIntent(BaseModel):
    """Semantic breakdown of a search keyword."""
    core_product: str
    location: Optional[str]
    category: Optional[str]
    reason: str

def parse_intent_with_ai(keyword: str) -> SearchIntent:
    """
    Analyzes a raw search keyword using GPT-4o-mini to extract intent parameters.
    
    Args:
        keyword: The user's search string.
        
    Returns:
        SearchIntent object with core_product, location, and category mapping.
    """
    prompt = f"""
    你是 KKDay 的搜尋意圖分析專家。
    分析關鍵字: "{keyword}"
    
    請萃取出以下資訊:
    1. core_product: 使用者真正想要的產品核心名詞 (例如: esim, 一日遊, 門票, 租車)。
    2. location: 提到的具體地點 (例如: 日本, 東京, 九份)。若無則 null。
    3. category: 根據以下規則映射分類代碼:
       - 門票: CATEGORY_001
       - SIM卡/WIFI: CATEGORY_081
       - 一日遊/行程: CATEGORY_020
       - 美食/餐廳: CATEGORY_125
       - 交通/接送: CATEGORY_120
       若不確定則提供最接近的代碼或 null。
    4. reason: 簡短解釋判定邏輯。

    請以繁體中文思考，並返回 JSON 格式。
    """
    
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
        logger.info(f"AI parsed '{keyword}' -> {res}")
        return res
    except Exception as e:
        logger.error(f"AI parsing failed for keyword '{keyword}': {e}")
        # Return a safe fallback
        return SearchIntent(core_product=keyword, location=None, category=None, reason="Fallback due to API error")
