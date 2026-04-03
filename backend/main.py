from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests as _requests
from kkday_api import fetch_kkday_products
from skills.intent_matcher import IntentMatcher
from skills.metrics import compute_ndcg, compute_recall_stats, compute_category_distribution, compute_rank_delta

app = FastAPI(title="Search Intent Verification API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

matcher = IntentMatcher("/Users/kkday_borrow_f/Documents/workspace/Search_data/be2_destinations_dump")


class VerifyRequest(BaseModel):
    keyword: str
    env: str
    cookie: str
    count: int = 300


class CompareRequest(BaseModel):
    keyword: str
    cookie: str
    count: int = 300


@app.get("/api/guest-cookie")
def get_guest_cookie(env: str = "production"):
    """
    用 Playwright Headless Chromium 訪問 KKDay，取得完整的動態 Cookie（含 csrf_cookie_name）。
    env: 'stage' | 'production'
    """
    if env == "production":
        url = "https://www.kkday.com/zh-tw"
    elif env == "stage":
        url = "https://www.stage.kkday.com/zh-tw"
    else:
        raise HTTPException(status_code=400, detail="env must be stage or production")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="zh-TW",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            # Step 1: 首頁 — 觸發 JS 設定的 KKUD / KKWEB
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)  # 等 JS 執行完畢

            # Step 2: 搜尋列表頁 — 觸發 csrf_cookie_name
            origin = url.rsplit("/zh-tw", 1)[0]
            page.goto(f"{origin}/zh-tw/product/productlist/test", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)

            # 收集所有 cookie
            cookies = context.cookies()
            browser.close()

        if not cookies:
            raise HTTPException(status_code=502, detail=f"KKDay [{env}] Headless 未取得任何 cookie")

        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        key_fields = [c['name'] for c in cookies if c['name'] in ("KKUD", "KKWEB", "KKWEBSTAGE", "csrf_cookie_name", "csrf_token")]

        return {
            "success": True,
            "env": env,
            "cookie": cookie_str,
            "key_fields_found": key_fields,
            "total_fields": len(cookies),
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="Playwright 未安裝，請執行: pip install playwright && playwright install chromium")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"[{env}] Playwright 取 Cookie 失敗: {e}")





def _build_results(products, keyword):
    results = []
    for i, p in enumerate(products):
        result = matcher.verify(p, keyword)
        img = p.get("img_url") or p.get("image_url") or ""
        results.append({
            "rank": i + 1,
            "id": p.get("id", ""),
            "name": p.get("name", ""),
            "img_url": img,
            "url": p.get("url", ""),
            "main_cat_key": p.get("main_cat_key", ""),
            "main_cat_name": p.get("product_category", {}).get("main", ""),
            "destinations": [d.get("name") for d in p.get("destinations", [])],
            "tier": result["tier"],
            "dest_match": result["dest_match"],
            "cat_match": result["cat_match"],
            "mismatch_reasons": result["mismatch_reasons"],
            "expected_dest": result["expected_dest"],
            "expected_cat": result["expected_cat"],
        })
    return results


@app.post("/api/verify")
def verify_keyword(req: VerifyRequest):
    if req.env not in ["stage", "production"]:
        raise HTTPException(status_code=400, detail="env must be stage or production")

    products, total, total_page = fetch_kkday_products(req.keyword, req.env, req.cookie, req.count)
    results = _build_results(products, req.keyword)

    # Compute metrics
    ndcg_10  = compute_ndcg(results, k=10)
    ndcg_50  = compute_ndcg(results, k=50)
    recall   = compute_recall_stats(results, k_list=(10, 50, 100))
    cat_dist = compute_category_distribution(results)

    return {
        "success": True,
        "keyword": req.keyword,
        "env": req.env,
        "total": total,
        "results": results,
        "metrics": {
            "ndcg_at_10": ndcg_10,
            "ndcg_at_50": ndcg_50,
            **recall,
            "category_distribution": cat_dist,
        }
    }


@app.post("/api/compare")
def compare_envs(req: CompareRequest):
    """
    同時抓 Stage + Production，計算 Rank Delta (stage_rank - prod_rank)
    """
    stage_prods, stage_total, _ = fetch_kkday_products(req.keyword, "stage",      req.cookie, req.count)
    prod_prods,  prod_total,  _ = fetch_kkday_products(req.keyword, "production", req.cookie, req.count)

    stage_results = _build_results(stage_prods, req.keyword)
    prod_results  = _build_results(prod_prods,  req.keyword)

    rank_delta = compute_rank_delta(stage_results, prod_results)

    # Attach delta to each stage result
    for p in stage_results:
        p["rank_delta"] = rank_delta.get(str(p["id"]))

    stage_metrics = {
        "ndcg_at_10": compute_ndcg(stage_results, k=10),
        "ndcg_at_50": compute_ndcg(stage_results, k=50),
        **compute_recall_stats(stage_results),
        "category_distribution": compute_category_distribution(stage_results),
    }
    prod_metrics = {
        "ndcg_at_10": compute_ndcg(prod_results, k=10),
        "ndcg_at_50": compute_ndcg(prod_results, k=50),
        **compute_recall_stats(prod_results),
        "category_distribution": compute_category_distribution(prod_results),
    }

    return {
        "success": True,
        "keyword": req.keyword,
        "stage": {"total": stage_total, "results": stage_results, "metrics": stage_metrics},
        "production": {"total": prod_total, "results": prod_results, "metrics": prod_metrics},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
