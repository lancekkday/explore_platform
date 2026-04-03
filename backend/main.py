from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from kkday_api import fetch_kkday_products
from skills.metrics import compute_ndcg, compute_recall_stats, compute_category_distribution, compute_rank_delta
from batch_engine import engine as batch_engine
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager

def _slim_product(p, rank, result, keyword):
    """
    將 API 原始資料瘦身，僅保留前端 UI 所需與比對相關的欄位
    """
    pc = p.get("product_category") or {}
    cat_code = p.get("main_cat_key") or ""
    if not cat_code and pc:
        if isinstance(pc.get("main"), str) and pc["main"].startswith("CATEGORY_"):
            cat_code = pc["main"]
        elif pc.get("key"):
            cat_code = pc["key"]

    return {
        "id": str(p.get("oid") or p.get("product_id") or rank),
        "rank": rank,
        "name": p.get("name"),
        "img_url": p.get("img_url"),
        "main_cat_key": cat_code,
        "destinations": [d.get("name") for d in p.get("destinations", [])],
        "tier": result["tier"],
        "mismatch_reasons": result["mismatch_reasons"],
        "cat_match": result["cat_match"],
        "dest_match": result["dest_match"],
    }

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





def _slim_product(p, rank, result, keyword):
    """
    優化存儲：只保留核心比對與展示欄位，丟棄 90% 不需要的 API 原始數據。
    """
    # 抽取分類代碼 (CATEGORY_XXX)
    cat_code = p.get("main_cat_key") or ""
    pc = p.get("product_category") or {}
    if not cat_code and pc:
        if isinstance(pc.get("main"), str) and pc["main"].startswith("CATEGORY_"):
            cat_code = pc["main"]
        elif pc.get("key"):
            cat_code = pc["key"]

    img = p.get("img_url") or (p.get("img_url_list") or [None])[0] or p.get("image_url") or ""
    prod_id = p.get("oid") or p.get("product_id") or p.get("prod_oid") or p.get("id") or f"idx-{rank}"

    return {
        "rank": rank,
        "id": str(prod_id),
        "name": p.get("name", ""),
        "img_url": img,
        "url": p.get("url", ""),
        "main_cat_key": cat_code,
        "main_cat_name": pc.get("main") if not str(pc.get("main")).startswith("CATEGORY_") else "",
        "destinations": [d.get("name") for d in p.get("destinations", [])],
        "tier": result["tier"],
        "dest_match": result["dest_match"],
        "cat_match": result["cat_match"],
        "mismatch_reasons": result["mismatch_reasons"],
        "expected_dest": result["expected_dest"],
        "expected_cat": result["expected_cat"],
    }


def _build_results(products, keyword):
    results = []
    for i, p in enumerate(products):
        result = matcher.verify(p, keyword)
        results.append(_slim_product(p, i + 1, result, keyword))
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
    ndcg_150 = compute_ndcg(results, k=150)
    recall   = compute_recall_stats(results, k_list=(10, 50, 150))
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
            "ndcg_at_150": ndcg_150,
            **recall,
            "category_distribution": cat_dist,
        }
    }


@app.post("/api/compare")
def compare_envs(req: CompareRequest):
    """
    同時抓 Stage + Production，計算 Rank Delta (stage_rank - prod_rank)
    """
    # 自動偵測 AI 模式：如果解析不到地點
    ai_metadata = None
    # 簡單判斷：如果關鍵字不包含特定的行程詞，但顯然是個特定名詞 (如 esim, wifi)
    # 這裡我們先暴力點：如果啟用專屬產品檢查
    expected_cat_name = None
    for cat in judger.matcher.CATEGORY_MAPPING.keys():
        if cat in req.keyword:
            expected_cat_name = cat
            break
    expected_dest_name = req.keyword.replace(expected_cat_name, "").strip() if expected_cat_name else req.keyword.strip()

    # 如果沒有地點，或是使用者手動強制 AI
    force_ai = req.ai_enabled if req.ai_enabled is not None else False
    ai_metadata = judger.get_ai_metadata(req.keyword, ai_enabled=(force_ai or not expected_dest_name or len(req.keyword) < 5))

    stage_prods, stage_total, _ = fetch_kkday_products(req.keyword, "stage",      req.cookie, req.count)
    prod_prods,  prod_total,  _ = fetch_kkday_products(req.keyword, "production", req.cookie, req.count)

    stage_results = [judger.process_and_calibrate(p, i+1, req.keyword, ai_metadata, _slim_product) for i, p in enumerate(stage_prods)]
    prod_results  = [judger.process_and_calibrate(p, i+1, req.keyword, ai_metadata, _slim_product) for i, p in enumerate(prod_prods)]

    rank_delta = compute_rank_delta(stage_results, prod_results)

    # Attach delta to each stage result
    for p in stage_results:
        p["rank_delta"] = rank_delta.get(str(p["id"]))

    stage_metrics = {
        "ndcg_at_10": compute_ndcg(stage_results, k=10),
        "ndcg_at_50": compute_ndcg(stage_results, k=50),
        "ndcg_at_150": compute_ndcg(stage_results, k=150),
        **compute_recall_stats(stage_results, k_list=(10, 50, 150)),
        "category_distribution": compute_category_distribution(stage_results),
    }
    prod_metrics = {
        "ndcg_at_10": compute_ndcg(prod_results, k=10),
        "ndcg_at_50": compute_ndcg(prod_results, k=50),
        "ndcg_at_150": compute_ndcg(prod_results, k=150),
        **compute_recall_stats(prod_results, k_list=(10, 50, 150)),
        "category_distribution": compute_category_distribution(prod_results),
    }

    return {
        "success": True,
        "keyword": req.keyword,
        "stage": {"total": stage_total, "results": stage_results, "metrics": stage_metrics},
        "production": {"total": prod_total, "results": prod_results, "metrics": prod_metrics},
    }

# ─── Batch Audit Endpoints ──────────────────────────────────────────────────

@app.get("/api/keywords")
def get_keywords():
    return {"success": True, "keywords": batch_engine.keyword_list}

@app.post("/api/keywords")
def update_keywords(req: KeywordListRequest):
    batch_engine.save_keywords(req.keywords)
    return {"success": True, "count": len(req.keywords)}

@app.post("/api/batch/run")
def run_batch(req: BatchRunRequest):
    if batch_engine.is_running:
        raise HTTPException(status_code=400, detail="Batch job already running")
    batch_engine.run_batch(req.cookie)
    return {"success": True, "status": "started"}

@app.post("/api/batch/stop")
def stop_batch():
    batch_engine.stop_batch()
    return {"success": True, "status": "stopped"}

@app.get("/api/batch/status")
def get_batch_status():
    return {
        "is_running": batch_engine.is_running,
        "progress": batch_engine.progress,
        "total_keywords": len(batch_engine.keyword_list),
        "results_count": len(batch_engine.results)
    }

@app.get("/api/batch/results")
def get_batch_results():
    """回傳所有關鍵字的彙總數據 (Summary Table 用)"""
    return {
        "success": True,
        "results": list(batch_engine.results.values())
    }

@app.get("/api/feedback")
def get_all_feedback():
    return {"success": True, "feedback": calibration_manager.feedback}

@app.post("/api/feedback")
def save_feedback(req: FeedbackRequest):
    success = calibration_manager.save_feedback(req.keyword, req.product_id, req.user_tier, req.comment)
    return {"success": success}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
