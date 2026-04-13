from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from kkday_api import fetch_kkday_products
from skills.metrics import compute_ndcg, compute_recall_stats, compute_category_distribution, compute_rank_delta
from skills.data_sanitizer import sanitizer
from batch_engine import engine as batch_engine
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager

app = FastAPI(title="Search Intent Verification API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VerifyRequest(BaseModel):
    keyword: str
    env: str
    cookie: str
    count: int = 300

class CompareRequest(BaseModel):
    keyword: str
    cookie: str
    count: int = 300
    ai_enabled: Optional[bool] = None

class FeedbackRequest(BaseModel):
    keyword: str
    product_id: str
    user_tier: int
    comment: str

class BatchRunRequest(BaseModel):
    cookie: str

class KeywordListRequest(BaseModel):
    keywords: list[Any]

class ExplainRequest(BaseModel):
    keyword: str
    product_name: str
    tier: int
    mismatch_reasons: list[str] = []
    destinations: list[Any] = []
    main_cat_key: str = ""

@app.post("/api/explain")
def explain_match(req: ExplainRequest):
    try:
        from skills.ai_agent import explain_product_match
        text, usage = explain_product_match(
            req.keyword, req.product_name, req.tier,
            req.mismatch_reasons, req.destinations, req.main_cat_key,
        )
        return {"success": True, "explanation": text, "usage": usage}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/guest-cookie")
def get_guest_cookie(env: str = "production"):
    if env == "production":
        url = "https://www.kkday.com/zh-tw/product/productlist/esim"
    elif env == "stage":
        url = "https://www.stage.kkday.com/zh-tw/product/productlist/esim"
    else:
        raise HTTPException(status_code=400, detail="env must be stage or production")

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="zh-TW",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            # Visit search result page to force CSRF set
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000) # Ensure hydration
            cookies = context.cookies()
            browser.close()
        
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        has_csrf = "csrf_cookie_name" in cookie_str or "csrf_ks_name" in cookie_str
        return {"success": True, "cookie": cookie_str, "has_csrf": has_csrf}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Cookie fetch failed: {e}")

def _slim_product(p, rank, result, keyword):
    pc = p.get("product_category") or {}
    cat_code = p.get("main_cat_key") or pc.get("main") or pc.get("key") or ""
    return {
        "rank": rank, "id": str(p.get("prod_oid") or p.get("oid") or p.get("product_id") or rank),
        "name": p.get("name", ""), "img_url": p.get("img_url", ""), "url": p.get("url", ""),
        "tier": result["tier"], "mismatch_reasons": result["mismatch_reasons"],
        "rank_delta": None,
        "main_cat_key": cat_code,
        "destinations": sanitizer.get_destinations(p),
        "show_order_count": p.get("show_order_count", ""),
    }

@app.post("/api/compare")
def compare_envs(req: CompareRequest):
    ai_metadata = judger.get_ai_metadata(req.keyword, ai_enabled=(req.ai_enabled or False))
    stage_prods, stage_total, _ = fetch_kkday_products(req.keyword, "stage",      req.cookie, req.count)
    prod_prods,  prod_total,  _ = fetch_kkday_products(req.keyword, "production", req.cookie, req.count)
    
    stage_res = [judger.process_and_calibrate(p, i+1, req.keyword, ai_metadata, _slim_product) for i, p in enumerate(stage_prods)]
    prod_res  = [judger.process_and_calibrate(p, i+1, req.keyword, ai_metadata, _slim_product) for i, p in enumerate(prod_prods)]
    
    delta = compute_rank_delta(stage_res, prod_res)
    for p in stage_res: p["rank_delta"] = delta.get(p["id"])

    final_results = {
        "success": True, "keyword": req.keyword,
        "stage": {"total": stage_total, "results": stage_res, "metrics": {
            "ndcg_at_10": compute_ndcg(stage_res, 10), "ndcg_at_50": compute_ndcg(stage_res, 50),
            "ndcg_at_150": compute_ndcg(stage_res, 150), **compute_recall_stats(stage_res, k_list=(10, 50, 150))
        }},
        "production": {"total": prod_total, "results": prod_res, "metrics": {
            "ndcg_at_10": compute_ndcg(prod_res, 10), "ndcg_at_50": compute_ndcg(prod_res, 50),
            "ndcg_at_150": compute_ndcg(prod_res, 150), **compute_recall_stats(prod_res, k_list=(10, 50, 150))
        }}
    }

    # 自動存檔單次巡檢結果 (New)
    batch_engine.save_single_record(req.keyword, final_results)
    
    return final_results

@app.post("/api/feedback")
def calibrate_feedback(req: FeedbackRequest):
    calibration_manager.save_feedback(req.keyword, req.product_id, req.user_tier, req.comment)
    return {"success": True}

@app.get("/api/keywords")
def get_keywords():
    return {"success": True, "keywords": batch_engine.keyword_list}

@app.post("/api/keywords")
def update_keywords(req: KeywordListRequest):
    batch_engine.save_keywords(req.keywords)
    return {"success": True}

@app.post("/api/batch/run")
def run_batch(req: BatchRunRequest):
    batch_engine.run_batch(req.cookie)
    return {"success": True}

@app.post("/api/batch/stop")
def stop_batch():
    batch_engine.stop_batch()
    return {"success": True}

@app.get("/api/batch/status")
def get_batch_status():
    return {
        "is_running": batch_engine.is_running,
        "progress": batch_engine.progress,
        "current_keyword": batch_engine.current_keyword,
        "total_keywords": len(batch_engine.keyword_list),
        "results_count": len(batch_engine.results)
    }

@app.get("/api/batch/results")
def get_batch_results():
    return {"success": True, "results": batch_engine.results}

@app.get("/api/batch/history")
def get_batch_history():
    return {"success": True, "history": batch_engine.get_history_list()}

@app.get("/api/batch/history/{history_id}")
def get_history_detail(history_id: int):
    results = batch_engine.get_history_detail(history_id)
    if not results:
        raise HTTPException(status_code=404, detail="History record not found")
    return {"success": True, "results": results}

@app.get("/api/single/history")
def get_single_history():
    return {"success": True, "history": batch_engine.get_single_history()}

@app.get("/api/single/history/{id}")
def get_single_detail(id: int):
    results = batch_engine.get_single_detail(id)
    if not results:
        raise HTTPException(status_code=404, detail="Single inspection record not found")
    return {"success": True, "results": results}

@app.get("/api/ai/usage")
def get_ai_usage(limit: int = 100):
    """Return recent AI usage records and aggregate stats."""
    import sqlite3
    from batch_engine import DB_PATH
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM ai_usage_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        agg = conn.execute(
            "SELECT COUNT(*) as calls, SUM(total_tokens) as total_tokens, SUM(estimated_cost_usd) as total_cost FROM ai_usage_log"
        ).fetchone()
        conn.close()
        return {
            "success": True,
            "aggregate": {
                "total_calls": agg["calls"] or 0,
                "total_tokens": agg["total_tokens"] or 0,
                "total_cost_usd": round(agg["total_cost"] or 0, 6),
            },
            "recent": [dict(r) for r in rows],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=19426)
