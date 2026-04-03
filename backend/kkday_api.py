import os
import re
import requests
from loguru import logger
from urllib.parse import quote, urlencode

def _csrf_token_from_cookie(cookie: str) -> str:
    m = re.search(r"csrf_cookie_name=([^;\s]+)", cookie or "")
    return m.group(1) if m else ""

def _parse_ajax_product_list_json(body: dict):
    """
    Parse kkday response json body based on original search_match_test.py
    """
    if not isinstance(body, dict):
        return [], 0, 0
    inner = body.get("data")
    
    if isinstance(inner, dict) and isinstance(inner.get("data"), list):
        prods = inner["data"]
        total = int(inner.get("total") or 0)
        tp = inner.get("total_page") or inner.get("total_pages") or 0
        return prods, total, int(tp)
        
    if isinstance(inner, list):
        return (
            inner,
            int(body.get("total") or 0),
            int(body.get("total_page") or body.get("total_pages") or 0),
        )
        
    return [], 0, 0

def fetch_kkday_products(keyword, env, cookie, row_count=50):
    if env == "production":
        origin = "https://www.kkday.com"
    elif env == "stage":
        origin = "https://www.stage.kkday.com"
    else:
        raise ValueError(f"Unknown env: {env}")

    base_url = f"{origin}/zh-tw/product/ajax_get_product_list"
    path_keyword = quote(keyword, safe="")
    query_keyword = quote(keyword, safe="")
    referer = (
        f"{origin}/zh-tw/product/productlist/{path_keyword}"
        f"?filter_trusted_partner=trusted_partner&keyword={query_keyword}"
        f"&currency=TWD&sort=prec&page=1&count={row_count}"
    )

    csrf = _csrf_token_from_cookie(cookie)
    post_body = urlencode({
        "filter[filter_trusted_partner][0]": "trusted_partner",
        "csrf_token_name": csrf,
    })

    params = {
        "keyword": keyword,
        "currency": "TWD",
        "sort": "prec",
        "page": 1,
        "start": 0,
        "count": row_count,
    }

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": origin,
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    }

    try:
        response = requests.post(base_url, params=params, data=post_body, headers=headers, timeout=60)
        response.raise_for_status()
        body = response.json()
        products, total, total_page = _parse_ajax_product_list_json(body)
        return products, total, total_page
    except Exception as e:
        logger.error(f"{env} API request failed for keyword '{keyword}': {e}")
        return [], 0, 0
