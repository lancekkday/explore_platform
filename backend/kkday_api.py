import os
import re
import requests
from loguru import logger
from urllib.parse import quote, urlencode

PAGE_SIZE = 50   # KKDay API 每頁上限

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
        if products:
            # logger.info(f"Sample product keys: {list(products[0].keys())}")
            logger.info(f"Sample product_category: {products[0].get('product_category')}")
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
