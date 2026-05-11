from typing import Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from loguru import logger

from kkday_api import fetch_kkday_products, fetch_kkday_products_v3
from skills.metrics import compute_ndcg, compute_recall_stats
from skills.data_sanitizer import sanitizer
from batch_engine import engine as batch_engine
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager
from ab_check import run_ab_check, find_rank as ab_find_rank
from baseline_service import baseline_service

TZ_TAIPEI = timezone(timedelta(hours=8))  # UTC+8, no system tzdata needed
scheduler = BackgroundScheduler(timezone=TZ_TAIPEI)

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
    search_api: Optional[str] = "ajax"   # "ajax" or "v3"

class FeedbackRequest(BaseModel):
    keyword: str
    product_id: str
    user_tier: int
    comment: str

class BatchRunRequest(BaseModel):
    cookie: str
    ai_enabled: Optional[bool] = None
    search_api: Optional[str] = "ajax"   # "ajax" or "v3"

class KeywordListRequest(BaseModel):
    keywords: list[Any]

class ABCheckRequest(BaseModel):
    version_a: int
    version_b: int
    skip_precise: bool = False
    skip_broad: bool = False

class UnifiedSearchRequest(BaseModel):
    keyword: str
    cookie: str = ""
    count: int = 300
    ai_enabled: bool = False
    search_api: str = "v3"
    version_a: int = 3
    version_b: Optional[int] = None

class ExplainRequest(BaseModel):
    keyword: str
    product_name: str
    tier: int
    mismatch_reasons: list[str] = []
    destinations: list[Any] = []
    main_cat_key: str = ""

_STAGE_URL = "https://www.stage.kkday.com/zh-tw/product/productlist/esim"
_PROD_URL  = "https://www.kkday.com/zh-tw/product/productlist/esim"

