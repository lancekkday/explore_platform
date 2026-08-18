"""FakeEventRepo — 測試與 demo 用的記憶體資料。

內建「福岡」treatment vs control fixture (spec 驗收 3),分數刻意做成
float32 同分帶情境 (spec 驗收 4),BQ 表未就緒時 UI 以 USE_FAKE=1 直接可看。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from .bigquery import LIST_COLUMNS

DEMO_DATE = "2026-08-13"
_EVENT_TS = datetime(2026, 8, 13, 7, 17, 10, tzinfo=timezone.utc)  # 台灣 15:17

_BASE = 110.99571
_ULP = float(np.spacing(np.float32(_BASE)))


def _scores(gaps_ulp: list[int]) -> list[float]:
    asc = [_BASE]
    for g in gaps_ulp:
        asc.append(asc[-1] + g * _ULP)
    return list(reversed(asc))


# 分數以升冪累加 gap 再 reverse 成降冪 — 要讓「前 6 名」緊貼成同分帶,
# 8 ULP 的小 gap 必須放在升冪序列的「尾端」(reverse 後才會落在頂部)。
# treatment (exp_a):前 6 名同帶,7-10 各差 200 ULP 拉開
_A_SCORES = _scores([200, 200, 200, 200, 8, 8, 8, 8, 8])
# control (exp_b):同一批商品,前段順序在帶內互換 + 兩顆不同商品
_B_SCORES = _scores([200, 200, 200, 200, 8, 8, 8, 8, 8])

_A_MIDS = ["248950", "131075", "205881", "142267", "198432",
           "173064", "155520", "162238", "144906", "188751"]
# control:帶內互換前兩名、尾端換成不同商品 (only_a / only_b 證據)
_B_MIDS = ["131075", "248950", "205881", "142267", "198432",
           "173064", "155520", "162238", "907001", "907002"]

_CODES = {
    "248950": "000220", "131075": "000200", "205881": "000000",
    "142267": "000220", "198432": "000020", "173064": "000200",
    "155520": "000000", "162238": "000220", "144906": "000200",
    "188751": "000000", "907001": "000020", "907002": "000200",
}


def _prods(mids: list[str], scores: list[float], session_id: str) -> list[dict]:
    out = []
    for i, (mid, score) in enumerate(zip(mids, scores)):
        rank = i + 1
        out.append({
            "session_id": session_id,
            "rank": rank,
            "prod_mid": mid,
            "prod_oid": mid,
            "is_ad": (rank == 3),
            "ltr_score": score if rank <= 100 else None,
            "relevance_status_code": _CODES.get(mid, "000000"),
            "in_rerank_scope": rank <= 100,
        })
    return out


_EVENTS: dict[str, dict[str, Any]] = {
    "sess-fukuoka-treatment": {
        "session_id": "sess-fukuoka-treatment",
        "event_date": _EVENT_TS,
        "event_type": "content",
        "cache_hit": False,
        "source_event_id": "recall-001",
        "keyword": "福岡",
        "normalized_keyword": "福岡",
        "lang": "zh-tw", "locale": "tw", "currency": "TWD",
        "exp_version": "exp_a",
        "source": "web",
        "kkud": "kkud-demo-001",
        "member_uuid": "member-demo-001",   # 登入會員 (PII;僅衍生 logged_in 出去)
        "ip_masked": "61.216.159.0/24",
        "filter_json": "{}",
        "page_start": 0, "page_count": 10, "total_count": 867, "prod_cnt": 10,
        "uf_intent": json.dumps({"dest_pref": {"d": "fukuoka", "v": 0.82, "t": 1}}),
        "uf_profile": json.dumps({"member_tier": {"d": "gold", "v": 1, "t": 1}}),
        "uf_profile_version": "v3",
        "uf_lbs": None,
        "cf_platform": "web",
        "cf_hour": 15, "cf_weekday": 3,
        "cf_query_final": "福岡",
        "cf_query_tokens": ["福岡"],
        "ltr_features_recovered": False,
        "join_failed": False,
        "uf_absent": False,
    },
    "sess-fukuoka-control": {
        "session_id": "sess-fukuoka-control",
        "event_date": _EVENT_TS,
        "event_type": "content.cache",
        "cache_hit": True,
        "source_event_id": "recall-002",
        "keyword": "福岡",
        "normalized_keyword": "福岡",
        "lang": "zh-tw", "locale": "tw", "currency": "TWD",
        "exp_version": "exp_b",
        "source": "web",
        "kkud": "kkud-demo-002",
        "ip_masked": "61.216.159.0/24",
        "filter_json": "{}",
        "page_start": 0, "page_count": 10, "total_count": 867, "prod_cnt": 10,
        "uf_intent": None,
        "uf_profile": None,
        "uf_profile_version": None,
        "uf_lbs": None,
        "cf_platform": "web",
        "cf_hour": 15, "cf_weekday": 3,
        "cf_query_final": "福岡",
        "cf_query_tokens": ["福岡"],
        "ltr_features_recovered": True,
        "join_failed": False,
        "uf_absent": True,
    },
    # join 失敗示例 (驗收 6:uf/cf 置灰)
    "sess-join-failed": {
        "session_id": "sess-join-failed",
        "event_date": _EVENT_TS,
        "event_type": "content",
        "cache_hit": False,
        "source_event_id": "recall-missing",
        "keyword": "東京",
        "normalized_keyword": None,
        "lang": "zh-tw", "locale": "tw", "currency": "TWD",
        "exp_version": "exp_a",
        "source": "app",
        "kkud": "kkud-demo-003",
        "ip_masked": "203.69.113.0/24",
        "filter_json": "{}",
        "page_start": 0, "page_count": 10, "total_count": 120, "prod_cnt": 10,
        "uf_intent": None, "uf_profile": None, "uf_profile_version": None, "uf_lbs": None,
        "cf_platform": None, "cf_hour": None, "cf_weekday": None,
        "cf_query_final": None, "cf_query_tokens": None,
        "ltr_features_recovered": False,
        "join_failed": True,
        "uf_absent": False,
    },
}

_CF_RAW = {
    "sess-fukuoka-treatment": json.dumps(
        {"platform": "web", "hour": 15, "weekday": 3,
         "query": {"final": "福岡", "tokens": ["福岡"]},
         "note": "demo cf_raw — 實際單筆約 138 KB"}
    ),
    "sess-fukuoka-control": json.dumps({"platform": "web", "hour": 15, "weekday": 3}),
}

_PRODS = {
    ("福岡", "exp_a"): _prods(_A_MIDS, _A_SCORES, "sess-fukuoka-treatment"),
    ("福岡", "exp_b"): _prods(_B_MIDS, _B_SCORES, "sess-fukuoka-control"),
}

class FakeEventRepo:
    """記憶體 repo。query_count 讓測試斷言「400 時查詢不得送出」(驗收 2)。

    列表回應共用 bigquery.LIST_COLUMNS 白名單 (單一來源,避免 cf_raw 防線
    在兩份清單間 drift) + 衍生欄 logged_in。
    """

    def __init__(self) -> None:
        self.query_count = 0

    def list_events(self, date: str, filters: dict[str, Any]) -> list[dict]:
        self.query_count += 1
        rows = []
        for ev in _EVENTS.values():
            if all(
                filters.get(k) is None or ev.get(k) == filters[k]
                for k in ("keyword", "kkud", "member_uuid", "session_id",
                          "exp_version", "locale", "lang", "currency", "cache_hit")
            ):
                row = {k: ev.get(k) for k in LIST_COLUMNS}
                row["logged_in"] = ev.get("member_uuid") is not None
                rows.append(row)
        return rows

    def get_event(self, session_id: str, date: str,
                  keyword: Optional[str] = None, exp_version: Optional[str] = None,
                  locale: Optional[str] = None) -> Optional[dict]:
        # cluster hint 在 fake 裡不影響結果 (session_id 已唯一),照收以對齊 Protocol
        self.query_count += 1
        ev = _EVENTS.get(session_id)
        return dict(ev) if ev else None

    def get_cf_raw(self, session_id: str, date: str,
                   keyword: Optional[str] = None, exp_version: Optional[str] = None,
                   locale: Optional[str] = None) -> Optional[str]:
        self.query_count += 1
        return _CF_RAW.get(session_id)

    def get_prods(self, date: str, keyword: str, locale: Optional[str],
                  exp_version: str, session_id: Optional[str] = None) -> list[dict]:
        self.query_count += 1
        prods = _PRODS.get((keyword, exp_version), [])
        if session_id:
            prods = [p for p in prods if p["session_id"] == session_id]
        return [dict(p) for p in prods]
