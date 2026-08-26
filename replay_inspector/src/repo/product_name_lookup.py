"""商品名稱查詢 (runtime,thread-safe,TTL cached)
=================================================================

spec §9.6:`stream_search_record_flat.prods` 沒有 prod_name 欄位。這裡用
`www.kkday.com` 商品頁公開的 `og:title` meta tag 補這個缺口 —— 不需要登入、
不需要 API key,商品名稱幾乎不變動,用長 TTL cache 大幅降低重複請求。

設計仿 backend/stage_product_check.py:module-level singleton + TTL cache +
single-flight,讓 FastAPI 多個 request 共用,同一個 mid 不會被同時查兩次。

    from src.repo.product_name_lookup import product_name_lookup
    product_name_lookup.lookup_many(["131075", "205881"])
    # -> {"131075": "福岡塔門票|即買即用電子票", "205881": "..."}
"""
from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

PRODUCT_URL = "https://www.kkday.com/zh-tw/product/{mid}"
FALLBACK_LOCALE_URL = "https://www.kkday.com/{locale}/product/{mid}"
# 404 在 zh-tw 常常不是「商品下架」,是「這個商品沒有 zh-tw 語言版本」
# (實測:119751/164116 在 zh-tw/zh-cn/zh-hk 404,但 en-us/ja/ko 都存在且有名稱)。
# zh-tw 失敗後依序試這些 locale,拿到名字就算數,比顯示裸 mid 有用。
FALLBACK_LOCALES = ["en-us", "ja-jp", "ko-kr", "zh-cn", "zh-hk"]

_OG_TITLE_RE = re.compile(
    r'property="og:title"\s+content="([^"]*)"', re.IGNORECASE
)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _extract_og_title(html: str) -> Optional[str]:
    m = _OG_TITLE_RE.search(html)
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


class ProductNameLookup:
    def __init__(
        self,
        ttl_sec: int = 86400,
        timeout: float = 6.0,
        retries: int = 1,
        enabled: bool = True,
        user_agent: str = _DEFAULT_UA,
    ):
        self.ttl_sec = ttl_sec
        self.timeout = timeout
        self.retries = retries
        self.enabled = enabled
        self._cache: dict[str, tuple[Optional[str], float]] = {}
        # single-flight:同個 mid 同時被多個 request 查時,只有 owner 實際發
        # HTTP,其他人等 owner 寫完 cache 再讀 (避免多個回放 session 同時展開
        # 同一批熱門商品時重複打 kkday.com)
        self._inflight: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept-Language": "zh-TW,zh;q=0.9",
        })

    def _fetch(self, url: str, retries: int, timeout: float) -> Optional[str]:
        for attempt in range(retries + 1):
            try:
                resp = self._session.get(url, timeout=timeout, allow_redirects=True)
                if resp.status_code == 404:
                    return None
                if resp.status_code >= 500 or resp.status_code == 429:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    return None
                return _extract_og_title(resp.text)
            except requests.RequestException:
                time.sleep(0.4 * (attempt + 1))
        return None

    def _do_lookup(self, mid: str) -> Optional[str]:
        name = self._fetch(PRODUCT_URL.format(mid=mid), self.retries, self.timeout)
        if name:
            return name
        # zh-tw 沒有 → 依序試其他 locale (不重試,timeout 縮短,壓住全下架商品的最差延遲)
        for locale in FALLBACK_LOCALES:
            name = self._fetch(
                FALLBACK_LOCALE_URL.format(locale=locale, mid=mid),
                retries=0, timeout=min(self.timeout, 4.0),
            )
            if name:
                return name
        return None

    def _own_fetch(self, mid: str) -> Optional[str]:
        name: Optional[str] = None
        try:
            name = self._do_lookup(mid)
        finally:
            with self._lock:
                self._cache[mid] = (name, time.time())
                event = self._inflight.pop(mid, None)
            if event is not None:
                event.set()
        return name

    def lookup_many(self, mids: list[str], workers: int = 8) -> dict[str, Optional[str]]:
        clean_mids = [str(m) for m in dict.fromkeys(mids) if m is not None]
        if not clean_mids:
            return {}
        if not self.enabled:
            return {m: None for m in clean_mids}

        results: dict[str, Optional[str]] = {}
        to_fetch: list[str] = []
        to_wait: list[tuple[str, threading.Event]] = []

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

        if to_fetch:
            if len(to_fetch) == 1:
                results[to_fetch[0]] = self._own_fetch(to_fetch[0])
            else:
                with ThreadPoolExecutor(max_workers=min(workers, len(to_fetch))) as pool:
                    for mid, name in zip(to_fetch, pool.map(self._own_fetch, to_fetch)):
                        results[mid] = name

        if to_wait:
            bounded_timeout = self.timeout * (self.retries + 1) + 5.0
            for m, ev in to_wait:
                ev.wait(timeout=bounded_timeout)
                with self._lock:
                    cached = self._cache.get(m)
                results[m] = cached[0] if cached else None

        return results

    def invalidate(self, mid: Optional[str] = None) -> None:
        with self._lock:
            if mid is None:
                self._cache.clear()
            else:
                self._cache.pop(str(mid), None)


def _make_default_lookup() -> ProductNameLookup:
    return ProductNameLookup(
        ttl_sec=int(os.environ.get("PRODUCT_NAME_LOOKUP_TTL_SEC", "86400")),
        timeout=float(os.environ.get("PRODUCT_NAME_LOOKUP_TIMEOUT", "6")),
        retries=int(os.environ.get("PRODUCT_NAME_LOOKUP_RETRIES", "1")),
        enabled=_env_bool("PRODUCT_NAME_LOOKUP_ENABLED", True),
    )


product_name_lookup = _make_default_lookup()
