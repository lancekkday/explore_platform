import os
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Model config — override via env vars to switch models or update pricing
AI_MODEL = os.getenv("AI_MODEL_NAME", "gpt-4o-mini")
# Pricing per 1M tokens (USD) — update when OpenAI changes pricing
AI_PRICE_INPUT  = float(os.getenv("AI_PRICE_INPUT_PER_1M",  "0.150"))
AI_PRICE_OUTPUT = float(os.getenv("AI_PRICE_OUTPUT_PER_1M", "0.600"))

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
       - 美食/餐廳/自助餐/buffet/下午茶: CATEGORY_079
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
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "你是一位專業的電商搜尋意圖分析師。"},
                {"role": "user", "content": prompt}
            ],
            response_format=SearchIntent,
        )
        res = completion.choices[0].message.parsed

        usage = completion.usage
        cost = (usage.prompt_tokens * AI_PRICE_INPUT + usage.completion_tokens * AI_PRICE_OUTPUT) / 1_000_000
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


TIER_LABELS = {1: "T1 完全相關", 2: "T2 部分相關", 3: "T3 疑似相關", 0: "MISS 不相關"}

def explain_product_match(keyword: str, product_name: str, tier: int,
                          mismatch_reasons: list, destinations: list,
                          main_cat_key: str) -> tuple[str, dict]:
    """
    Ask GPT to explain in plain Chinese why a product received its tier judgment.
    Returns (explanation_text, usage_dict).
    """
    dest_names = []
    for d in (destinations or []):
        if isinstance(d, dict):
            n = d.get("name", "")
        else:
            n = str(d)
        if n and n != "GLOBAL":
            dest_names.append(n)

    tier_label = TIER_LABELS.get(tier, str(tier))
    reasons_text = " | ".join(mismatch_reasons) if mismatch_reasons else "無（全部條件符合）"

    has_cat_mismatch = any("類別" in r for r in (mismatch_reasons or []))
    priority_hint = (
        "【重要】商品類別與搜尋詞的產品類型明顯不符，這是判定 MISS 的核心原因。"
        "請優先說明類別/產品類型的差異，地點是否匹配為次要考量，不需強調。"
        if has_cat_mismatch else ""
    )

    prompt = f"""用戶在 KKDay 搜尋「{keyword}」，系統對以下商品進行意圖比對：

商品名稱：{product_name}
判定等級：{tier_label}
商品目的地：{', '.join(dest_names) or '（未指定）'}
商品分類：{main_cat_key or '（未知）'}
系統判定原因：{reasons_text}
{priority_hint}
請用 2～3 句繁體中文，簡潔說明：
1. 為何判定為「{tier_label}」（點出最關鍵的不符原因）
2. 這個判定是否合理；如果有疑問請直接點出

請直接說明結論，不要有開場白或「根據以上」等語氣詞。"""

    _zero = {"prompt_tokens": 0, "completion_tokens": 0, "estimated_cost_usd": 0.0}
    try:
        completion = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "你是 KKDay 搜尋品質分析師，專門用簡短繁體中文解釋商品意圖比對結果。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        text = completion.choices[0].message.content.strip()
        usage = completion.usage
        cost = (usage.prompt_tokens * AI_PRICE_INPUT + usage.completion_tokens * AI_PRICE_OUTPUT) / 1_000_000
        logger.info(f"Explain '{keyword}'/'{product_name[:30]}' tier={tier} tokens={usage.total_tokens} cost=${cost:.6f}")
        return text, {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "estimated_cost_usd": round(cost, 8),
        }
    except Exception as e:
        logger.error(f"explain_product_match failed: {e}")
        return "AI 解釋暫時無法使用。", _zero
