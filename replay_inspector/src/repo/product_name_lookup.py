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

Code review 補強 (2026-08-26):
- 「查無此商品」(全部 locale 都確定 404 / 無 og:title) 跟「查詢失敗」
  (timeout / 5xx / 429 重試用盡) 分開快取,失敗用短 TTL (預設 5 分鐘),
  避免一次線上暫時性故障被記成「沒名字」記滿 24 小時。
- single-flight waiter 逾時值算入 fallback locale 鏈的最差總時長,避免
  owner 還在跑 fallback 時,等待中的 caller 提早拿到 None。

Stage host fallback (2026-08-26):部署主機若只放行 stage、沒開對外網路,
`www.kkday.com` 整個 host 都連不上(不是 404,是連線失敗)—— 這種情況換打
`www.stage.kkday.com`。實測同一個 mid 在 prod/stage 的 og:title 一致
(商品目錄同步),名稱前綴 `(Stage) ` 標記來源,方便日後目錄不同步時排查。
只在 prod host 查詢失敗時才換 host;乾淨 404 已是明確答案,不用多打一輪。
"""
from __future__ import annotations

import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

LOCALE_URL = "{host}/{locale}/product/{mid}"
# prod 打不通(部署主機防火牆只放行 stage,沒開對外網路)時換 stage 商品頁 —
# 實測同一個 mid 在 prod/stage 的 og:title 內容一致(商品目錄同步),不是猜測。
# 只在 prod 那個 host「查詢失敗」(非乾淨 404)時才換,乾淨 404 已經是明確
# 答案,不用多花一輪 stage 的完整 locale 掃描。
PRODUCT_HOSTS = ["https://www.kkday.com", "https://www.stage.kkday.com"]
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
        failure_ttl_sec: int = 300,
        timeout: float = 6.0,
        retries: int = 1,
        enabled: bool = True,
        user_agent: str = _DEFAULT_UA,
    ):
        self.ttl_sec = ttl_sec
        self.failure_ttl_sec = failure_ttl_sec
        self.timeout = timeout
        self.retries = retries
        self.enabled = enabled
        # value: (name_or_None, cached_at, confirmed) — confirmed=False 代表
        #「查詢失敗,不代表商品真的沒有這個名稱」,只能用短 TTL
        self._cache: dict[str, tuple[Optional[str], float, bool]] = {}
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

    def _fetch(self, url: str, retries: int, timeout: float) -> tuple[Optional[str], bool]:
        """回傳 (name, confirmed)。confirmed=True 代表拿到明確答案(有名字 /
        確定 404 / 200 但無 og:title),confirmed=False 代表查詢失敗,不能
        代表商品真的沒有這個名稱(重試用盡的 5xx/429/連線錯誤/非預期狀態碼)。"""
        for attempt in range(retries + 1):
            try:
                resp = self._session.get(url, timeout=timeout, allow_redirects=True)
                if resp.status_code == 404:
                    return None, True
                if resp.status_code >= 500 or resp.status_code == 429:
                    time.sleep(0.4 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    return None, False
                return _extract_og_title(resp.text), True
            except requests.RequestException:
                time.sleep(0.4 * (attempt + 1))
        return None, False

    @staticmethod
    def _tag_host(name: str, host_idx: int) -> str:
        # host_idx 0 = prod(不標記);非 0 = fallback host(目前只有 stage),
        # 標出來提醒使用者這筆名稱不是從 prod 拿到的,萬一哪天目錄不同步好排查。
        return name if host_idx == 0 else f"(Stage) {name}"

    def _do_lookup(self, mid: str) -> tuple[Optional[str], bool]:
        for host_idx, host in enumerate(PRODUCT_HOSTS):
            name, confirmed = self._fetch(
                LOCALE_URL.format(host=host, locale="zh-tw", mid=mid),
                self.retries, self.timeout,
            )
            if name:
                return self._tag_host(name, host_idx), True
            any_confirmed = confirmed
            # zh-tw 沒有 → 依序試其他 locale (不重試,timeout 縮短,壓住全下架商品的最差延遲)
            for locale in FALLBACK_LOCALES:
                name, confirmed = self._fetch(
                    LOCALE_URL.format(host=host, locale=locale, mid=mid),
                    retries=0, timeout=min(self.timeout, 4.0),
                )
                if name:
                    return self._tag_host(name, host_idx), True
                any_confirmed = any_confirmed or confirmed
            if any_confirmed:
                # 這個 host 至少有一次拿到明確答案(有名字或乾淨 404),代表
                # host 本身連得通 —— 沒找到名字就是真的沒有,不用為了單一次
                # 孤立的逾時/5xx 就整輪重打下一個 host(那樣才是浪費呼叫)。
                return None, True
            # 這個 host 6 次(zh-tw + 5 fallback locale)全部查詢失敗,一次明確
            # 答案都沒拿到 → 判定整個 host 連不上,換下一個 host 試。
        return None, False

    def _own_fetch(self, mid: str) -> Optional[str]:
        name: Optional[str] = None
        confirmed = False
        try:
            name, confirmed = self._do_lookup(mid)
        finally:
            with self._lock:
                self._cache[mid] = (name, time.time(), confirmed)
                event = self._inflight.pop(mid, None)
            if event is not None:
                event.set()
        return name

    @staticmethod
    def _retry_worst_case(retries: int, timeout: float) -> float:
        """_fetch 的單一 URL 最差耗時:retries+1 次嘗試,每次最多 timeout 秒,
        且每次失敗(含最後一次)都還會 `time.sleep(0.4*(attempt+1))` 才回傳
        (見 _fetch 的 for 迴圈 — 最後一次也會 sleep 才 fall through)。
        sleep 總和是三角數 0.4 * attempts*(attempts+1)/2,不是 0.4*retries
        (少算最後一次;之前的版本就是漏了這裡,兩位數 retries 時誤差會二次方放大)。"""
        attempts = retries + 1
        total_sleep = 0.4 * attempts * (attempts + 1) / 2
        return timeout * attempts + total_sleep

    def _waiter_timeout(self) -> float:
        # 跟 owner 實際最差耗時對齊:單一 host 是 zh-tw 那一輪 + 全部 fallback
        # locale(各 1 次,不重試)的最差時長;owner 最差情況是兩個 host 都
        # 查詢失敗、整輪都跑完(prod 網路不通才會走到 stage,見 _do_lookup)。
        primary_worst = self._retry_worst_case(self.retries, self.timeout)
        fallback_timeout = min(self.timeout, 4.0)
        fallback_worst = len(FALLBACK_LOCALES) * self._retry_worst_case(0, fallback_timeout)
        per_host_worst = primary_worst + fallback_worst
        return len(PRODUCT_HOSTS) * per_host_worst + 5.0

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
                if cached:
                    name, cached_at, confirmed = cached
                    ttl = self.ttl_sec if confirmed else self.failure_ttl_sec
                    if now - cached_at < ttl:
                        results[m] = name
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
            bounded_timeout = self._waiter_timeout()
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
        failure_ttl_sec=int(os.environ.get("PRODUCT_NAME_LOOKUP_FAILURE_TTL_SEC", "300")),
        timeout=float(os.environ.get("PRODUCT_NAME_LOOKUP_TIMEOUT", "6")),
        retries=int(os.environ.get("PRODUCT_NAME_LOOKUP_RETRIES", "1")),
        enabled=_env_bool("PRODUCT_NAME_LOOKUP_ENABLED", True),
    )


product_name_lookup = _make_default_lookup()