def _fetch_cookie(url: str) -> str:
    """Fetch a guest cookie from KKDay via Playwright for the given URL."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="zh-TW",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        cookies = context.cookies()
        browser.close()
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

def _fetch_stage_cookie() -> str:
    """Convenience wrapper used by the scheduler."""
    return _fetch_cookie(_STAGE_URL)


def _next_run_str(schedule: dict) -> str:
    """Compute next run time string for a schedule dict."""
    freq = schedule["freq"]
    h, m = schedule["hour"], schedule["minute"]
    now = datetime.now(TZ_TAIPEI)
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if freq == "daily":
        if candidate <= now:
            candidate += timedelta(days=1)
    elif freq == "monthly":
        candidate = candidate.replace(day=1)
        if candidate <= now:
            if candidate.month == 12:
                candidate = candidate.replace(year=candidate.year+1, month=1, day=1)
            else:
                candidate = candidate.replace(month=candidate.month+1, day=1)
    elif freq == "weekly":
        days = [int(d) for d in (schedule.get("day_of_week") or "0").split(",")]
        for delta in range(8):
            test = (now + timedelta(days=delta)).replace(hour=h, minute=m, second=0, microsecond=0)
            if test.weekday() in days and test > now:
                candidate = test
                break
    elif freq == "biweekly":
        # Anchor to last_run to preserve the correct 2-week on/off cycle.
        # Falls back to created_at, then to now + 14 days for first-ever run.
        epoch_str = schedule.get("last_run") or schedule.get("created_at")
        if epoch_str:
            base = datetime.fromisoformat(epoch_str).replace(hour=h, minute=m, second=0, microsecond=0)
            candidate = base + timedelta(weeks=2)
            # Advance if somehow behind (e.g. missed cycles)
            while candidate <= now:
                candidate += timedelta(weeks=2)
        else:
            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(weeks=2)
    return candidate.isoformat()


def _run_scheduled_batch(schedule_id: int):
    """Called by APScheduler to auto-run a batch."""
    schedules = batch_engine.list_schedules()
    s = next((x for x in schedules if x["id"] == schedule_id), None)
    if not s or not s["enabled"]:
        return
    logger.info(f"[Scheduler] Starting scheduled batch for schedule_id={schedule_id}")
    try:
        cookie = _fetch_stage_cookie()
    except Exception as e:
        logger.error(f"[Scheduler] Cookie fetch failed: {e}")
        return
    # Use schedule-specific keywords if set, otherwise fall back to global list
    kw_override = s.get("keywords") if s.get("keywords") else None
    # run_batch_sync blocks until the batch finishes (APScheduler already provides a thread)
    ran = batch_engine.run_batch_sync(cookie, ai_enabled_override=bool(s["ai_enabled"]), keyword_list_override=kw_override, search_api=s.get("search_api", "ajax"))
    if not ran:
        logger.warning(f"[Scheduler] Skipped schedule_id={schedule_id}: a batch was already running.")
        return
    # Only update last_run and notify after the batch truly finishes
    next_run = _next_run_str(s)
    batch_engine.update_last_run(schedule_id, next_run)
    if s.get("slack_notify"):
        webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
        if webhook:
            try:
                import httpx as _httpx
                _httpx.post(webhook, json={"text": f"✅ 定期批次巡檢完成 (schedule #{schedule_id})"}, timeout=10)
            except Exception:
                pass


def _reload_scheduler_jobs():
    """Sync APScheduler jobs with DB schedules."""
    # Remove existing schedule jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("schedule_"):
            scheduler.remove_job(job.id)
    # Re-add enabled schedules
    for s in batch_engine.list_schedules():
        if not s["enabled"]:
            continue
        freq = s["freq"]
        h, m = s["hour"], s["minute"]
        sid = s["id"]
        try:
            if freq == "daily":
                trigger = CronTrigger(hour=h, minute=m, timezone=TZ_TAIPEI)
            elif freq == "weekly":
                dow = s.get("day_of_week") or "0"
                trigger = CronTrigger(day_of_week=dow, hour=h, minute=m, timezone=TZ_TAIPEI)
            elif freq == "biweekly":
                # Calculate first occurrence for start_date
                start_dt = datetime.fromisoformat(_next_run_str(s))
                trigger = IntervalTrigger(weeks=2, start_date=start_dt, timezone=TZ_TAIPEI)
            elif freq == "monthly":
                trigger = CronTrigger(day=1, hour=h, minute=m, timezone=TZ_TAIPEI)
            else:
                continue
            scheduler.add_job(
                _run_scheduled_batch,
                trigger=trigger,
                id=f"schedule_{sid}",
                args=[sid],
                replace_existing=True,
                misfire_grace_time=3600,
            )
            logger.info(f"[Scheduler] Loaded schedule_id={sid} freq={freq} {h:02d}:{m:02d}")
        except Exception as e:
            logger.error(f"[Scheduler] Failed to add job for schedule_id={sid}: {e}")


@app.on_event("startup")
def startup_event():
    scheduler.start()
    _reload_scheduler_jobs()


@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown(wait=False)


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
def get_guest_cookie(env: str = "stage"):
    if env == "production":
        url = _PROD_URL
    elif env == "stage":
        url = _STAGE_URL
    else:
        raise HTTPException(status_code=400, detail="env must be stage or production")

    try:
        cookie_str = _fetch_cookie(url)
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
    fetch_fn = fetch_kkday_products_v3 if req.search_api == "v3" else fetch_kkday_products
    stage_prods, stage_total, _ = fetch_fn(req.keyword, "stage", req.cookie, req.count)
    # Production disabled (Datadome blocks prod API)
    prod_res = []

    stage_res = [judger.process_and_calibrate(p, i+1, req.keyword, ai_metadata, _slim_product) for i, p in enumerate(stage_prods)]
    for p in stage_res: p["rank_delta"] = None

    final_results = {
        "success": True, "keyword": req.keyword,
        "stage": {"total": stage_total, "results": stage_res, "metrics": {
            "ndcg_at_10": compute_ndcg(stage_res, 10), "ndcg_at_50": compute_ndcg(stage_res, 50),
            "ndcg_at_150": compute_ndcg(stage_res, 150), **compute_recall_stats(stage_res)
        }},
        "production": {"total": 0, "results": [], "metrics": {
            "ndcg_at_10": 0, "ndcg_at_50": 0, "ndcg_at_150": 0,
            "mismatch_rate": 0, "tier1_rate": 0, "tier2_rate": 0, "tier3_rate": 0
        }}
    }

    # 自動存檔單次巡檢結果 (New)
    batch_engine.save_single_record(req.keyword, final_results)
    
    return final_results

@app.post("/api/ab-check")
def ab_check(req: ABCheckRequest):
    cookie = os.getenv("KKDAY_SEARCH_COOKIE", "")
    result = run_ab_check(
        version_a=req.version_a,
        version_b=req.version_b,
        cookie=cookie,
        skip_precise=req.skip_precise,
        skip_broad=req.skip_broad,
    )
    return {"success": True, **result}

@app.get("/api/baseline/keywords")
def get_baseline_keywords():
    kws = baseline_service.get_all_keywords()
    return {
        "success": True,
        "keywords": kws,
        "total": len(kws),
    }


def _process_version(keyword, cookie, count, ai_enabled, search_api, test_exp):
    """Fetch + judge + annotate a single version. Returns (results, total, metrics)."""
    ai_metadata = judger.get_ai_metadata(keyword, ai_enabled=ai_enabled)
    fetch_fn = fetch_kkday_products_v3 if search_api == "v3" else fetch_kkday_products
    kwargs = {"keyword": keyword, "env": "stage", "cookie": cookie, "row_count": count}
    if search_api == "v3":
        kwargs["test_exp"] = test_exp
    prods, total, _ = fetch_fn(**kwargs)

    results = []
    for i, p in enumerate(prods):
        res = judger.process_and_calibrate(p, i + 1, keyword, ai_metadata, _slim_product)
        res["rank_delta"] = None
        # Carry prod_mid for baseline annotation
        res["prod_mid"] = p.get("prod_mid") or p.get("prod_oid") or 0
        results.append(res)

    baseline_service.annotate_products(keyword, results)
    baseline_alerts = baseline_service.find_baseline_alerts(keyword, results)

    metrics = {
        "ndcg_at_10": compute_ndcg(results, 10),
        "ndcg_at_50": compute_ndcg(results, 50),
        "ndcg_at_150": compute_ndcg(results, 150),
        **compute_recall_stats(results),
    }

    return results, total, metrics, baseline_alerts


def _compute_ab_comparison(keyword, a_results, b_results):
    """Compare two result sets using ab_check severity logic."""
    from ab_check import (
        check_ab_precise, check_ab_broad,
        PRECISE_CSV, BROAD_CSV,
    )
    import pandas as pd

    a_mids = tuple(r.get("prod_mid", 0) for r in a_results)
    b_mids = tuple(r.get("prod_mid", 0) for r in b_results)

    rank_changes = []

    # Check precise baseline
    if PRECISE_CSV.exists():
        pdf = pd.read_csv(PRECISE_CSV)
        kw_row = pdf[pdf["query"] == keyword]
        if not kw_row.empty:
            row = kw_row.iloc[0]
            for rank_n, mid_col in [(1, "top1_prod_mid"), (2, "top2_prod_mid")]:
                mid = row[mid_col]
                if pd.isna(mid):
                    continue
                mid = int(mid)
                a_rank = ab_find_rank(mid, a_mids)
                b_rank = ab_find_rank(mid, b_mids)
                alert = check_ab_precise(keyword, mid, rank_n, a_rank, b_rank)
                if alert or (a_rank != b_rank):
                    name = row.get(f"top{rank_n}_prod_nm", "")
                    rank_changes.append({
                        "prod_mid": mid,
                        "name": name,
                        "a_rank": a_rank,
                        "b_rank": b_rank,
                        "delta": (b_rank - a_rank) if (a_rank and b_rank) else None,
                        "baseline_tag": f"precise_top{rank_n}",
                        "severity": alert.severity if alert else "OK",
                    })

    # Check broad baseline
    if BROAD_CSV.exists():
        bdf = pd.read_csv(BROAD_CSV)
        kw_group = bdf[bdf["query"] == keyword]
        for _, brow in kw_group.iterrows():
            mid = int(brow["prod_mid"])
            bl_rank = int(brow["profit_rank"])
            a_rank = ab_find_rank(mid, a_mids)
            b_rank = ab_find_rank(mid, b_mids)
            alert = check_ab_broad(keyword, mid, bl_rank, a_rank, b_rank)
            # Skip if already in rank_changes from precise
            if any(rc["prod_mid"] == mid for rc in rank_changes):
                continue
            if alert or (a_rank != b_rank):
                rank_changes.append({
                    "prod_mid": mid,
                    "name": brow.get("prod_nm", ""),
                    "a_rank": a_rank,
                    "b_rank": b_rank,
                    "delta": (b_rank - a_rank) if (a_rank and b_rank) else None,
                    "baseline_tag": f"broad_rank_{bl_rank}",
                    "severity": alert.severity if alert else "OK",
                })

    sev_counts = {"P0": 0, "P1": 0, "P2": 0, "INFO": 0}
    for rc in rank_changes:
        s = rc.get("severity", "OK")
        if s in sev_counts:
            sev_counts[s] += 1

    return {
        "rank_changes": rank_changes,
        "summary": {"total_changes": len(rank_changes), **sev_counts},
    }


@app.post("/api/unified-search")
async def unified_search(req: UnifiedSearchRequest):
    import asyncio

    cookie = req.cookie or os.getenv("KKDAY_SEARCH_COOKIE", "")
    kw = req.keyword.strip()
    if not kw:
        raise HTTPException(status_code=400, detail="keyword is required")

    baseline = baseline_service.get_baseline(kw)
    loop = asyncio.get_running_loop()

    # A/B versions in parallel using threads (requests is sync)
    a_future = loop.run_in_executor(
        None, _process_version, kw, cookie, req.count, req.ai_enabled, req.search_api, req.version_a
    )
    if req.version_b is not None:
        b_future = loop.run_in_executor(
            None, _process_version, kw, cookie, req.count, req.ai_enabled, req.search_api, req.version_b
        )
        (a_results, a_total, a_metrics, a_alerts), (b_results, b_total, b_metrics, b_alerts) = await asyncio.gather(a_future, b_future)
    else:
        a_results, a_total, a_metrics, a_alerts = await a_future
        b_results = b_total = b_metrics = b_alerts = None

    response = {
        "success": True,
        "keyword": kw,
        "baseline": baseline,
        "version_a": {
            "test_exp": req.version_a,
            "total": a_total,
            "results": a_results,
            "metrics": a_metrics,
            "baseline_alerts": a_alerts,
        },
        "version_b": {
            "test_exp": req.version_b,
            "total": b_total,
            "results": b_results,
            "metrics": b_metrics,
            "baseline_alerts": b_alerts,
        } if b_results is not None else None,
        "ab_comparison": None,
    }

    if b_results is not None:
        response["ab_comparison"] = _compute_ab_comparison(kw, a_results, b_results)

    return response


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
    batch_engine.run_batch(req.cookie, ai_enabled_override=req.ai_enabled, search_api=req.search_api)
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

class ScheduleCreateRequest(BaseModel):
    freq: str
    hour: int
    minute: int = 0
    day_of_week: Optional[str] = None
    env: str = "stage"
    ai_enabled: bool = False
    slack_notify: bool = False
    auto_diff: bool = False
    keywords: Optional[list] = None  # None = use global keyword list

class SchedulePatchRequest(BaseModel):
    freq: Optional[str] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    day_of_week: Optional[str] = None
    env: Optional[str] = None
    ai_enabled: Optional[bool] = None
    slack_notify: Optional[bool] = None
    auto_diff: Optional[bool] = None
    enabled: Optional[int] = None
    keywords: Optional[list] = None  # None = keep existing


@app.get("/api/batch/schedule")
def list_schedules():
    return batch_engine.list_schedules()


@app.post("/api/batch/schedule")
def create_schedule(req: ScheduleCreateRequest):
    logger.info(f"[Schedule] create req keywords={req.keywords!r}")
    kw_list = None
    if req.keywords:
        kw_list = [
            kw if isinstance(kw, dict) else {"keyword": kw, "ai_enabled": req.ai_enabled}
            for kw in req.keywords
        ]
    logger.info(f"[Schedule] kw_list={kw_list!r}")
    new_id = batch_engine.add_schedule(
        req.freq, req.hour, req.minute, req.day_of_week,
        req.env, req.ai_enabled, req.slack_notify, req.auto_diff,
        keywords=kw_list
    )
    _reload_scheduler_jobs()
    return {"success": True, "id": new_id}


@app.patch("/api/batch/schedule/{schedule_id}")
def patch_schedule(schedule_id: int, req: SchedulePatchRequest):
    raw = req.model_dump(exclude_none=True)
    logger.info(f"[Schedule] patch {schedule_id} raw={raw!r}")
    # Convert keywords list → keywords_json string for storage
    if "keywords" in raw:
        kw = raw.pop("keywords")
        raw["keywords_json"] = json.dumps(kw, ensure_ascii=False) if kw else None
    batch_engine.update_schedule(schedule_id, **raw)
    _reload_scheduler_jobs()
    return {"success": True}


@app.delete("/api/batch/schedule/{schedule_id}")
def remove_schedule(schedule_id: int):
    batch_engine.delete_schedule(schedule_id)
    _reload_scheduler_jobs()
    return {"success": True}


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
