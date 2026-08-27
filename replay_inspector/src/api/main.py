"""FastAPI 服務層 — spec §5。所有端點唯讀。

規則 (spec 5.1):
- `date` 必填且在建查詢前就檢查,缺 → 400、查詢不得送出 (驗收 2)
- PII (member_uuid / user_id / ip) 不得進 URL query string
  → GET /api/events 不收 member_uuid;要用 member_uuid 過濾走 POST /api/events/search
- 回應一律不含 cf_raw,除 5.4 單筆端點
"""
from __future__ import annotations

import json
from datetime import timedelta, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from src.domain.compare import merge_rows, personalization_strength, strength_warning
from src.domain.relevance import decode_relevance
from src.domain.tie_band import assign_tie_bands, dispersion_stats
from src.repo.bigquery import (
    RERANK_BOUNDARY,
    UF_COVERAGE_BASELINE,
    ClusterKeyRequired,
    EventRepo,
    MissingPartitionDate,
    QueryTooExpensive,
    get_repo,
    local_date_to_utc_range,
    mask_ip_to_24,
)
from src.repo.product_name_lookup import ProductNameLookup, product_name_lookup

TZ_TAIPEI = timezone(timedelta(hours=8))

app = FastAPI(title="Search Personalization Replay Inspector", version="1.0")

# PII 欄位絕不允許出現在 query string (spec 5.1)
_FORBIDDEN_QS_KEYS = {"member_uuid", "user_id", "ip", "ip_masked"}


def _reject_pii_in_query_string(request: Request) -> None:
    hit = _FORBIDDEN_QS_KEYS & set(request.query_params.keys())
    if hit:
        raise HTTPException(
            status_code=400,
            detail=f"PII field(s) {sorted(hit)} must not appear in URL query string; "
                   f"use POST /api/events/search with a JSON body",
        )


def _require_date(date: Optional[str]) -> str:
    """先驗 date 再做任何事 — 缺分區條件的查詢一律不得送出 (驗收 2)。"""
    if not date:
        raise HTTPException(status_code=400, detail="date (YYYY-MM-DD, UTC+8) is required")
    try:
        local_date_to_utc_range(date)
    except MissingPartitionDate as e:
        raise HTTPException(status_code=400, detail=str(e))
    return date


def _to_local_iso(ts) -> Optional[str]:
    if ts is None:
        return None
    return ts.astimezone(TZ_TAIPEI).isoformat()


def _listed(row: dict) -> dict:
    out = dict(row)
    ts = out.pop("event_date", None)
    out["event_date_local"] = _to_local_iso(ts)
    return out


def get_product_name_lookup() -> ProductNameLookup:
    return product_name_lookup


def _enrich_prod_names(prods: list[dict], lookup: ProductNameLookup) -> list[dict]:
    """spec §9.6:flat 表 payload 沒有商品名稱 — 缺的用 og:title 公開頁面補,
    已有名稱(如 demo fixture)的不重查,避免不必要的 HTTP 呼叫。"""
    needs_name = [not p.get("prod_name") for p in prods]
    if not any(needs_name):
        return prods
    missing_mids = [p["prod_mid"] for p, need in zip(prods, needs_name) if need and p.get("prod_mid")]
    names = lookup.lookup_many(missing_mids)
    return [
        {**p, "prod_name": names.get(p.get("prod_mid"))} if need else p
        for p, need in zip(prods, needs_name)
    ]


# ── 5.2 GET /api/events(非 PII 過濾)──────────────────────────────────────────

