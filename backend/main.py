from typing import Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from loguru import logger

from kkday_api import (
    fetch_kkday_products,
    fetch_kkday_products_v3,
    DEFAULT_LANG,
    DEFAULT_LOCALE,
    DEFAULT_CHANNEL,
)
from skills.metrics import compute_ndcg, compute_recall_stats
from skills.data_sanitizer import sanitizer
from batch_engine import engine as batch_engine
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager
from skills.synonym_service import synonym_service
from ab_check import run_ab_check, find_rank as ab_find_rank
import ab_check_runner
from baseline_service import baseline_service, BASELINE_DROP_MULTIPLIER, _safe_int
from baseline_version_manager import baseline_version_manager
import baseline_scheduler

import sys as _sys
from pathlib import Path as _Path
# Support both local (backend/../handoff/scripts) and Docker (/app/handoff/scripts)
_base_dir = _Path(__file__).resolve().parent
for _candidate in [
    _base_dir.parent / "handoff" / "scripts",
    _base_dir / "handoff" / "scripts",
]:
    if _candidate.is_dir():
        _path_str = str(_candidate)
        if _path_str not in _sys.path:
            _sys.path.insert(0, _path_str)
        break

# ── Structured JSON logging for Kibana ────────────────────────────────────────
# Human-readable logs keep going to stderr (captured in backend.log). In addition,
# any log call tagged with an `event` bind field is mirrored as one JSON object per
# line to logs/api_events.jsonl, so Filebeat/Kibana can index every bound field
# (keyword, version_a/b, intersection, mid_warnings, request_id, …) under `extra`.
# Registered from the FastAPI startup event (NOT at import) so merely importing this
# module — e.g. `from main import _normalize_mid` in unit tests — does not create a
# logs dir or spin up a background sink thread.
_kibana_sink_added = False


def _setup_kibana_sink():
    # Idempotent: the startup event can fire more than once in a process (e.g. a
    # TestClient(app) context manager, or a future lifespan re-init); without this
    # guard each re-entry adds another sink and every event is written N times.
    global _kibana_sink_added
    if _kibana_sink_added:
        return
    _kibana_sink_added = True
    log_dir = _base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "api_events.jsonl",
        level="INFO",
        serialize=True,          # emit JSON; bound fields land under record["extra"]
        rotation="20 MB",
        retention="14 days",
        enqueue=True,            # non-blocking, safe across the thread-pool executors
        filter=lambda r: "event" in r["extra"],
    )

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
    lang: str = DEFAULT_LANG
    locale: str = DEFAULT_LOCALE
    channel: str = DEFAULT_CHANNEL

class FeedbackRequest(BaseModel):
    keyword: str
    product_id: str
    user_tier: int
    comment: str
    synonyms: Optional[list[str]] = None

class BatchRunRequest(BaseModel):
    cookie: str
    ai_enabled: Optional[bool] = None
    search_api: Optional[str] = "ajax"   # "ajax" or "v3"
    version_a: Optional[int] = 0
    version_b: Optional[int] = None      # None = 不跑 B 版
    lang: str = DEFAULT_LANG
    locale: str = DEFAULT_LOCALE
    channel: str = DEFAULT_CHANNEL

class KeywordListRequest(BaseModel):
    keywords: list[Any]

class ABCheckRequest(BaseModel):
    version_a: int
    version_b: int
    cookie: str = ""
    skip_precise: bool = False
    skip_broad: bool = False
    lang: str = DEFAULT_LANG
    locale: str = DEFAULT_LOCALE
    channel: str = DEFAULT_CHANNEL

class ABCheckStartRequest(BaseModel):
    type: str  # 'precise' | 'broad'
    version_a: int
    version_b: int
    cookie: str = ""
    limit: Optional[int] = None
    resume_run_id: Optional[str] = None
    lang: str = DEFAULT_LANG
    locale: str = DEFAULT_LOCALE
    channel: str = DEFAULT_CHANNEL

class ABCheckCancelRequest(BaseModel):
    run_id: str

