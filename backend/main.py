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
    向 KKDay 首頁發送 GET 請求，取得訪客 Cookie。
    env: 'stage' | 'production'
    """
    if env == "production":
        url = "https://www.kkday.com/zh-tw"
    elif env == "stage":
        url = "https://www.stage.kkday.com/zh-tw"
    else:
        raise HTTPException(status_code=400, detail="env must be stage or production")

    try:
        resp = _requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "zh-TW,zh;q=0.9",
            },
            timeout=15,
            allow_redirects=True,
        )
        # Build cookie string from the response cookies jar
        cookie_str = "; ".join(f"{k}={v}" for k, v in resp.cookies.items())
        if not cookie_str:
            raise HTTPException(status_code=502, detail=f"KKDay 服務在 {env} 未回傳任何 cookie，請檢查環境是否可連線")
        return {"success": True, "env": env, "cookie": cookie_str}
    except _requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"[{env}] 接活 KKDay 失敗: {e}")


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
