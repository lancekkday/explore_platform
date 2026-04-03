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
    query_keyword = quote(keyword, safe="")
    referer = (
        f"{origin}/zh-tw/product/productlist/{path_keyword}"
        f"?filter_trusted_partner=trusted_partner&keyword={query_keyword}"
        f"&currency=TWD&sort=prec&page=1&count={PAGE_SIZE}"
    )

    csrf = _csrf_token_from_cookie(cookie)
    post_body = urlencode({
        "filter[filter_trusted_partner][0]": "trusted_partner",
        "csrf_token_name": csrf,
    })

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
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    }

    all_products = []
    seen_ids = set()

    # ── Page 1 ──
    page1, total, total_page = _fetch_page(base_url, base_params, post_body, headers, env, keyword, 1)
    for p in page1:
        pid = p.get("oid") or p.get("product_id") or p.get("id")
        if pid not in seen_ids:
            seen_ids.add(pid)
            all_products.append(p)

    if not total or total_page <= 1:
        return all_products[:row_count], total, total_page

    # ── Pages 2…N ──
    max_page = min(total_page, -(-row_count // PAGE_SIZE))   # 需要幾頁才夠 row_count
    for page in range(2, max_page + 1):
        if len(all_products) >= row_count:
            break
        prods, _, _ = _fetch_page(base_url, base_params, post_body, headers, env, keyword, page)
        if not prods:
            break
        for p in prods:
            pid = p.get("oid") or p.get("product_id") or p.get("id")
            if pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)

    logger.info(f"[{env}] keyword='{keyword}' fetched total={len(all_products)} (requested={row_count})")
    return all_products[:row_count], total, total_page