class UnifiedSearchRequest(BaseModel):
    keyword: str
    cookie: str = ""
    count: int = 300
    ai_enabled: bool = False
    search_api: str = "v3"
    version_a: int = 3
    version_b: Optional[int] = None
    lang: str = DEFAULT_LANG
    locale: str = DEFAULT_LOCALE
    channel: str = DEFAULT_CHANNEL

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
    ran = batch_engine.run_batch_sync(cookie, ai_enabled_override=bool(s["ai_enabled"]), keyword_list_override=kw_override, search_api=s.get("search_api", "ajax"),
                                      version_a=s.get("version_a", 0), version_b=s.get("version_b"))
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
    _setup_kibana_sink()
    scheduler.start()
    _reload_scheduler_jobs()
    baseline_scheduler.register_job(scheduler)
    # Mark any ab-check runs that were in-flight when the process died
    # as `interrupted`, so the UI can offer a resume button.
    n = ab_check_runner.sweep_interrupted_runs()
    if n:
        logger.warning(f"[ABRunner] startup swept {n} interrupted run(s)")


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
    # v3 search API sale_status: 1 = on sale, 0 = "not purchasable" (下架/售罄/暫停
    # 的合併訊號). Normalize to int at the API boundary so the frontend can safely
    # use strict `=== 0`: v3 has been observed to inconsistently serialize numeric
    # fields as str across test_exp versions (see _coerce_product_id for prod_mid),
    # and we don't want the badge to silently vanish if the API flips to "0".
    ss = p.get("sale_status")
    if ss is not None and not isinstance(ss, bool):
        try:
            ss = int(ss)
        except (TypeError, ValueError):
            pass  # leave non-numeric values visible for downstream anomaly detection
    return {
        "rank": rank, "id": str(p.get("prod_oid") or p.get("oid") or p.get("product_id") or rank),
        "name": p.get("name", ""), "img_url": p.get("img_url", ""), "url": p.get("url", ""),
        "tier": result["tier"], "mismatch_reasons": result["mismatch_reasons"],
        "rank_delta": None,
        "main_cat_key": cat_code,
        "destinations": sanitizer.get_destinations(p),
        "show_order_count": p.get("show_order_count", ""),
        "sale_status": ss,
    }

@app.post("/api/compare")
def compare_envs(req: CompareRequest):
    ai_metadata = judger.get_ai_metadata(req.keyword, ai_enabled=(req.ai_enabled or False))
    fetch_fn = fetch_kkday_products_v3 if req.search_api == "v3" else fetch_kkday_products
    fetch_kwargs = {"keyword": req.keyword, "env": "stage", "cookie": req.cookie, "row_count": req.count}
    if req.search_api == "v3":
        fetch_kwargs.update(lang=req.lang, locale=req.locale, channel=req.channel)
    stage_prods, stage_total, _ = fetch_fn(**fetch_kwargs)
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
    # Deprecated: prefer POST /api/ab-check/start (async + checkpointed).
    # Kept temporarily for un-migrated callers; will be removed when UI flips.
    logger.warning(
        "[Deprecation] POST /api/ab-check is deprecated; "
        "migrate to /api/ab-check/start (async + checkpointed)"
    )
    cookie = req.cookie or os.getenv("KKDAY_SEARCH_COOKIE", "")
    result = run_ab_check(
        version_a=req.version_a,
        version_b=req.version_b,
        cookie=cookie,
        skip_precise=req.skip_precise,
        skip_broad=req.skip_broad,
        lang=req.lang,
        locale=req.locale,
        channel=req.channel,
    )
    return {"success": True, **result}


# ── AB-check runner (new, async + checkpointed) ───────────────────────────────

