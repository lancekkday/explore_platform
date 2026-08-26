"""商品名稱查詢 (og:title 公開頁面) — TTL cache + single-flight 契約測試。
仿 backend/stage_product_check.py 的測試手法,mock requests.Session。
"""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.repo.product_name_lookup import FALLBACK_LOCALES, PRODUCT_URL, ProductNameLookup


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
    # zh-tw:1 次原始 + 1 次重試,再 5 個 fallback locale (各 retries=0) = 7
    assert calls["n"] == 2 + len(FALLBACK_LOCALES)


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
    assert PRODUCT_URL.format(mid="131075") == "https://www.kkday.com/zh-tw/product/131075"
