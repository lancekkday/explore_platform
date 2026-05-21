"""
Stage product existence checker (runtime,thread-safe,TTL cached)
=================================================================

提供給 baseline_service / ab_check 在巡檢時即時判斷某個 prod_mid 在 stage
是不是真的存在 (還是只是排到 300 名外抓不到):

    from stage_product_check import stage_checker
    stage_checker.check(mid)             # -> "exists" | "removed" | "check_failed"
    stage_checker.check_many([m1, m2])   # -> {m1: ..., m2: ...}

判斷規則 (HEAD 請求,不跟 redirect):
  - 200 / 301 / 302  → "exists"  (大多 stage 會 301 到帶 slug 的 URL,少數舊商品直接 200)
  - 404              → "removed"
  - 5xx / 429        → 重試,仍失敗 → "check_failed"
  - 其他狀態 / 連線錯誤 → "check_failed"

設計重點:
- Module-level singleton + threading.Lock,讓 ThreadPoolExecutor / FastAPI worker 共用
- TTL cache (預設 600s) — stage 商品狀態變動極慢,大幅降低重複請求
- 環境變數可關 (STAGE_CHECK_ENABLED=false) 做 fallback,關掉時 check() 一律回 "check_failed"
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

import requests

StageStatus = Literal["exists", "removed", "check_failed"]

STAGE_PRODUCT_URL = "https://www.stage.kkday.com/zh-tw/product/{mid}"

_EXISTS_HTTP = {200, 301, 302}
_REMOVED_HTTP = {404}

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
_DEFAULT_COOKIE = "i18n_redirected=zh-tw; country_lang=zh-tw; lang_ui=zh-tw; currency=TWD"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


class StageProductChecker:
    def __init__(
        self,
        ttl_sec: int = 600,
        timeout: float = 8.0,
        retries: int = 2,
        enabled: bool = True,
        user_agent: str = _DEFAULT_UA,
        cookie: str = _DEFAULT_COOKIE,
    ):
        self.ttl_sec = ttl_sec
        self.timeout = timeout
        self.retries = retries
        self.enabled = enabled
        self._cache: dict[int, tuple[StageStatus, float]] = {}
        # 同個 mid 同時被多個 thread 查時,只有 owner 實際發 HTTP,
        # 其他人等 owner 寫完 cache 再讀 (single-flight,避免 ab_check 工作池
        # 內多個 worker 重複打 stage 同一個下架商品)
        self._inflight: dict[int, threading.Event] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Cookie": cookie,
            "Accept-Language": "zh-TW,zh;q=0.9",
        })

    def _do_check(self, mid: int) -> StageStatus:
        url = STAGE_PRODUCT_URL.format(mid=mid)
        for attempt in range(self.retries + 1):
            try:
                resp = self._session.head(url, timeout=self.timeout, allow_redirects=False)
                code = resp.status_code
                if code in _EXISTS_HTTP:
                    return "exists"
                if code in _REMOVED_HTTP:
                    return "removed"
                if code >= 500 or code == 429:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                return "check_failed"
            except requests.RequestException:
                time.sleep(0.4 * (attempt + 1))
        return "check_failed"

    def _own_fetch(self, mid: int) -> StageStatus:
        """Owner side:跑 HTTP + 寫 cache + signal 等待中的 waiter。
        前置條件:呼叫者已經在 self._inflight[mid] 放了 Event,且 self.enabled=True
        (disabled 由 check_many 開頭 fast-path 處理,不會走到這裡)。"""
        status: StageStatus = "check_failed"
        try:
            status = self._do_check(mid)
        finally:
            with self._lock:
                self._cache[mid] = (status, time.time())
                event = self._inflight.pop(mid, None)
            if event is not None:
                event.set()
        return status

    def check(self, mid: Optional[int]) -> StageStatus:
        if mid is None:
            return "check_failed"
        # 直接走 check_many,共用 TTL + single-flight 邏輯
        return self.check_many([int(mid)])[int(mid)]

    def check_many(
        self,
        mids: list[int],
        workers: int = 8,
    ) -> dict[int, StageStatus]:
        if not mids:
            return {}
        clean_mids = [int(m) for m in dict.fromkeys(mids) if m is not None]
        # Disabled fast-path:全部標 check_failed,跳過 cache/inflight bookkeeping
        if not self.enabled:
            return {m: "check_failed" for m in clean_mids}

        results: dict[int, StageStatus] = {}
        to_fetch: list[int] = []                                # we own
        to_wait: list[tuple[int, threading.Event]] = []         # someone else owns

        now = time.time()
        with self._lock:
            for m in clean_mids:
                cached = self._cache.get(m)
                if cached and now - cached[1] < self.ttl_sec:
                    results[m] = cached[0]
                    continue
                event = self._inflight.get(m)
                if event is not None:
                    to_wait.append((m, event))
                else:
                    self._inflight[m] = threading.Event()
                    to_fetch.append(m)

        # Fetch our owned mids (並行;只 1 個就不開 pool 省 overhead)
        if to_fetch:
            if len(to_fetch) == 1:
                results[to_fetch[0]] = self._own_fetch(to_fetch[0])
            else:
                with ThreadPoolExecutor(max_workers=min(workers, len(to_fetch))) as pool:
                    for mid, status in zip(to_fetch, pool.map(self._own_fetch, to_fetch)):
                        results[mid] = status

        # Wait for in-flight mids owned by other callers (bounded timeout 防卡死)
        if to_wait:
            bounded_timeout = self.timeout * (self.retries + 1) + 5.0
            for m, ev in to_wait:
                ev.wait(timeout=bounded_timeout)
                with self._lock:
                    cached = self._cache.get(m)
                results[m] = cached[0] if cached else "check_failed"

        return results

    def cache_size(self) -> int:
        with self._lock:
            return len(self._cache)

    def invalidate(self, mid: Optional[int] = None) -> None:
        with self._lock:
            if mid is None:
                self._cache.clear()
            else:
                self._cache.pop(int(mid), None)


def _make_default_checker() -> StageProductChecker:
    return StageProductChecker(
        ttl_sec=int(os.environ.get("STAGE_CHECK_TTL_SEC", "600")),
        timeout=float(os.environ.get("STAGE_CHECK_TIMEOUT", "8")),
        retries=int(os.environ.get("STAGE_CHECK_RETRIES", "2")),
        enabled=_env_bool("STAGE_CHECK_ENABLED", True),
    )


stage_checker = _make_default_checker()