@app.post("/api/ab-check/start")
def ab_check_start(req: ABCheckStartRequest):
    if req.type not in ("precise", "broad"):
        raise HTTPException(status_code=400, detail="type must be 'precise' or 'broad'")
    cookie = req.cookie or os.getenv("KKDAY_SEARCH_COOKIE", "")
    try:
        run_id = ab_check_runner.start_run(
            type_=req.type,
            version_a=req.version_a,
            version_b=req.version_b,
            cookie=cookie,
            limit=req.limit,
            resume_run_id=req.resume_run_id,
            sync=False,
            lang=req.lang,
            locale=req.locale,
            channel=req.channel,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    run = ab_check_runner.get_run(run_id)
    return {
        "run_id": run_id,
        "status": run["status"],
        "total_queries": run["total_queries"],
        # PR #28: 立即回 run-level locale,讓前端在 polling 第一輪之前就能顯示。
        # Resume 時這裡會回 parent 的值(start_run 內已 inherit),前端因此能立刻
        # 看到「沿用了哪個 locale」,不會等 2s 才更新。
        "lang": run.get("lang"),
        "locale": run.get("locale"),
        "channel": run.get("channel"),
    }


@app.get("/api/ab-check/status")
def ab_check_status(run_id: str, since_idx: int = 0):
    run = ab_check_runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
    rows = ab_check_runner.get_checkpoints(run_id, since_idx=since_idx)
    return {
        "run": run,
        "progress": {
            "done": run["done_count"],
            "total": run["total_queries"],
            "running_idx": ab_check_runner.get_running_idx(run_id),
        },
        "rows": rows,
    }


@app.post("/api/ab-check/cancel")
def ab_check_cancel(req: ABCheckCancelRequest):
    run = ab_check_runner.get_run(req.run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run_id not found: {req.run_id}")
    if run["status"] != "running":
        return {"ok": False, "reason": f"run already {run['status']}"}
    if ab_check_runner.request_cancel(req.run_id):
        return {"ok": True}
    # status='running' in DB but no in-memory flag — worker dead or running
    # in another process. Unstick the DB row so the UI can recover.
    flipped = ab_check_runner.force_interrupt_run(req.run_id)
    return {
        "ok": flipped,
        "reason": "worker not in current process; flipped to interrupted" if flipped
                  else "worker not in current process and DB update failed",
    }


@app.get("/api/ab-check/history")
def ab_check_history(type: Optional[str] = None, limit: int = 50):
    return ab_check_runner.list_runs(type_=type, limit=limit)


@app.get("/api/ab-check/history/{run_id}")
def ab_check_history_detail(run_id: str):
    run = ab_check_runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run_id not found: {run_id}")
    rows = ab_check_runner.get_checkpoints(run_id, since_idx=0)
    return {"run": run, "rows": rows}

@app.get("/api/baseline/keywords")
def get_baseline_keywords():
    kws = baseline_service.get_all_keywords()
    return {
        "success": True,
        "keywords": kws,
        "total": len(kws),
        "precise_count": len(baseline_service._precise),
        "broad_count": len(baseline_service._broad),
    }


@app.post("/api/baseline/upload")
async def upload_baseline(file: UploadFile = File(...), type: Optional[str] = Form(None)):
    """Upload a baseline CSV (Plan B for when BQ fetch is unavailable).
    HTML upload deprecated — use BQ fetch or manually-exported CSV instead."""
    content = await file.read()
    filename = file.filename or ""

    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="只支援 .csv 檔案（HTML 上傳已停用，請改用 BQ 自動 fetch 或手動匯出 CSV）")

    if type not in ("precise", "broad"):
        raise HTTPException(status_code=400, detail="CSV 上傳需指定 type=precise 或 type=broad")

    text = content.decode("utf-8")
    first_line = text.split("\n", 1)[0].lower()
    if type == "precise" and not all(k in first_line for k in ("query", "top1_prod_mid", "top2_prod_mid")):
        raise HTTPException(status_code=400, detail="精準詞 CSV header 必須包含 query, top1_prod_mid, top2_prod_mid")
    if type == "broad" and not all(k in first_line for k in ("query", "prod_mid", "profit_rank")):
        raise HTTPException(status_code=400, detail="泛詞 CSV header 必須包含 query, prod_mid, profit_rank")

    precise_csv = text if type == "precise" else None
    broad_csv = text if type == "broad" else None
    meta = baseline_version_manager.create_version(precise_csv, broad_csv, source_filename=filename)
    baseline_service.reload()
    return {"success": True, "mode": "csv", "type": type, "version": meta}


@app.get("/api/baseline/versions")
def list_baseline_versions():
    versions = baseline_version_manager.list_versions()
    return {"success": True, "versions": versions}


class RollbackRequest(BaseModel):
    timestamp: str

@app.post("/api/baseline/rollback")
def rollback_baseline(req: RollbackRequest):
    timestamp = req.timestamp
    meta = baseline_version_manager.activate(timestamp)
    if not meta:
        raise HTTPException(status_code=404, detail=f"版本 {timestamp} 不存在")
    baseline_service.reload()
    return {"success": True, "version": meta}


@app.delete("/api/baseline/versions/{timestamp}")
def archive_baseline_version(timestamp: str):
    """Archive (soft-delete) a non-active baseline version."""
    ok = baseline_version_manager.archive(timestamp)
    if not ok:
        raise HTTPException(status_code=400, detail="無法刪除：版本不存在或為使用中版本")
    return {"success": True}


@app.post("/api/baseline/reload")
def reload_baseline():
    baseline_service.reload()
    kws = baseline_service.get_all_keywords()
    return {"success": True, "total_keywords": len(kws)}


@app.post("/api/baseline/refresh-from-bq")
def refresh_baseline_from_bq():
    """Manually trigger BQ fetch + activate, bypassing the daily cron."""
    last_run = baseline_scheduler.run_now()
    if last_run.get("success"):
        baseline_service.reload()
    return {"success": last_run["success"], "last_run": last_run}


@app.get("/api/baseline/source-status")
def baseline_source_status():
    """Last fetch outcome (for UI banner) + active version meta."""
    cfg = baseline_scheduler.get_config()
    active = baseline_version_manager.get_active_version()
    return {
        "success": True,
        "cron": {"enabled": cfg["enabled"], "hour": cfg["hour"], "minute": cfg["minute"]},
        "last_run": cfg.get("last_run"),
        "active_version": active,
    }


class CronScheduleRequest(BaseModel):
    hour: int
    minute: int
    enabled: bool = True

@app.get("/api/baseline/cron-schedule")
def get_baseline_cron_schedule():
    cfg = baseline_scheduler.get_config()
    return {"success": True, "schedule": {k: cfg[k] for k in ("enabled", "hour", "minute")}}

@app.patch("/api/baseline/cron-schedule")
def patch_baseline_cron_schedule(req: CronScheduleRequest):
    try:
        cfg = baseline_scheduler.update_schedule(scheduler, req.hour, req.minute, req.enabled)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "schedule": {k: cfg[k] for k in ("enabled", "hour", "minute")}}