@app.get("/api/events")
def list_events(
    request: Request,
    date: Optional[str] = None,
    keyword: Optional[str] = None,
    kkud: Optional[str] = None,
    session_id: Optional[str] = None,
    exp_version: Optional[str] = None,
    locale: Optional[str] = None,
    lang: Optional[str] = None,
    currency: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    repo: EventRepo = Depends(get_repo),
):
    _reject_pii_in_query_string(request)
    date = _require_date(date)
    filters = {
        "keyword": keyword, "kkud": kkud, "session_id": session_id,
        "exp_version": exp_version, "locale": locale, "lang": lang,
        "currency": currency, "cache_hit": cache_hit, "member_uuid": None,
    }
    if not filters.get("keyword") and not filters.get("kkud"):
        raise HTTPException(
            status_code=400,
            detail="keyword 或 kkud 至少一項必填 (flat 表叢集鍵,缺了會掃全天分區;"
                   "member_uuid 過濾走 POST /api/events/search 且仍需搭配 keyword/kkud)",
        )
    try:
        rows = [_listed(r) for r in repo.list_events(date, filters)]
        return {"rows": rows, "bytes_billed": repo.last_query_bytes()}
    except ClusterKeyRequired as e:
        raise HTTPException(status_code=400, detail=str(e))
    except QueryTooExpensive as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 5.2' POST /api/events/search(含 member_uuid 的過濾走 body)────────────────

class EventSearchBody(BaseModel):
    date: str
    keyword: Optional[str] = None
    kkud: Optional[str] = None
    member_uuid: Optional[str] = None
    session_id: Optional[str] = None
    exp_version: Optional[str] = None
    locale: Optional[str] = None
    lang: Optional[str] = None
    currency: Optional[str] = None
    cache_hit: Optional[bool] = None


@app.post("/api/events/search")
def search_events(body: EventSearchBody, repo: EventRepo = Depends(get_repo)):
    date = _require_date(body.date)
    filters = body.model_dump(exclude={"date"})
    if not filters.get("keyword") and not filters.get("kkud"):
        raise HTTPException(
            status_code=400,
            detail="keyword 或 kkud 至少一項必填 (flat 表叢集鍵,缺了會掃全天分區);"
                   "member_uuid / session_id 可作為附加過濾",
        )
    try:
        rows = [_listed(r) for r in repo.list_events(date, filters)]
        return {"rows": rows, "bytes_billed": repo.last_query_bytes()}
    except ClusterKeyRequired as e:
        raise HTTPException(status_code=400, detail=str(e))
    except QueryTooExpensive as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 5.3 GET /api/events/{session_id} 單筆明細 ─────────────────────────────────

@app.get("/api/events/{session_id}")
def event_detail(
    session_id: str,
    request: Request,
    date: Optional[str] = None,
    # cluster hint (keyword/exp_version/locale 是表的叢集鍵):點查不帶會繞過
    # cluster pruning 掃整個分區窗 — 前端從列表 row 帶入
    keyword: Optional[str] = None,
    exp_version: Optional[str] = None,
    locale: Optional[str] = None,
    repo: EventRepo = Depends(get_repo),
    name_lookup: ProductNameLookup = Depends(get_product_name_lookup),
):
    _reject_pii_in_query_string(request)
    date = _require_date(date)
    try:
        ev = repo.get_event(session_id, date, keyword=keyword,
                            exp_version=exp_version, locale=locale)
    except QueryTooExpensive as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ev:
        raise HTTPException(status_code=404, detail=f"session_id not found: {session_id}")
    bytes_billed = repo.last_query_bytes()

    # 商品列已併在 get_event() 裡一起抽(2026-08-27 省成本:同一個 event_id
    # 鎖定的是同一列資料,不用再開一支查詢重掃一次,見 bigquery.py 註解)
    prods = _enrich_prod_names(ev.get("prods") or [], name_lookup)
    scores = [p.get("ltr_score") for p in prods]
    bands = assign_tie_bands(scores)
    prod_rows = [
        {
            "rank": p["rank"],
            "prod_mid": p["prod_mid"],
            "prod_oid": p.get("prod_oid"),
            "prod_name": p.get("prod_name"),
            "is_ad": bool(p.get("is_ad")),
            "ltr_score": p.get("ltr_score"),
            "tie_band": band,
            "relevance": decode_relevance(p.get("relevance_status_code")),
            "relevance_status_code": p.get("relevance_status_code"),
            "in_rerank_scope": bool(p.get("in_rerank_scope")),
        }
        for p, band in zip(prods, bands)
    ]

    def _json_or_none(v):
        if v is None:
            return None
        try:
            return json.loads(v) if isinstance(v, str) else v
        except (ValueError, TypeError):
            return None

    return {
        "session_id": ev["session_id"],
        "bytes_billed": bytes_billed,   # 這次查詢 (content+recall+prods) 累積計費位元組數
        "event_date_local": _to_local_iso(ev.get("event_date")),
        "event_type": ev.get("event_type"),
        "cache_hit": ev.get("cache_hit"),
        "keyword": ev.get("keyword"),
        "normalized_keyword": ev.get("normalized_keyword"),
        "lang": ev.get("lang"), "locale": ev.get("locale"), "currency": ev.get("currency"),
        "exp_version": ev.get("exp_version"),
        "source": ev.get("source"),
        "kkud": ev.get("kkud"),
        "ip_masked": mask_ip_to_24(ev.get("ip_masked")),
        "pagination": {
            "page_start": ev.get("page_start"),
            "page_count": ev.get("page_count"),
            "total_count": ev.get("total_count"),
            "prod_cnt": ev.get("prod_cnt"),
            "rerank_boundary": RERANK_BOUNDARY,
        },
        # 4.5:先回答「這筆資料能不能信」
        "quality_flags": {
            "join_failed": bool(ev.get("join_failed")),
            "uf_absent": bool(ev.get("uf_absent")),
            "ltr_features_recovered": bool(ev.get("ltr_features_recovered")),
        },
        "uf": {
            "intent": _json_or_none(ev.get("uf_intent")),
            "profile": _json_or_none(ev.get("uf_profile")),
            "profile_version": ev.get("uf_profile_version"),
            "lbs": _json_or_none(ev.get("uf_lbs")),
        },
        "cf_summary": {
            "platform": ev.get("cf_platform"),
            "hour": ev.get("cf_hour"),
            "weekday": ev.get("cf_weekday"),
            "query_final": ev.get("cf_query_final"),
            "query_tokens": ev.get("cf_query_tokens"),
        },
        "coverage_baseline": UF_COVERAGE_BASELINE,
        "dispersion": dispersion_stats(scores),
        "prods": prod_rows,
    }


