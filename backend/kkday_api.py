import os
import re
import requests
from loguru import logger
from urllib.parse import quote, urlencode
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

PAGE_SIZE = 50   # KKDay API 每頁上限

# Source tag sent on every outbound search call so this platform's traffic is
# identifiable in the API gateway / Kibana logs (verified accepted by the v3 search
# API — returns 200 with identical results). Lets us separate 巡檢 traffic from real
# users and correlate against our own request_id.
KKDAY_FORWARDED_ID = "explore_platform"

def _csrf_token_from_cookie(cookie: str) -> str:
    m = re.search(r"csrf_cookie_name=([^;\s]+)", cookie or "")
    return m.group(1) if m else ""


def _parse_ajax_product_list_json(body: dict):
    """
    支援兩種回傳格式：
    - { "data": { "data": [...], "total": N, "total_page": P } }
    - { "data": [...], "total": N, "total_page": P }
    """
    if not isinstance(body, dict):
        return [], 0, 0

    inner = body.get("data")

    if isinstance(inner, dict) and isinstance(inner.get("data"), list):
        prods = inner["data"]
        total = int(inner.get("total") or 0)
        tp = inner.get("total_page") or inner.get("total_pages") or 0
        if not tp and total and prods:
            tp = -(-total // len(prods))   # ceiling division
        return prods, total, int(tp)

    if isinstance(inner, list):
        return (
            inner,
            int(body.get("total") or 0),
            int(body.get("total_page") or body.get("total_pages") or 0),
        )

    return [], 0, 0


def _fetch_page(base_url, params, post_body, headers, env, keyword, page):
    """發送單頁請求，回傳 (products, total, total_page) 或 ([], 0, 0)"""
    p = {**params, "page": page, "start": (page - 1) * PAGE_SIZE}
    try:
        resp = requests.post(base_url, params=p, data=post_body, headers=headers, timeout=60)
        resp.raise_for_status()
        products, total, total_page = _parse_ajax_product_list_json(resp.json())
        logger.info(f"[{env}] keyword='{keyword}' page={page} got={len(products)} total={total} total_page={total_page}")
        return products, total, total_page
    except Exception as e:
        logger.error(f"[{env}] keyword='{keyword}' page={page} failed: {e}")
        return [], 0, 0


def fetch_kkday_products(keyword: str, env: str, cookie: str, row_count: int = 300):
    """
    分頁抓取 KKDay 商品，最多回傳 row_count 筆。
    每頁固定 PAGE_SIZE=50，依照 total_page 翻頁直到夠數為止。
    """
    if env == "production":
        origin = "https://www.kkday.com"
    elif env == "stage":
        origin = "https://www.stage.kkday.com"
    else:
        raise ValueError(f"Unknown env: {env}")

    base_url = f"{origin}/zh-tw/product/ajax_get_product_list"
    path_keyword = quote(keyword, safe="")
    # 簡化 Referer，模擬從列表頁發起的 AJAX
    referer = f"{origin}/zh-tw/product/productlist/{path_keyword}"

    csrf = _csrf_token_from_cookie(cookie)
    # 備用 CSRF：如果 cookie 裡沒找到，試著找有沒有其他可能的 token
    if not csrf:
        csrf_m = re.search(r"csrf_ks_name=([^;\s]+)", cookie or "")
        csrf = csrf_m.group(1) if csrf_m else ""

    # filter_trusted_partner is intentionally omitted: including it restricts results
    # to KKDay-verified partners only, which reduces recall for intent verification purposes.
    post_body = f"csrf_token_name={csrf}" if csrf else ""

    base_params = {
        "keyword": keyword,
        "currency": "TWD",
        "sort": "prec",
        "count": PAGE_SIZE,
    }

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": origin,
        "Referer": referer,
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
        "kkday-forwarded-id": KKDAY_FORWARDED_ID,
    }

    all_products = []
    seen_ids = set()

    def add_unique(prods):
        for p in prods:
            # Try multiple ID sources used by KKDay API variants
            pid = p.get("oid") or p.get("product_id") or p.get("id") or p.get("prod_id")
            if pid is None:
                # If no ID, we can't reliably deduplicate, so just keep it
                all_products.append(p)
            elif pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

    # ── Page 1 ──
    page1, total, total_page = _fetch_page(base_url, base_params, post_body, headers, env, keyword, 1)
    add_unique(page1)

    if not total or total_page <= 1:
        return all_products[:row_count], total, total_page

    # ── Pages 2…N ──
    max_page = min(total_page, -(-row_count // PAGE_SIZE))
    for page in range(2, max_page + 1):
        if len(all_products) >= row_count:
            break
        prods, _, _ = _fetch_page(base_url, base_params, post_body, headers, env, keyword, page)
        if not prods:
            break
        add_unique(prods)

    logger.info(f"[{env}] keyword='{keyword}' fetched total={len(all_products)} (requested={row_count})")
    return all_products[:row_count], total, total_page


# ── v3 Search API ────────────────────────────────────────────────────────────

V3_PAGE_SIZE = 50


def _coerce_product_id(v):
    """Coerce a numeric product id (prod_mid/prod_oid) to int for type-stable keys.
    Numeric strings ("137689", "137689.0") and floats become int; None/'' and
    genuinely non-numeric values are returned unchanged so they stay visible to
    downstream anomaly detection instead of being silently zeroed."""
    if v is None or v == "" or isinstance(v, bool):
        return v
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return v

_V3_BASE_URLS = {
    "stage": "https://api-search.stage.kkday.com/v3/product/search/product-list",
    "production": "https://api-search.kkday.com/v3/product/search/product-list",
}


def _fetch_page_v3(url, headers, body, env, keyword):
    """發送 v3 search API 請求，回傳 (products, total)"""
    try:
        resp = requests.get(url, headers=headers, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        total = data.get("metadata", {}).get("pagination", {}).get("total_count", 0)
        prods = data.get("data", {}).get("prods", [])
        logger.info(f"[v3][{env}] keyword='{keyword}' start={body.get('start')} got={len(prods)} total={total}")
        return prods, int(total)
    except Exception as e:
        logger.error(f"[v3][{env}] keyword='{keyword}' start={body.get('start')} failed: {e}")
        return [], 0


DEFAULT_LANG = "zh-tw"
DEFAULT_LOCALE = "tw"
DEFAULT_CHANNEL = "ios"


def fetch_kkday_products_v3(
    keyword: str,
    env: str,
    cookie: str,
    row_count: int = 300,
    test_exp: int = 3,
    lang: str = DEFAULT_LANG,
    locale: str = DEFAULT_LOCALE,
    channel: str = DEFAULT_CHANNEL,
):
    """
    使用 v3 search API 抓取商品，最多回傳 row_count 筆。
    介面與 fetch_kkday_products 相同：回傳 (products, total, total_page)。
    test_exp: 搜尋演算法版本（AB 巡檢用）。
    lang / locale / channel: 由呼叫端帶入,預設值與舊行為一致 (zh-tw / tw / ios)。
    """
    url = _V3_BASE_URLS.get(env)
    if not url:
        raise ValueError(f"Unknown env: {env}")

    auth_key = os.getenv("KKDAY_SEARCH_AUTH_KEY", "")
    device_id = os.getenv("KKDAY_SEARCH_DEVICE_ID", "e5af2aba849682eebc53766e4487289f")

    headers = {
        "x-auth-key": auth_key,
        "Content-Type": "application/json",
        "Cookie": cookie,
        "kkday-forwarded-id": KKDAY_FORWARDED_ID,
    }

    base_body = {
        "q": keyword,
        "lang": lang or DEFAULT_LANG,
        "locale": locale or DEFAULT_LOCALE,
        "currency": "TWD",
        "channel": channel or DEFAULT_CHANNEL,
        "source": channel or DEFAULT_CHANNEL,
        "translate_status": 1,
        "page_name": "product_list_mobile",
        "device_id": device_id,
        "ux_exp": 0,
        "sort": "PREC",
        "test_exp": test_exp,
    }

    all_products = []
    seen_ids = set()

    def add_unique(prods):
        for p in prods:
            # Normalize product ids at the API boundary. The v3 API serializes
            # prod_mid/prod_oid as int for some test_exp versions and as str for
            # others; coercing here means every downstream consumer (unified-search,
            # ab_check._fetch_results, the cron AB runner) keys on a consistent type,
            # so 137689 (int) and "137689" (str) can never miss-match into a false
            # "未出現". Genuinely non-numeric ids are left untouched so anomaly
            # detection (mid_warnings) can still see the original bad value.
            for _f in ("prod_mid", "prod_oid"):
                if _f in p:
                    p[_f] = _coerce_product_id(p[_f])
            pid = p.get("prod_oid") or p.get("prod_mid") or p.get("oid") or p.get("product_id")
            if pid is None:
                all_products.append(p)
            elif pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

    # ── First page ──
    body = {**base_body, "start": "0", "count": str(V3_PAGE_SIZE)}
    prods, total = _fetch_page_v3(url, headers, body, env, keyword)
    add_unique(prods)

    if not total or len(prods) == 0:
        total_page = 1 if prods else 0
        return all_products[:row_count], total, total_page

    total_page = -(-total // V3_PAGE_SIZE)  # ceiling division

    # ── Remaining pages ──
    max_page = min(total_page, -(-row_count // V3_PAGE_SIZE))
    for page in range(2, max_page + 1):
        if len(all_products) >= row_count:
            break
        start = (page - 1) * V3_PAGE_SIZE
        body = {**base_body, "start": str(start), "count": str(V3_PAGE_SIZE)}
        prods, _ = _fetch_page_v3(url, headers, body, env, keyword)
        if not prods:
            break
        add_unique(prods)

    logger.info(f"[v3][{env}] keyword='{keyword}' fetched total={len(all_products)} (requested={row_count})")
    return all_products[:row_count], total, total_page