def _normalize_mid(mid):
    """Coerce a prod_mid to int, returning 0 for missing/non-numeric values.
    Thin 0-sentinel adapter over baseline_service._safe_int (the single int(float())
    parser) — 0 is the 'no valid id' marker the cross-version match + mid_warnings
    detection rely on (real prod_mids are non-zero positive ints)."""
    return _safe_int(mid) or 0


def _process_version(keyword, cookie, count, ai_enabled, search_api, test_exp,
                     lang=DEFAULT_LANG, locale=DEFAULT_LOCALE, channel=DEFAULT_CHANNEL,
                     request_id=None):
    """Fetch + judge + annotate a single version. Returns (results, total, metrics)."""
    ai_metadata = judger.get_ai_metadata(keyword, ai_enabled=ai_enabled)
    fetch_fn = fetch_kkday_products_v3 if search_api == "v3" else fetch_kkday_products
    kwargs = {"keyword": keyword, "env": "stage", "cookie": cookie, "row_count": count}
    if search_api == "v3":
        kwargs["test_exp"] = test_exp
        kwargs["lang"] = lang
        kwargs["locale"] = locale
        kwargs["channel"] = channel
    prods, total, _ = fetch_fn(**kwargs)

    results = []
    mid_warnings = []
    for i, p in enumerate(prods):
        res = judger.process_and_calibrate(p, i + 1, keyword, ai_metadata, _slim_product)
        res["rank_delta"] = None
        # Carry prod_mid for baseline annotation + cross-version matching.
        # NOTE: the v3 API is inconsistent about prod_mid's JSON type across test_exp
        # versions (int for some experiments, str for others). It is int-coerced at the
        # v3 boundary (kkday_api._coerce_product_id); _normalize_mid collapses anything
        # left to int so 137689 == "137689" instead of 100% "未出現".
        # Match on prod_mid ONLY — prod_oid is a different id namespace (can differ from
        # prod_mid), so it must NOT be a fallback key or it mis-matches across versions.
        raw_mid, raw_oid = p.get("prod_mid"), p.get("prod_oid")
        mid = _normalize_mid(raw_mid)
        res["prod_mid"] = mid
        # Every real v3 product carries a non-zero positive integer prod_mid. Resolving
        # to <= 0 means the API changed shape / sent a malformed id — surface it instead
        # of silently keying the row on 0 (which reads as "未出現"). Only flag for v3:
        # the legacy (ajax) API legitimately lacks prod_mid, so warning there is noise.
        if mid <= 0 and search_api == "v3":
            mid_warnings.append({
                "rank": i + 1,
                "prod_mid": raw_mid,
                "prod_oid": raw_oid,
                "name": res.get("name", ""),
            })
        results.append(res)

    if mid_warnings:
        logger.bind(
            event="mid_warning",
            ts=datetime.now(TZ_TAIPEI).isoformat(),
            request_id=request_id,
            keyword=keyword,
            test_exp=test_exp,
            search_api=search_api,
            lang=lang, locale=locale, channel=channel,
            count=len(mid_warnings),
            returned=len(results),
            samples=mid_warnings[:5],
        ).error(
            f"unresolvable prod_mid keyword={keyword!r} test_exp={test_exp} "
            f"count={len(mid_warnings)} (expected non-zero positive int)"
        )

    baseline_service.annotate_products(keyword, results)
    baseline_alerts = baseline_service.find_baseline_alerts(keyword, results)

    metrics = {
        "ndcg_at_10": compute_ndcg(results, 10),
        "ndcg_at_50": compute_ndcg(results, 50),
        "ndcg_at_150": compute_ndcg(results, 150),
        **compute_recall_stats(results),
    }

    return results, total, metrics, baseline_alerts, mid_warnings