# ── 5.4 GET /api/events/{session_id}/cf 完整 cf_raw ───────────────────────────

@app.get("/api/events/{session_id}/cf")
def event_cf(
    session_id: str,
    request: Request,
    date: Optional[str] = None,
    keyword: Optional[str] = None,
    exp_version: Optional[str] = None,
    locale: Optional[str] = None,
    repo: EventRepo = Depends(get_repo),
):
    _reject_pii_in_query_string(request)
    date = _require_date(date)
    try:
        cf = repo.get_cf_raw(session_id, date, keyword=keyword,
                             exp_version=exp_version, locale=locale)
    except QueryTooExpensive as e:
        raise HTTPException(status_code=400, detail=str(e))
    if cf is None:
        raise HTTPException(status_code=404, detail="cf not found")
    return {"session_id": session_id, "cf_raw": cf, "bytes_billed": repo.last_query_bytes()}


# ── 5.5 GET /api/compare ──────────────────────────────────────────────────────

@app.get("/api/compare")
def compare(
    request: Request,
    date: Optional[str] = None,
    keyword: Optional[str] = None,
    locale: Optional[str] = None,
    exp_a: Optional[str] = None,   # treatment
    exp_b: Optional[str] = None,   # control
    cache_hit: Optional[bool] = None,
    repo: EventRepo = Depends(get_repo),
    name_lookup: ProductNameLookup = Depends(get_product_name_lookup),
):
    _reject_pii_in_query_string(request)
    date = _require_date(date)
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword is required")

    cost = [0]   # 累積這次 /api/compare 打了幾次 repo、共花多少計費位元組數

    def _tracked_list_events(filters: dict) -> list[dict]:
        rows = repo.list_events(date, filters)
        cost[0] += repo.last_query_bytes()
        return rows

    try:
        # exp_a/exp_b 可省略 — 自動從當日該 keyword 的事件偵測兩個實驗組
        # (RD:個性化實驗階段 control 組就是非個性化 baseline 組)。升冪排序取前二,
        # 對齊 ui-spec §4 範例「A treatment 100000 ↔ B control 100001」的編號慣例;
        # 顯式帶入仍可覆寫。
        if not exp_a or not exp_b:
            seen: list[str] = []
            for ev in _tracked_list_events({"keyword": keyword, "locale": locale,
                                            "cache_hit": cache_hit}):
                v = ev.get("exp_version")
                if v and v not in seen:
                    seen.append(v)
            seen.sort()
            if len(seen) < 2:
                raise HTTPException(
                    status_code=404,
                    detail="找不到兩個實驗組事件,無法對照 — 可放寬 locale / cache_hit,"
                           "或以 exp_a/exp_b 明確指定",
                )
            exp_a, exp_b = seen[0], seen[1]

        def _latest_session(exp: str) -> Optional[dict]:
            # 同天同 keyword+exp 可能有多個 session — 各側取最新一個事件,
            # 不鎖 session 的話多個事件的 rank 會混在同一張排序表 (spec 3.2 FK)。
            # cache_hit 必須跟著帶:使用者明選 cache_hit=false 要看 live 排序時,
            # 不帶會抓到 cache 事件,比對對象錯置。
            events = _tracked_list_events({
                "keyword": keyword, "exp_version": exp, "locale": locale,
                "cache_hit": cache_hit,
            })
            return events[0] if events else None

        def _side(exp: str) -> tuple[list[dict], Optional[dict]]:
            ev = _latest_session(exp)
            if not ev:
                return [], None
            prods = repo.get_prods(date, keyword, locale, exp,
                                   session_id=ev["session_id"])
            cost[0] += repo.last_query_bytes()
            prods = _enrich_prod_names(prods, name_lookup)
            detail = repo.get_event(ev["session_id"], date, keyword=keyword,
                                    exp_version=exp, locale=ev.get("locale"))
            cost[0] += repo.last_query_bytes()
            # 表格內每列要能呈現來源側的 exp / lang / locale / cf (事件層級 metadata)
            meta = {
                "exp_version": exp,
                "session_id": ev["session_id"],
                "lang": (detail or {}).get("lang"),
                "locale": (detail or {}).get("locale") or ev.get("locale"),
                "currency": (detail or {}).get("currency"),
                "cf": {
                    "platform": (detail or {}).get("cf_platform"),
                    "hour": (detail or {}).get("cf_hour"),
                    "weekday": (detail or {}).get("cf_weekday"),
                },
            }
            return prods, meta

        a_prods, a_meta = _side(exp_a)
        b_prods, b_meta = _side(exp_b)
    except QueryTooExpensive as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not a_prods and not b_prods:
        raise HTTPException(status_code=404, detail="no prods for either experiment")

    rows = merge_rows(a_prods, b_prods)

    a_top = [p["prod_mid"] for p in sorted(a_prods, key=lambda p: p["rank"])]
    b_top = [p["prod_mid"] for p in sorted(b_prods, key=lambda p: p["rank"])]
    strength = personalization_strength(a_top, b_top)
    top10_overlap = len(set(a_top[:10]) & set(b_top[:10]))

    rank_changes = sum(
        1 for r in rows
        if r["rank_a"] is not None and r["rank_b"] is not None and r["rank_a"] != r["rank_b"]
    )
    tie_unresolvable = sum(1 for r in rows if r["verdict"] == "tie_unresolvable")
    # ui-spec §5 讀數列第三格「跨帶變動」= real_move 計數。rank_changes 含同帶內
    # 位移(總量),跨帶才是可歸因於演算法的變動 — 兩者都回,UI 用 real_move。
    real_move = sum(1 for r in rows if r["verdict"] == "real_move")

    return {
        "meta": {"keyword": keyword, "locale": locale, "exp_a": exp_a, "exp_b": exp_b,
                 "a": a_meta, "b": b_meta},
        "metrics": {
            "personalization_strength": round(strength, 4),
            "top10_overlap": top10_overlap,
            "rank_changes": rank_changes,
            "real_move_changes": real_move,
            "tie_unresolvable_changes": tie_unresolvable,
            "warning": strength_warning(strength),
        },
        "dispersion_a": dispersion_stats([p.get("ltr_score") for p in a_prods]),
        "dispersion_b": dispersion_stats([p.get("ltr_score") for p in b_prods]),
        "rows": rows,
        "bytes_billed": cost[0],
    }
