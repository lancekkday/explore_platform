"""
Baseline Service
================

Loads precise/broad baseline CSVs at startup and provides:
- keyword lookup (precise / broad / both)
- product annotation (tag baseline products in search results)
- missing baseline product detection
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

from loguru import logger

# ── 設定 ──────────────────────────────────────────────────────────────────────
# 「排名下降」閾值倍數：current_rank > expected_rank * N 視為 dropped
BASELINE_DROP_MULTIPLIER = int(os.environ.get("BASELINE_DROP_MULTIPLIER", "3"))

# ── CSV paths (same as ab_check.py) ─────────────────────────────────────────
# Support both local (backend/../handoff/data) and Docker (/app/handoff/data)
_app_dir = Path(__file__).resolve().parent
HANDOFF_DATA = next(
    (p for p in [_app_dir.parent / "handoff" / "data", _app_dir / "handoff" / "data"] if p.is_dir()),
    _app_dir.parent / "handoff" / "data",  # fallback
)
PRECISE_CSV = HANDOFF_DATA / "search_keyword_precise.csv"
BROAD_CSV = HANDOFF_DATA / "search_keyword_broad.csv"


def _safe_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _safe_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


class BaselineService:
    def __init__(self):
        self._precise: dict[str, dict] = {}      # query -> row dict
        self._broad: dict[str, list[dict]] = {}   # query -> [row dicts sorted by profit_rank]
        self._load()

    def _load(self):
        # Load precise CSV (case-insensitive: keys stored as lowercase)
        if PRECISE_CSV.exists():
            with open(PRECISE_CSV, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    q = row.get("query", "").strip()
                    if not q:
                        continue
                    self._precise[q.lower()] = {
                        "query": q,
                        "is_destination": row.get("is_destination", "").strip().lower() == "true",
                        "search_pv": _safe_int(row.get("search_pv")),
                        "top1_prod_nm": row.get("top1_prod_nm", ""),
                        "top1_prod_mid": _safe_int(row.get("top1_prod_mid")),
                        "top1_profit": _safe_float(row.get("top1_profit")),
                        "top1_ctr": _safe_float(row.get("top1_ctr")),
                        "top2_prod_nm": row.get("top2_prod_nm", ""),
                        "top2_prod_mid": _safe_int(row.get("top2_prod_mid")),
                        "top2_profit": _safe_float(row.get("top2_profit")),
                        "top2_ctr": _safe_float(row.get("top2_ctr")),
                    }
            logger.info(f"[Baseline] Loaded {len(self._precise)} precise keywords from {PRECISE_CSV}")
        else:
            logger.warning(f"[Baseline] Precise CSV not found: {PRECISE_CSV}")

        # Load broad CSV
        if BROAD_CSV.exists():
            with open(BROAD_CSV, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    q = row.get("query", "").strip()
                    if not q:
                        continue
                    entry = {
                        "prod_nm": row.get("prod_nm", ""),
                        "prod_mid": _safe_int(row.get("prod_mid")),
                        "profit": _safe_float(row.get("profit")),
                        "ctr": _safe_float(row.get("ctr")),
                        "profit_rank": _safe_int(row.get("profit_rank")),
                    }
                    self._broad.setdefault(q.lower(), []).append(entry)
            # Sort each group by profit_rank
            for q in self._broad:
                self._broad[q].sort(key=lambda x: x.get("profit_rank") or 999)
            n_queries = len(self._broad)
            n_rows = sum(len(v) for v in self._broad.values())
            logger.info(f"[Baseline] Loaded {n_rows} broad rows ({n_queries} keywords) from {BROAD_CSV}")
        else:
            logger.warning(f"[Baseline] Broad CSV not found: {BROAD_CSV}")

    def reload(self):
        """Clear and reload CSVs. Called after baseline upload."""
        self._precise.clear()
        self._broad.clear()
        self._load()
        logger.info(f"[Baseline] Reloaded: {len(self._precise)} precise, {len(self._broad)} broad keywords")

    # ── Lookup ───────────────────────────────────────────────────────────────

    def get_baseline(self, keyword: str) -> dict:
        """Return baseline data for a keyword."""
        kw = keyword.strip().lower()
        has_precise = kw in self._precise
        has_broad = kw in self._broad

        if has_precise and has_broad:
            kw_type = "both"
        elif has_precise:
            kw_type = "precise"
        elif has_broad:
            kw_type = "broad"
        else:
            kw_type = "none"

        return {
            "has_data": has_precise or has_broad,
            "keyword_type": kw_type,
            "precise": self._precise.get(kw),
            "broad_products": self._broad.get(kw, []),
        }

    def get_all_keywords(self) -> list[str]:
        """Return all keywords that have baseline data."""
        return sorted(set(self._precise.keys()) | set(self._broad.keys()))

    # ── Annotation ───────────────────────────────────────────────────────────

    def annotate_products(self, keyword: str, products: list[dict]) -> list[dict]:
        """Add baseline_tag, baseline_profit, baseline_profit_rank to each product."""
        kw = keyword.strip().lower()
        precise = self._precise.get(kw)
        broad_list = self._broad.get(kw, [])

        # Build lookup: prod_mid -> baseline info
        baseline_map: dict[int, dict] = {}
        if precise:
            for rank_n, prefix in [(1, "top1"), (2, "top2")]:
                mid = precise.get(f"{prefix}_prod_mid")
                if mid is not None:
                    baseline_map[mid] = {
                        "baseline_tag": f"precise_top{rank_n}",
                        "baseline_profit": precise.get(f"{prefix}_profit"),
                        "baseline_ctr": precise.get(f"{prefix}_ctr"),
                        "baseline_profit_rank": None,
                    }
        for entry in broad_list:
            mid = entry.get("prod_mid")
            if mid is not None:
                if mid in baseline_map:
                    # Already tagged as precise, add broad info
                    baseline_map[mid]["baseline_profit_rank"] = entry.get("profit_rank")
                    if baseline_map[mid]["baseline_profit"] is None:
                        baseline_map[mid]["baseline_profit"] = entry.get("profit")
                else:
                    baseline_map[mid] = {
                        "baseline_tag": f"broad_rank_{entry.get('profit_rank', '?')}",
                        "baseline_profit": entry.get("profit"),
                        "baseline_ctr": entry.get("ctr"),
                        "baseline_profit_rank": entry.get("profit_rank"),
                    }

        # Annotate each product
        for p in products:
            pid = p.get("prod_mid") or p.get("id")
            if pid is not None:
                pid = _safe_int(pid)
            info = baseline_map.get(pid) if pid else None
            if info:
                p["baseline_tag"] = info["baseline_tag"]
                p["baseline_profit"] = info["baseline_profit"]
                p["baseline_ctr"] = info["baseline_ctr"]
                p["baseline_profit_rank"] = info["baseline_profit_rank"]
            else:
                p["baseline_tag"] = None
                p["baseline_profit"] = None
                p["baseline_ctr"] = None
                p["baseline_profit_rank"] = None

        return products

    def find_baseline_alerts(self, keyword: str, products: list[dict]) -> list[dict]:
        """Check which baseline products are missing or dropped in the results."""
        kw = keyword.strip().lower()
        precise = self._precise.get(kw)
        broad_list = self._broad.get(kw, [])

        # Collect all baseline products we expect
        expected: list[dict] = []
        if precise:
            for rank_n, prefix in [(1, "top1"), (2, "top2")]:
                mid = precise.get(f"{prefix}_prod_mid")
                if mid is not None:
                    expected.append({
                        "prod_mid": mid,
                        "prod_nm": precise.get(f"{prefix}_prod_nm", ""),
                        "baseline_tag": f"precise_top{rank_n}",
                        "expected_rank": rank_n,
                    })
        for entry in broad_list:
            mid = entry.get("prod_mid")
            if mid is not None:
                # Don't duplicate if already in precise
                if not any(e["prod_mid"] == mid for e in expected):
                    expected.append({
                        "prod_mid": mid,
                        "prod_nm": entry.get("prod_nm", ""),
                        "baseline_tag": f"broad_rank_{entry.get('profit_rank', '?')}",
                        "expected_rank": entry.get("profit_rank"),
                    })

        # Build result mid -> rank lookup
        result_ranks: dict[int, int] = {}
        for p in products:
            pid = _safe_int(p.get("prod_mid") or p.get("id"))
            rank = p.get("rank")
            if pid and rank:
                result_ranks[pid] = rank

        alerts = []
        for e in expected:
            mid = e["prod_mid"]
            current_rank = result_ranks.get(mid)
            if current_rank is None:
                status = "missing"
            elif e["expected_rank"] and current_rank > e["expected_rank"] * BASELINE_DROP_MULTIPLIER:
                status = "dropped"
            else:
                status = "present"
            alerts.append({
                "prod_mid": mid,
                "prod_nm": e["prod_nm"],
                "baseline_tag": e["baseline_tag"],
                "status": status,
                "current_rank": current_rank,
                "expected_rank": e["expected_rank"],
            })

        return alerts


# Module-level singleton
baseline_service = BaselineService()