def _compute_ab_comparison(keyword, a_results, b_results):
    """Compare two result sets using ab_check severity logic.
    Reuses baseline_service singleton instead of re-reading CSVs."""
    from ab_check import check_ab_precise, check_ab_broad

    # prod_mid is already a normalized int here: _process_version sets it via
    # _normalize_mid, and the v3 boundary (_coerce_product_id) coerces upstream.
    a_mids = tuple(r.get("prod_mid", 0) for r in a_results)
    b_mids = tuple(r.get("prod_mid", 0) for r in b_results)

    bl = baseline_service.get_baseline(keyword)
    if not bl["has_data"]:
        return {"rank_changes": [], "summary": {"total_changes": 0, "P0": 0, "P1": 0, "P2": 0, "INFO": 0}}

    rank_changes = []

    # Check precise baseline
    precise = bl.get("precise")
    if precise:
        for rank_n, prefix in [(1, "top1"), (2, "top2")]:
            mid = precise.get(f"{prefix}_prod_mid")  # already int|None via _safe_int at load
            if not mid:
                continue
            a_rank = ab_find_rank(mid, a_mids)
            b_rank = ab_find_rank(mid, b_mids)
            alert = check_ab_precise(keyword, mid, rank_n, a_rank, b_rank)
            if alert or (a_rank != b_rank):
                rank_changes.append({
                    "prod_mid": mid,
                    "name": precise.get(f"{prefix}_prod_nm", ""),
                    "a_rank": a_rank,
                    "b_rank": b_rank,
                    "delta": (b_rank - a_rank) if (a_rank and b_rank) else None,
                    "baseline_tag": f"precise_top{rank_n}",
                    "severity": alert.severity if alert else "OK",
                    "stage_status": alert.stage_status if alert else None,
                })

    # Check broad baseline
    for entry in bl.get("broad_products", []):
        mid = entry.get("prod_mid")  # already int|None via _safe_int at load
        if not mid:
            continue
        bl_rank = entry.get("profit_rank", 0)
        a_rank = ab_find_rank(mid, a_mids)
        b_rank = ab_find_rank(mid, b_mids)
        alert = check_ab_broad(keyword, mid, bl_rank, a_rank, b_rank)
        if any(rc["prod_mid"] == mid for rc in rank_changes):
            continue
        if alert or (a_rank != b_rank):
            rank_changes.append({
                "prod_mid": mid,
                "name": entry.get("prod_nm", ""),
                "a_rank": a_rank,
                "b_rank": b_rank,
                "delta": (b_rank - a_rank) if (a_rank and b_rank) else None,
                "baseline_tag": f"broad_rank_{bl_rank}",
                "severity": alert.severity if alert else "OK",
                "stage_status": alert.stage_status if alert else None,
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

    request_id = uuid.uuid4().hex[:12]
    t0 = time.monotonic()
    cookie = req.cookie or os.getenv("KKDAY_SEARCH_COOKIE", "")
    kw = req.keyword.strip()
    if not kw:
        raise HTTPException(status_code=400, detail="keyword is required")

    baseline = baseline_service.get_baseline(kw)
    loop = asyncio.get_running_loop()

    # A/B versions in parallel using threads (requests is sync)
    a_future = loop.run_in_executor(
        None, _process_version, kw, cookie, req.count, req.ai_enabled, req.search_api, req.version_a,
        req.lang, req.locale, req.channel, request_id,
    )
    if req.version_b is not None:
        b_future = loop.run_in_executor(
            None, _process_version, kw, cookie, req.count, req.ai_enabled, req.search_api, req.version_b,
            req.lang, req.locale, req.channel, request_id,
        )
        (a_results, a_total, a_metrics, a_alerts, a_mid_warnings), (b_results, b_total, b_metrics, b_alerts, b_mid_warnings) = await asyncio.gather(a_future, b_future)
    else:
        a_results, a_total, a_metrics, a_alerts, a_mid_warnings = await a_future
        b_results = b_total = b_metrics = b_alerts = b_mid_warnings = None

    response = {
        "success": True,
        "keyword": kw,
        "baseline": baseline,
        "baseline_drop_multiplier": BASELINE_DROP_MULTIPLIER,
        "version_a": {
            "test_exp": req.version_a,
            "total": a_total,
            "results": a_results,
            "metrics": a_metrics,
            "baseline_alerts": a_alerts,
            "mid_warnings": a_mid_warnings,
        },
        "version_b": {
            "test_exp": req.version_b,
            "total": b_total,
            "results": b_results,
            "metrics": b_metrics,
            "baseline_alerts": b_alerts,
            "mid_warnings": b_mid_warnings,
        } if b_results is not None else None,
        "ab_comparison": None,
    }

    if b_results is not None:
        response["ab_comparison"] = _compute_ab_comparison(kw, a_results, b_results)

    response["request_id"] = request_id

    # ── Structured event for Kibana ──────────────────────────────────────────
    # One JSON line per search. The A/B *match stats* (intersection / a_only /
    # b_only) are the canary for prod_mid-keying bugs: a healthy reorder keeps a
    # large intersection, whereas intersection==0 with both sides non-empty is the
    # exact signature of the int-vs-str regression this whole change fixed.
    ab_enabled = b_results is not None
    a_keys = {r.get("prod_mid") for r in a_results if r.get("prod_mid")}
    b_keys = {r.get("prod_mid") for r in (b_results or []) if r.get("prod_mid")}
    intersection = len(a_keys & b_keys) if ab_enabled else None
    logger.bind(
        event="unified_search",
        ts=datetime.now(TZ_TAIPEI).isoformat(),
        request_id=request_id,
        keyword=kw,
        search_api=req.search_api,
        version_a=req.version_a,
        version_b=req.version_b,
        ab_enabled=ab_enabled,
        lang=req.lang, locale=req.locale, channel=req.channel,
        count_requested=req.count,
        cookie_present=bool(cookie),
        a_total=a_total,
        b_total=b_total,
        a_returned=len(a_results),
        b_returned=(len(b_results) if ab_enabled else None),
        mid_warnings_a=len(a_mid_warnings or []),
        mid_warnings_b=(len(b_mid_warnings or []) if ab_enabled else None),
        match_intersection=intersection,
        match_a_only=(len(a_keys - b_keys) if ab_enabled else None),
        match_b_only=(len(b_keys - a_keys) if ab_enabled else None),
        ab_summary=(response["ab_comparison"]["summary"] if response["ab_comparison"] else None),
        duration_ms=round((time.monotonic() - t0) * 1000),
    ).info(
        f"unified-search keyword={kw!r} vA={req.version_a} vB={req.version_b} "
        f"intersection={intersection if ab_enabled else 'n/a'} "
        f"mid_warn_a={len(a_mid_warnings or [])} request_id={request_id}"
    )

    return response


@app.post("/api/feedback")
def calibrate_feedback(req: FeedbackRequest):
    calibration_manager.save_feedback(req.keyword, req.product_id, req.user_tier, req.comment)
    if req.synonyms:
        synonym_service.add_synonyms(req.keyword, req.synonyms)
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
    batch_engine.run_batch(req.cookie, ai_enabled_override=req.ai_enabled, search_api=req.search_api,
                          version_a=req.version_a, version_b=req.version_b,
                          lang=req.lang, locale=req.locale, channel=req.channel)
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
