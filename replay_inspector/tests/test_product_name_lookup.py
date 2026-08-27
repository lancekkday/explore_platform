"""商品名稱查詢 (og:title 公開頁面) — TTL cache + single-flight 契約測試。
仿 backend/stage_product_check.py 的測試手法,mock requests.Session。
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.repo.product_name_lookup import (
    FALLBACK_LOCALES,
    LOCALE_URL,
    PRODUCT_HOSTS,
    ProductNameLookup,
)


def _resp(status_code=200, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    return r


OG_TITLE_HTML = '<html><head><meta property="og:title" content="福岡塔門票｜即買即用電子票"/></head></html>'


def test_extracts_name_from_og_title():
    lookup = ProductNameLookup(enabled=True)
    with patch.object(lookup._session, "get", return_value=_resp(200, OG_TITLE_HTML)):
        result = lookup.lookup_many(["131075"])
    assert result["131075"] == "福岡塔門票｜即買即用電子票"


def test_404_on_all_locales_returns_none():
    lookup = ProductNameLookup(enabled=True)
    with patch.object(lookup._session, "get", return_value=_resp(404, "")):
        result = lookup.lookup_many(["999999"])
    assert result["999999"] is None


def test_5xx_retries_then_none(monkeypatch):
    lookup = ProductNameLookup(enabled=True, retries=1, timeout=1)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_get(*a, **kw):
        calls["n"] += 1
        return _resp(500, "")

    with patch.object(lookup._session, "get", side_effect=fake_get):
        result = lookup.lookup_many(["555555"])
    assert result["555555"] is None
    # 每個 host:zh-tw(1 次原始 + 1 次重試)+ 5 個 fallback locale(各 retries=0)= 7,
    # 5xx 全部查詢失敗(非乾淨 404)→ 兩個 host 都會試過 = 14
    assert calls["n"] == len(PRODUCT_HOSTS) * (2 + len(FALLBACK_LOCALES))


def test_zh_tw_404_falls_back_to_other_locale():
    """實測案例:119751/164116 在 zh-tw 404,但 en-us/ja 有 og:title。"""
    lookup = ProductNameLookup(enabled=True)
    ja_name = "台湾 eSIM 4G無制限データ｜中華電信ローミング"
    ja_html = f'<html><head><meta property="og:title" content="{ja_name}"/></head></html>'

    def fake_get(url, **kw):
        if "/zh-tw/" in url or "/en-us/" in url:
            return _resp(404, "")
        if "/ja-jp/" in url:
            return _resp(200, ja_html)
        return _resp(404, "")

    with patch.object(lookup._session, "get", side_effect=fake_get):
        result = lookup.lookup_many(["119751"])
    assert result["119751"] == ja_name


def test_removed_everywhere_returns_none():
    lookup = ProductNameLookup(enabled=True)
    with patch.object(lookup._session, "get", return_value=_resp(404, "")) as mock_get:
        result = lookup.lookup_many(["000000"])
    assert result["000000"] is None
    # 1 (zh-tw) + len(FALLBACK_LOCALES) 次都試過才放棄
    assert mock_get.call_count == 1 + len(FALLBACK_LOCALES)


def test_no_og_title_meta_returns_none():
    lookup = ProductNameLookup(enabled=True)
    with patch.object(lookup._session, "get", return_value=_resp(200, "<html></html>")):
        result = lookup.lookup_many(["123"])
    assert result["123"] is None


def test_ttl_cache_avoids_second_http_call():
    lookup = ProductNameLookup(enabled=True, ttl_sec=600)
    mock_get = MagicMock(return_value=_resp(200, OG_TITLE_HTML))
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["131075"])
        lookup.lookup_many(["131075"])
    assert mock_get.call_count == 1


def test_disabled_returns_none_without_http_call():
    lookup = ProductNameLookup(enabled=False)
    mock_get = MagicMock(return_value=_resp(200, OG_TITLE_HTML))
    with patch.object(lookup._session, "get", mock_get):
        result = lookup.lookup_many(["131075"])
    assert result["131075"] is None
    mock_get.assert_not_called()


def test_dedups_duplicate_mids_in_one_call():
    lookup = ProductNameLookup(enabled=True)
    mock_get = MagicMock(return_value=_resp(200, OG_TITLE_HTML))
    with patch.object(lookup._session, "get", mock_get):
        result = lookup.lookup_many(["131075", "131075"])
    assert result == {"131075": "福岡塔門票｜即買即用電子票"}
    assert mock_get.call_count == 1


def test_single_flight_concurrent_calls_hit_http_once():
    lookup = ProductNameLookup(enabled=True)
    call_count = {"n": 0}
    lock = threading.Lock()

    def slow_get(*a, **kw):
        with lock:
            call_count["n"] += 1
        time.sleep(0.05)
        return _resp(200, OG_TITLE_HTML)

    results = []
    with patch.object(lookup._session, "get", side_effect=slow_get):
        threads = [
            threading.Thread(target=lambda: results.append(lookup.lookup_many(["131075"])))
            for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert call_count["n"] == 1
    assert all(r["131075"] == "福岡塔門票｜即買即用電子票" for r in results)


def test_builds_expected_url():
    url = LOCALE_URL.format(host=PRODUCT_HOSTS[0], locale="zh-tw", mid="131075")
    assert url == "https://www.kkday.com/zh-tw/product/131075"


# ── code review 補強:失敗 vs 確認查無,分開 TTL ────────────────────────────

def test_transient_failure_uses_short_ttl_and_is_retried_sooner(monkeypatch):
    """5xx 重試用盡是「查詢失敗」,不是「確認查無」,不該記滿 24h —
    只要過了短的 failure_ttl_sec 就該重新查。"""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(time, "time", lambda: fake_now["t"])
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    lookup = ProductNameLookup(
        enabled=True, ttl_sec=86400, failure_ttl_sec=10, retries=0, timeout=1,
    )
    mock_get = MagicMock(return_value=_resp(500, ""))
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["777777"])
    after_first = mock_get.call_count

    fake_now["t"] += 5  # 還沒過 failure_ttl_sec → 走 cache
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["777777"])
    assert mock_get.call_count == after_first

    fake_now["t"] += 10  # 過了 failure_ttl_sec → 重新查
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["777777"])
    assert mock_get.call_count > after_first


def test_confirmed_absent_uses_long_ttl_not_failure_ttl(monkeypatch):
    """全部 locale 都確定 404 (非查詢失敗) 要用長 TTL,過了 failure_ttl_sec
    也不該重查,否則跟查詢失敗的情境混在一起,失去分開快取的意義。"""
    fake_now = {"t": 1000.0}
    monkeypatch.setattr(time, "time", lambda: fake_now["t"])
    lookup = ProductNameLookup(enabled=True, ttl_sec=86400, failure_ttl_sec=10)
    mock_get = MagicMock(return_value=_resp(404, ""))
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["888888"])
    after_first = mock_get.call_count

    fake_now["t"] += 20  # 遠超過 failure_ttl_sec,但遠低於 ttl_sec
    with patch.object(lookup._session, "get", mock_get):
        lookup.lookup_many(["888888"])
    assert mock_get.call_count == after_first


# ── code review 補強:waiter 逾時要算進 fallback 鏈的最差時長 ───────────────
#
# 這裡刻意不重算 production 用的同一條算式再比對相等 —— 那種寫法只會驗證
# 「_waiter_timeout() 的實作沒被手滑改掉」,連 production 算式本身漏算最後
# 一次重試的 sleep(第一版就是這樣,兩邊都少 0.4*(retries+1)(retries+2)/2 - 0.4*retries
# 那一截,測試照樣通過)都抓不到。改成量測 _do_lookup 全部失敗時的「真實」
# 執行時間,直接驗證 waiter 逾時值真的蓋得住 owner 的最差耗時這個不變量。

def test_waiter_timeout_covers_measured_worst_case_do_lookup_duration():
    lookup = ProductNameLookup(timeout=0.05, retries=1)
    with patch.object(lookup._session, "get", return_value=_resp(500, "")):
        start = time.perf_counter()
        lookup._do_lookup("999999")
        elapsed = time.perf_counter() - start
    assert elapsed <= lookup._waiter_timeout()


def test_retry_worst_case_counts_sleep_after_final_attempt():
    """_fetch 對「最後一次」失敗嘗試也會 sleep 才 fall through 回傳 —
    worst-case 算式的 sleep 總和該是三角數,不是 0.4*retries(少算最後一次)。"""
    retries, timeout = 2, 1.0
    attempts = retries + 1
    expected_sleep = 0.4 * attempts * (attempts + 1) / 2  # 0.4+0.8+1.2 = 2.4
    assert ProductNameLookup._retry_worst_case(retries, timeout) == pytest.approx(
        timeout * attempts + expected_sleep
    )
    # 舊算式(0.4*retries = 0.8)會少算 1.6 秒 — 確保新算式沒有退化回去
    old_formula_value = timeout * attempts + 0.4 * retries
    assert ProductNameLookup._retry_worst_case(retries, timeout) > old_formula_value


# ── stage host fallback:prod 網路不通時才換 host,乾淨 404 不用換 ──────────

def test_falls_back_to_stage_host_when_prod_unreachable(monkeypatch):
    """prod host 全部 locale 都連線失敗(非 404)→ 換 stage host 試,
    stage 找到名字就用(前綴 `(Stage)` 標記來源,不是 prod 拿到的)—— 實測
    stage/prod 商品目錄同步,名稱一致。"""
    lookup = ProductNameLookup(enabled=True, retries=0, timeout=1)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    name = "台灣eSIM｜每日流量與總量流量套餐推薦"
    html = f'<html><head><meta property="og:title" content="{name}"/></head></html>'

    def fake_get(url, **kw):
        if "stage.kkday.com" in url:
            return _resp(200, html) if "/zh-tw/" in url else _resp(404, "")
        raise requests.ConnectionError("prod unreachable")

    with patch.object(lookup._session, "get", side_effect=fake_get):
        result = lookup.lookup_many(["162522"])
    assert result["162522"] == f"(Stage) {name}"


def test_prod_hit_is_not_tagged():
    lookup = ProductNameLookup(enabled=True)
    name = "福岡塔門票｜即買即用電子票"
    html = f'<html><head><meta property="og:title" content="{name}"/></head></html>'
    with patch.object(lookup._session, "get", return_value=_resp(200, html)):
        result = lookup.lookup_many(["131075"])
    assert result["131075"] == name  # 沒有 "(Stage)" 前綴


def test_confirmed_absent_on_prod_skips_stage_host():
    """prod 全部 locale 都是乾淨 404(非連線失敗)→ 已經是明確答案,
    不用浪費一次 stage host 的完整 locale 掃描。"""
    lookup = ProductNameLookup(enabled=True)
    stage_calls = {"n": 0}

    def fake_get(url, **kw):
        if "stage.kkday.com" in url:
            stage_calls["n"] += 1
        return _resp(404, "")

    with patch.object(lookup._session, "get", side_effect=fake_get):
        result = lookup.lookup_many(["000000"])
    assert result["000000"] is None
    assert stage_calls["n"] == 0


def test_product_hosts_prod_first_then_stage():
    assert PRODUCT_HOSTS[0] == "https://www.kkday.com"
    assert "stage" in PRODUCT_HOSTS[1]


def test_single_transient_blip_among_clean_404s_does_not_trigger_stage(monkeypatch):
    """re-review 抓到的 bug:prod host 6 次嘗試裡只要有 1 次 timeout/5xx,
    即使其餘 5 次都是乾淨 404(證明 host 明明連得上),舊邏輯仍會整輪重打
    stage —— 這正是 spec §9.6 第 3 點說的「避免浪費呼叫」要擋掉的情況。
    只有整個 host 完全連不上(6 次全部失敗)才該換 host。"""
    lookup = ProductNameLookup(enabled=True, retries=0, timeout=1)
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    stage_calls = {"n": 0}

    def fake_get(url, **kw):
        if "stage.kkday.com" in url:
            stage_calls["n"] += 1
            return _resp(404, "")
        if "/en-us/" in url:
            raise requests.ConnectionError("one-off blip")
        return _resp(404, "")  # zh-tw + 其他 4 個 fallback locale 都乾淨 404

    with patch.object(lookup._session, "get", side_effect=fake_get):
        result = lookup.lookup_many(["555000"])
    assert result["555000"] is None
    assert stage_calls["n"] == 0
