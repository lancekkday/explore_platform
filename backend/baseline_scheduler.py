"""
Baseline BQ cron scheduler
==========================

Daily BQ fetch via APScheduler (in-process, shares main.py's scheduler).
Config + last-run status persisted to backend/data/baseline_cron.json.

Schema of baseline_cron.json:
{
  "enabled": true,
  "hour": 7, "minute": 0,            # Asia/Taipei
  "last_run": {                       # last attempt (success or fail)
    "ts": "2026-05-21T07:00:01+08:00",
    "trigger": "cron" | "manual",
    "success": true,
    "precise_rows": 895,
    "broad_rows": 7730,
    "warnings": ["broad: 7730 rows < previous 22560 × 50%"],
    "error": null
  }
}
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from baseline_bq_fetcher import fetch_from_bq, apply_and_activate

TZ_TAIPEI = timezone(timedelta(hours=8))

_DATA_DIR = Path(__file__).resolve().parent / "data"
CONFIG_PATH = _DATA_DIR / "baseline_cron.json"
JOB_ID = "baseline_bq_fetch"

DEFAULT_CONFIG = {
    "enabled": True,
    "hour": 7,
    "minute": 0,
    "last_run": None,
}

_lock = threading.Lock()


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # Fill missing keys
        return {**DEFAULT_CONFIG, **cfg}
    except Exception as e:
        logger.warning(f"[BaselineCron] config corrupt, falling back to defaults: {e}")
        return dict(DEFAULT_CONFIG)


def _save_config(cfg: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_config() -> dict:
    with _lock:
        return _load_config()


def update_schedule(scheduler, hour: int, minute: int, enabled: bool) -> dict:
    """Update cron time + enabled state; re-register the APScheduler job."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("hour must be 0-23, minute must be 0-59")
    with _lock:
        cfg = _load_config()
        cfg["hour"] = hour
        cfg["minute"] = minute
        cfg["enabled"] = bool(enabled)
        _save_config(cfg)
    register_job(scheduler)
    return cfg


def _run_fetch(trigger: str) -> dict:
    """Execute one BQ fetch + activate; persist outcome to last_run; return summary."""
    logger.info(f"[BaselineCron] fetch trigger={trigger}")
    result = fetch_from_bq()
    if result.success:
        result = apply_and_activate(result, source=f"bq_{trigger}")

    last_run = {
        "ts": datetime.now(TZ_TAIPEI).isoformat(timespec="seconds"),
        "trigger": trigger,
        "success": result.success,
        "precise_rows": result.precise_rows,
        "broad_rows": result.broad_rows,
        "warnings": list(result.warnings),
        "error": result.error,
    }
    with _lock:
        cfg = _load_config()
        cfg["last_run"] = last_run
        _save_config(cfg)
    return last_run


def run_now() -> dict:
    """Manual trigger from API / UI."""
    return _run_fetch(trigger="manual")


def _cron_callback():
    try:
        _run_fetch(trigger="cron")
    except Exception as e:
        logger.exception(f"[BaselineCron] uncaught exception in cron callback: {e}")


def register_job(scheduler) -> None:
    """(Re-)register the daily APScheduler job from current config."""
    cfg = get_config()
    # remove if exists
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if not cfg.get("enabled", True):
        logger.info(f"[BaselineCron] disabled in config — job not registered")
        return
    trigger = CronTrigger(hour=cfg["hour"], minute=cfg["minute"], timezone=TZ_TAIPEI)
    scheduler.add_job(
        _cron_callback,
        trigger=trigger,
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        f"[BaselineCron] registered daily fetch at {cfg['hour']:02d}:{cfg['minute']:02d} Asia/Taipei"
    )
