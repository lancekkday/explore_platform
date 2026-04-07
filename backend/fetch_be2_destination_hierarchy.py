#!/usr/bin/env python3
"""
從 BE2 (stage) svc-geo 遞迴抓取完整 Destination 階層資料。

API（與你在瀏覽器看到的相同）:
  GET https://api-gateway.stage.kkday.com/svc-geo/api/admin/destinations/hierarchy-with-groups
  Query:
    - lang=zh-tw
    - parentDestinationCode=   (空字串 = tier1 根節點)
    - parentDestinationCode=D-TW-225  (子層)

安全：請勿把 Bearer token 寫進程式或 commit。
  export KKDAY_BE2_BEARER_TOKEN='你的 token'
  或 export KKDAY_BE2_BEARER_TOKEN_FILE='/path/to/secret_file'（檔案內一行 token；全量抓取時腳本會每次請求前重讀，可中途換新 JWT）

Token 流程（與瀏覽器一致，建議長跑必讀）:
  1) 先準備**有效** access JWT → 寫入 KKDAY_BE2_BEARER_TOKEN_FILE（或 --token / KKDAY_BE2_BEARER_TOKEN）。
  2) **第一支 refresh** 仍須從瀏覽器複製一次：DevTools 裡  
     PATCH .../api/v1/refresh-token/<refreshJWT> **路徑上的 refresh JWT** → KKDAY_BE2_REFRESH_TOKEN_FILE。  
     （無法只靠 access「憑空」向 auth 要 refresh；refresh API 需要 URL 上的 refresh + Header 上的 access。）
  3) 之後腳本可選在**程式一開始**先打 refresh（預設開啟，若有設 refresh）換新 access 再撈 geo；並**輪替寫回**新 access／新 refresh。  
     geo 每請求前若 access 剩餘 ≤ KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC（預設 120，0＝關閉）會**主動** refresh；401/403 也會再試。  
     關閉啟動 refresh：`--no-refresh-at-start` 或 `KKDAY_BE2_REFRESH_AT_START=0`。

  若 refresh 仍失敗，可選設 KKDAY_BE2_AUTH_COOKIE（與瀏覽器相同 Cookie 字串）。
  refresh PATCH 會帶與 geo 相同的 kkday-forwarded-id／x-auth-id（預設 BE2-DESTINATIONS／be2）；
  若仍 AU9997，可試與瀏覽器對齊：KKDAY_BE2_AUTH_FORWARDED_ID、KKDAY_BE2_AUTH_X_AUTH_ID。

選用 header（與 curl 對齊）:
  KKDAY_BE2_FORWARDED_ID   預設 BE2-DESTINATIONS
  KKDAY_BE2_X_AUTH_ID      預設 be2
  KKDAY_BE2_USER_AGENT     預設 Chrome/macOS 風格（可被 WAF 檢查）
  KKDAY_BE2_ACCEPT_LANGUAGE 預設 zh-TW,...（設為空字串可關閉）

輸出:
  - 預設根目錄固定為腳本同層的 be2_destinations_dump/<UTC時間戳>/（可用 --output-dir 覆寫）
  - 未指定 -o 時預設寫 bundle：meta.json + destinations.jsonl + destinations.sqlite
  - --by-country：在該次 run 目錄下依 isoCountryCode 分子資料夾；根目錄有 crawl_progress.json 記錄各國 pending/in_progress/complete
  - --resume 請固定同一 --output-dir
  - --parallel-iso N：by-country 時最多 N 國並行（每國獨立 Session；國內仍節流）。N>1 可能觸發 gateway 限流，請保守
  - -o 與 --by-country 不可併用

  每筆欄位: code, name, isoCountryCode, tier, status, hasHierarchy, languages
  - 額外附 parentCode（根層為 null）；若不要可加 --no-parent-code

節流（預設較保守，避免影響服務）:
  - 每次 API 成功後等待 delay + random(0, jitter) 秒
  - 預設 delay=1.0、jitter=0.5；可用 --delay / --jitter 或 KKDAY_BE2_REQUEST_DELAY、KKDAY_BE2_REQUEST_JITTER

日誌（loguru）:
  - --log-level / 環境變數 KKDAY_BE2_LOG_LEVEL（預設 INFO）
  - --log-file / KKDAY_BE2_LOG_FILE（選用，可 rotation）
  - --progress-interval：每隔幾次成功請求打一筆 INFO 進度（預設 20）；DEBUG 會記錄每次請求與節流秒數
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sqlite3
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from loguru import logger

DEFAULT_BASE = (
    "https://api-gateway.stage.kkday.com/svc-geo/api/admin/destinations/hierarchy-with-groups"
)

# 預設節流：避免短時間大量打 API 影響服務；可用環境變數或 CLI 覆寫。
DEFAULT_REQUEST_DELAY = 1.0  # 每次請求後至少間隔（秒）
DEFAULT_REQUEST_JITTER = 0.5  # 額外隨機 0～jitter 秒，打散同時請求

# 預設匯出根：backend/data/be2_destinations_dump/<時間戳>/
DEFAULT_DUMP_DIRNAME = os.path.join("data", "be2_destinations_dump")


def _script_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__)) or "."


def default_run_output_dir() -> str:
    """每次執行一個子資料夾，避免覆蓋；與 --resume 併用時請自行指定固定 --output-dir。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(_script_base_dir(), DEFAULT_DUMP_DIRNAME, ts)


def _configure_loguru(level: str, log_file: Optional[str]) -> None:
    """stderr 彩色日誌；選用檔案（自動 rotation，不寫入 token 內文）。"""
    logger.remove()
    lvl = (level or "INFO").strip().upper()
    fmt_console = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )
    logger.add(sys.stderr, level=lvl, format=fmt_console, colorize=True)
    if log_file:
        fmt_file = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}\n"
        )
        logger.add(
            log_file,
            level=lvl,
            format=fmt_file,
            encoding="utf-8",
            rotation="50 MB",
            retention=5,
            enqueue=True,
        )
        logger.info("日誌檔：{}", os.path.abspath(log_file))


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_only_iso_csv(raw: Optional[str]) -> Optional[Set[str]]:
    """'TW, JP' → {'TW','JP'}；空則 None（表示不篩選）。"""
    if raw is None or str(raw).strip() == "":
        return None
    return {x.strip().upper() for x in str(raw).split(",") if x.strip()}


def _sleep_between_requests(delay_sec: float, jitter_sec: float) -> None:
    """每次 API 成功回來後暫停，降低對 gateway / svc-geo 的壓力。"""
    base = max(0.0, delay_sec)
    extra = random.uniform(0.0, max(0.0, jitter_sec)) if jitter_sec > 0 else 0.0
    wait = base + extra
    if wait > 0:
        logger.debug(
            "節流 sleep {:.3f}s（delay={:.3f}, jitter_max={:.3f}）",
            wait,
            base,
            jitter_sec,
        )
        time.sleep(wait)


def _refresh_session_bearer_from_token_file(session: requests.Session) -> None:
    """
    若設定了 KKDAY_BE2_BEARER_TOKEN_FILE，每次請求前重新讀檔更新 Authorization。
    全量階層抓取耗時常超過 JWT 有效時間（約 5 分鐘），可在腳本執行中覆寫檔案換新 token。
    """
    path = (os.environ.get("KKDAY_BE2_BEARER_TOKEN_FILE") or "").strip()
    if not path or not os.path.isfile(path):
        return
    try:
        raw = open(path, "r", encoding="utf-8").read().strip()
    except OSError:
        return
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if raw:
        session.headers["authorization"] = f"Bearer {raw}"
        logger.debug("已自 token 檔更新 Authorization：{}（token 長度 {}）", path, len(raw))


# 並行時避免多條 thread 同時打 refresh
_token_refresh_lock = threading.Lock()


def _bearer_value_from_session(session: requests.Session) -> Optional[str]:
    h = session.headers.get("Authorization") or session.headers.get("authorization")
    if not h:
        return None
    h = str(h).strip()
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return h or None


def _read_bearer_from_token_file_only() -> Optional[str]:
    path = (os.environ.get("KKDAY_BE2_BEARER_TOKEN_FILE") or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        raw = open(path, "r", encoding="utf-8").read().strip()
    except OSError:
        return None
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    return raw or None


def _load_refresh_token() -> Optional[str]:
    t = (os.environ.get("KKDAY_BE2_REFRESH_TOKEN") or "").strip()
    if t:
        return t
    p = (os.environ.get("KKDAY_BE2_REFRESH_TOKEN_FILE") or "").strip()
    if p and os.path.isfile(p):
        try:
            return open(p, "r", encoding="utf-8").read().strip()
        except OSError:
            return None
    return None


def _persist_bearer_access_token(access: str) -> None:
    path = (os.environ.get("KKDAY_BE2_BEARER_TOKEN_FILE") or "").strip()
    if not path:
        return
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(access.strip() + "\n")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("寫入 KKDAY_BE2_BEARER_TOKEN_FILE 失敗：{}", e)


def _persist_refresh_token_if_configured(refresh: str) -> None:
    p = (os.environ.get("KKDAY_BE2_REFRESH_TOKEN_FILE") or "").strip()
    if not p:
        return
    try:
        tmp = f"{p}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(refresh.strip() + "\n")
        os.replace(tmp, p)
        logger.info("已更新 KKDAY_BE2_REFRESH_TOKEN_FILE（輪替 refresh JWT）")
    except OSError as e:
        logger.warning("寫入 KKDAY_BE2_REFRESH_TOKEN_FILE 失敗：{}", e)


def _collect_jwt_like_strings_for_keys(
    obj: Any,
    key_names: Tuple[str, ...],
    out: List[str],
    *,
    depth: int = 0,
    max_depth: int = 8,
) -> None:
    """遞迴收集 dict 裡指定鍵名的字串值（因應 data / tokens / result 等巢狀）。"""
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in key_names and isinstance(v, str) and len(v.strip()) > 20:
                out.append(v.strip())
            _collect_jwt_like_strings_for_keys(
                v, key_names, out, depth=depth + 1, max_depth=max_depth
            )
    elif isinstance(obj, list):
        for item in obj:
            _collect_jwt_like_strings_for_keys(
                item, key_names, out, depth=depth + 1, max_depth=max_depth
            )


def _extract_access_token_from_auth_response(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    candidates: List[Any] = []
    data = body.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("access_token"),
                data.get("accessToken"),
                data.get("token"),
            ]
        )
        inner = data.get("data")
        if isinstance(inner, dict):
            candidates.extend(
                [
                    inner.get("access_token"),
                    inner.get("accessToken"),
                    inner.get("token"),
                ]
            )
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            candidates.extend(
                [
                    tokens.get("access_token"),
                    tokens.get("accessToken"),
                    tokens.get("token"),
                ]
            )
    candidates.extend(
        [
            body.get("access_token"),
            body.get("accessToken"),
            body.get("token"),
        ]
    )
    for c in candidates:
        if isinstance(c, str) and len(c) > 30:
            return c.strip()
    walked: List[str] = []
    _collect_jwt_like_strings_for_keys(
        body,
        ("accessToken", "access_token", "token"),
        walked,
    )
    for s in walked:
        if len(s) > 30 and s.count(".") == 2:
            return s
    return None


def _extract_refresh_token_from_auth_response(body: Any) -> Optional[str]:
    """解析 refresh API 回應中的 refreshToken（camelCase）或 refresh_token。"""
    if not isinstance(body, dict):
        return None
    candidates: List[Any] = []
    data = body.get("data")
    if isinstance(data, dict):
        candidates.extend(
            [
                data.get("refresh_token"),
                data.get("refreshToken"),
            ]
        )
        inner = data.get("data")
        if isinstance(inner, dict):
            candidates.extend(
                [
                    inner.get("refresh_token"),
                    inner.get("refreshToken"),
                ]
            )
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            candidates.extend(
                [
                    tokens.get("refresh_token"),
                    tokens.get("refreshToken"),
                ]
            )
    candidates.extend([body.get("refresh_token"), body.get("refreshToken")])
    for c in candidates:
        if isinstance(c, str) and len(c) > 30:
            return c.strip()
    walked: List[str] = []
    _collect_jwt_like_strings_for_keys(
        body,
        ("refreshToken", "refresh_token"),
        walked,
    )
    for s in walked:
        if len(s) > 30:
            return s
    return None


def try_refresh_be2_access_token(session: requests.Session, timeout: float) -> bool:
    """
    PATCH auth.stage /api/v1/refresh-token/{refreshJWT}
    Header: Authorization: Bearer {accessJWT}（可用檔案內最新 access）
    """
    refresh_jwt = _load_refresh_token()
    if not refresh_jwt:
        return False
    bearer = _read_bearer_from_token_file_only() or _bearer_value_from_session(session)
    if not bearer:
        return False

    auth_base = (os.environ.get("KKDAY_BE2_AUTH_BASE") or "https://auth.stage.kkday.com").rstrip(
        "/"
    )
    url = f"{auth_base}/api/v1/refresh-token/{refresh_jwt}"
    ua = (
        session.headers.get("User-Agent")
        or session.headers.get("user-agent")
        or "Mozilla/5.0 (compatible; fetch_be2_destination_hierarchy/1.0)"
    )
    # auth.stage refresh 與瀏覽器／gateway 一致：需帶 BE2 識別，否則可能 AU9997 Service key is invalid
    forwarded = (
        os.environ.get("KKDAY_BE2_AUTH_FORWARDED_ID")
        or os.environ.get("KKDAY_BE2_FORWARDED_ID")
        or "BE2-DESTINATIONS"
    ).strip()
    x_auth = (
        os.environ.get("KKDAY_BE2_AUTH_X_AUTH_ID")
        or os.environ.get("KKDAY_BE2_X_AUTH_ID")
        or "be2"
    ).strip()
    hdrs: Dict[str, str] = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {bearer}",
        "kkday-forwarded-id": forwarded,
        "origin": "https://be2.stage.kkday.com",
        "referer": "https://be2.stage.kkday.com/",
        "user-agent": ua,
        "x-auth-id": x_auth,
        "request-uuid": str(uuid.uuid4()),
    }
    accept_language = (os.environ.get("KKDAY_BE2_ACCEPT_LANGUAGE") or "").strip()
    if accept_language:
        hdrs["accept-language"] = accept_language
    cookie = (os.environ.get("KKDAY_BE2_AUTH_COOKIE") or "").strip()
    if cookie:
        hdrs["Cookie"] = cookie

    try:
        pr = requests.patch(url, headers=hdrs, timeout=timeout)
    except requests.RequestException as e:
        logger.warning("refresh-token 連線失敗：{}", e)
        return False

    if not pr.ok:
        logger.warning(
            "refresh-token HTTP {}：{}",
            pr.status_code,
            (pr.text or "")[:400],
        )
        return False
    try:
        body = pr.json()
    except json.JSONDecodeError:
        logger.warning("refresh-token 回應非 JSON")
        return False

    new_access = _extract_access_token_from_auth_response(body)
    if not new_access:
        logger.warning(
            "refresh-token 回應找不到 access token，頂層 keys={}",
            list(body.keys()) if isinstance(body, dict) else type(body),
        )
        return False

    session.headers["authorization"] = f"Bearer {new_access}"
    _persist_bearer_access_token(new_access)
    new_refresh = _extract_refresh_token_from_auth_response(body)
    if new_refresh:
        _persist_refresh_token_if_configured(new_refresh)
        logger.info("回應含 refreshToken，已嘗試寫入 KKDAY_BE2_REFRESH_TOKEN_FILE（若有設定）")
    logger.success("已透過 auth refresh-token 換新 access（長度 {}）", len(new_access))
    return True


def _jwt_payload_exp_unix(access_jwt: str) -> Optional[float]:
    """解出 JWT payload 的 exp（unix 秒）；失敗則 None（不驗簽，僅供本地過期判斷）。"""
    parts = access_jwt.strip().split(".")
    if len(parts) < 2:
        return None
    b64 = parts[1]
    pad = (-len(b64)) % 4
    if pad:
        b64 += "=" * pad
    try:
        raw = base64.urlsafe_b64decode(b64.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    exp = payload.get("exp")
    if exp is None:
        return None
    try:
        return float(exp)
    except (TypeError, ValueError):
        return None


def _access_expiring_soon(access_jwt: str, buffer_sec: float) -> bool:
    """True 表示依 JWT exp 判斷將在 buffer_sec 內過期（含已過期）。"""
    if buffer_sec <= 0:
        return False
    exp = _jwt_payload_exp_unix(access_jwt)
    if exp is None:
        return False
    return (exp - time.time()) <= buffer_sec


def maybe_proactive_refresh_be2_access(session: requests.Session, timeout: float) -> None:
    """
    每次 geo 請求前：若已設定 refresh，且 access JWT 的 exp 將在緩衝秒數內到達，則先 PATCH refresh。
    緩衝秒數：KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC（預設 120；≤0 關閉）。
    """
    buf = _env_float("KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC", 120.0)
    if buf <= 0:
        return
    if not _load_refresh_token():
        return
    with _token_refresh_lock:
        _refresh_session_bearer_from_token_file(session)
        acc = _read_bearer_from_token_file_only() or _bearer_value_from_session(session)
        if not acc or not _access_expiring_soon(acc, buf):
            return
        exp = _jwt_payload_exp_unix(acc)
        secs_left = (exp - time.time()) if exp is not None else float("nan")
        if try_refresh_be2_access_token(session, timeout):
            logger.info(
                "access JWT 約 {:.0f}s 內過期（<= buffer {}s），已主動 refresh",
                secs_left,
                int(buf),
            )
    _refresh_session_bearer_from_token_file(session)


def _log_loaded_refresh_token_exp_hint() -> None:
    """
    若目前載入的 refresh 為標準 JWT 且含 exp，打 INFO／WARNING 協助推測效期（例如是否約 24h）。
    不驗簽；若後端實際效期與 JWT exp 不一致，以實際 API 為準。
    """
    r = _load_refresh_token()
    if not r:
        return
    exp = _jwt_payload_exp_unix(r)
    if exp is None:
        logger.info(
            "refresh token：無法從 JWT payload 解出 exp（可能非三段式 JWT、或 payload 無 exp）"
        )
        return
    left = exp - time.time()
    if left <= 0:
        logger.warning(
            "refresh JWT（payload exp）已過期（約 {:.0f}s 前）；啟動時 refresh 很可能失敗，請從瀏覽器更新 refresh 檔",
            -left,
        )
    else:
        logger.info(
            "refresh JWT（僅解 payload exp，未驗簽）：約 {:.2f} 小時 / {:.0f} 分鐘後過期",
            left / 3600.0,
            left / 60.0,
        )


def _refresh_at_program_start_enabled(cli_no_refresh_at_start: bool) -> bool:
    """預設啟動時先 refresh（若有 refresh 設定）；CLI 與環境變數可關閉。"""
    if cli_no_refresh_at_start:
        return False
    raw = (os.environ.get("KKDAY_BE2_REFRESH_AT_START") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def maybe_refresh_tokens_at_program_start(
    session: requests.Session,
    timeout: float,
    *,
    enabled: bool,
) -> None:
    """
    進任何 geo 請求前：若 enabled 且已設定 refresh，先 PATCH refresh-token 換新 access（與可選的新 refresh）。
    仍需事先具備 refresh JWT（瀏覽器或上次寫入之檔案）；無法在零 refresh 下「開機取得第一支 refresh」。
    """
    if not enabled:
        return
    if not _load_refresh_token():
        return
    _log_loaded_refresh_token_exp_hint()
    with _token_refresh_lock:
        _refresh_session_bearer_from_token_file(session)
        ok = try_refresh_be2_access_token(session, timeout)
    _refresh_session_bearer_from_token_file(session)
    if ok:
        logger.success("啟動時 refresh-token 成功，已換新 access（接著撈 geo 使用新 JWT）")
    else:
        logger.warning(
            "啟動時 refresh-token 失敗，沿用啟動時的 access；執行中遇 401/403 或 access 將過期仍會再試 refresh"
        )


def _extract_destinations_list(body: Any) -> List[Dict[str, Any]]:
    """從 API JSON 取出 destinations 陣列（容錯多種包裝）。"""
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if isinstance(data, dict):
        dest = data.get("destinations")
        if isinstance(dest, list):
            return [x for x in dest if isinstance(x, dict)]
        # 有些 API 可能直接 data 為 list
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    dest = body.get("destinations")
    if isinstance(dest, list):
        return [x for x in dest if isinstance(x, dict)]
    return []


def _normalize_item(
    raw: Dict[str, Any],
    parent_code: Optional[str],
    include_parent_code: bool,
) -> Dict[str, Any]:
    """對齊你預期的結構；缺欄位則補合理預設。"""
    code = raw.get("code") or raw.get("destinationCode") or raw.get("id")
    name = raw.get("name") or raw.get("destinationName") or ""
    tier = raw.get("tier")
    if tier is None:
        tier = raw.get("tierLevel")
    try:
        tier = int(tier) if tier is not None else None
    except (TypeError, ValueError):
        tier = None
    status = raw.get("status") or "UNKNOWN"
    has_h = raw.get("hasHierarchy")
    if has_h is None:
        has_h = raw.get("hasChildren") or raw.get("hasChild")
    if isinstance(has_h, str):
        has_h = has_h.lower() in ("true", "1", "yes")
    if has_h is None:
        has_h = False
    iso = raw.get("isoCountryCode") or raw.get("iso_country_code") or ""
    languages = raw.get("languages")
    if languages is None or not isinstance(languages, dict):
        languages = {}

    out: Dict[str, Any] = {
        "code": code,
        "name": name,
        "isoCountryCode": iso,
        "tier": tier,
        "status": status,
        "hasHierarchy": bool(has_h),
        "languages": languages,
    }
    if include_parent_code:
        out["parentCode"] = parent_code
    return out


def fetch_page(
    session: requests.Session,
    url: str,
    parent_param: str,
    lang: str,
    timeout: float,
) -> List[Dict[str, Any]]:
    params: Dict[str, str] = {"lang": lang}
    # tier1：瀏覽器是 parentDestinationCode= 空字串
    params["parentDestinationCode"] = parent_param

    last_resp: Optional[requests.Response] = None
    for attempt in range(2):
        _refresh_session_bearer_from_token_file(session)
        maybe_proactive_refresh_be2_access(session, timeout)

        # 與瀏覽器請求對齊；部分 gateway 會檢查此欄位
        req_headers = {"request-uuid": str(uuid.uuid4())}
        logger.debug(
            "GET hierarchy-with-groups parent={!r} attempt={} request-uuid={}",
            parent_param,
            attempt + 1,
            req_headers["request-uuid"],
        )
        r = session.get(url, params=params, timeout=timeout, headers=req_headers)
        last_resp = r

        if r.status_code in (401, 403) and attempt == 0 and _load_refresh_token():
            with _token_refresh_lock:
                _refresh_session_bearer_from_token_file(session)
                if try_refresh_be2_access_token(session, timeout):
                    logger.info("access token 已刷新，重試 geo 請求 parent={!r}", parent_param)
                    continue

        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            snippet = (r.text or "").strip()[:500]
            extra = f"\n回應內文摘要: {snippet!r}" if snippet else ""
            if r.status_code == 403:
                extra += (
                    "\n403 常見原因：① access JWT 已過期——可設定 KKDAY_BE2_REFRESH_TOKEN(_FILE) 自動 refresh；"
                    "② 未連公司 VPN；③ WAF／UA。"
                    "\n若已設 refresh 仍失敗，可試 KKDAY_BE2_AUTH_COOKIE（與瀏覽器相同）。"
                )
            raise requests.HTTPError(f"{e}{extra}", response=r) from e

        body = r.json()
        items = _extract_destinations_list(body)
        logger.debug(
            "回應 200 parent={!r} 解析到 {} 筆 destinations",
            parent_param,
            len(items),
        )
        return items

    if last_resp is not None:
        last_resp.raise_for_status()
    raise RuntimeError("fetch_page: unexpected fallthrough")


def _iso_key(iso_raw: Optional[str]) -> str:
    """分組用 ISO key；空白則 _EMPTY。"""
    s = (iso_raw or "").strip().upper()
    return s if s else "_EMPTY"


def _iso_fs_dir(iso_key: str) -> str:
    """資料夾名稱（檔案系統安全）。"""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in iso_key)


def _meta_json_path(output_dir: str) -> str:
    return os.path.join(output_dir, "meta.json")


def read_crawl_status(output_dir: str) -> Optional[str]:
    p = _meta_json_path(output_dir)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            m = json.load(f)
        raw = m.get("crawlStatus")
        return str(raw) if raw is not None else None
    except (OSError, json.JSONDecodeError):
        return None


CRAWL_PROGRESS_BASENAME = "crawl_progress.json"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _crawl_progress_path(output_root: str) -> str:
    return os.path.join(output_root, CRAWL_PROGRESS_BASENAME)


def _atomic_write_json(path: str, data: Any) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _read_meta_status_and_count(subdir: str) -> Tuple[Optional[str], Optional[int]]:
    p = _meta_json_path(subdir)
    if not os.path.isfile(p):
        return None, None
    try:
        with open(p, "r", encoding="utf-8") as f:
            m = json.load(f)
        st = m.get("crawlStatus")
        st_s = str(st) if st is not None else None
        c = m.get("count")
        try:
            ci = int(c) if c is not None else None
        except (TypeError, ValueError):
            ci = None
        return st_s, ci
    except (OSError, json.JSONDecodeError):
        return None, None


def _progress_summary(countries: Dict[str, Any]) -> Dict[str, int]:
    def cnt(status: str) -> int:
        return sum(1 for v in countries.values() if v.get("status") == status)

    return {
        "complete": cnt("complete"),
        "in_progress": cnt("in_progress"),
        "pending": cnt("pending"),
        "skipped": cnt("skipped"),
        "failed": cnt("failed"),
    }


def build_crawl_progress_document(
    output_root: str,
    by_iso: Dict[str, List[Dict[str, Any]]],
    only_iso: Optional[Set[str]],
    tier1_fetched_at_utc: str,
) -> Dict[str, Any]:
    """
    先建立各國資料夾，並產生 crawl_progress.json 初稿（依各國 meta.json 還原 complete / 待重跑）。
    """
    output_root = os.path.abspath(output_root)
    os.makedirs(output_root, exist_ok=True)
    countries: Dict[str, Any] = {}

    for ik in sorted(by_iso.keys()):
        folder = _iso_fs_dir(ik)
        subdir = os.path.join(output_root, folder)
        os.makedirs(subdir, exist_ok=True)

        if only_iso and ik not in only_iso:
            countries[ik] = {
                "folder": folder,
                "status": "skipped",
                "note": "未在 --only-iso 範圍內",
                "updatedAt": _utcnow_iso(),
            }
            continue

        st, cnt = _read_meta_status_and_count(subdir)
        if st == "complete":
            countries[ik] = {
                "folder": folder,
                "status": "complete",
                "count": cnt,
                "updatedAt": _utcnow_iso(),
            }
        elif st == "in_progress":
            countries[ik] = {
                "folder": folder,
                "status": "pending",
                "note": "上次中斷（meta 為 in_progress），本次將重撈",
                "updatedAt": _utcnow_iso(),
            }
        else:
            countries[ik] = {
                "folder": folder,
                "status": "pending",
                "updatedAt": _utcnow_iso(),
            }

    doc: Dict[str, Any] = {
        "version": 1,
        "outputRoot": output_root,
        "tier1FetchedAtUtc": tier1_fetched_at_utc,
        "updatedAt": _utcnow_iso(),
        "summary": _progress_summary(countries),
        "countries": countries,
        "hint": "token 過期重跑：固定同一 --output-dir 並加 --resume；看 summary 與各國 status。in_progress=執行中或異常中斷。",
    }
    return doc


class CrawlProgressTracker:
    """執行緒安全更新 crawl_progress.json（並行 by-country 時使用）。"""

    def __init__(self, output_root: str, initial_doc: Dict[str, Any]):
        self._path = _crawl_progress_path(output_root)
        self._doc = initial_doc
        self._lock = threading.Lock()

    def write_file_unlocked_initial(self) -> None:
        _atomic_write_json(self._path, self._doc)

    def mark(self, iso_key: str, **fields: Any) -> None:
        with self._lock:
            block = self._doc["countries"].get(iso_key)
            if not block:
                return
            block.update(fields)
            block["updatedAt"] = _utcnow_iso()
            self._doc["updatedAt"] = _utcnow_iso()
            self._doc["summary"] = _progress_summary(self._doc["countries"])
            _atomic_write_json(self._path, self._doc)

    def refresh_from_disk(self, by_iso: Dict[str, List[Dict[str, Any]]], only_iso: Optional[Set[str]]) -> None:
        """結束前依各國 meta.json 再對齊一次（complete 筆數等）。"""
        with self._lock:
            for ik in sorted(by_iso.keys()):
                if only_iso and ik not in only_iso:
                    continue
                block = self._doc["countries"].get(ik)
                if not block or block.get("status") == "skipped":
                    continue
                subdir = os.path.join(self._doc["outputRoot"], _iso_fs_dir(ik))
                st, cnt = _read_meta_status_and_count(subdir)
                if st == "complete":
                    block["status"] = "complete"
                    block["count"] = cnt
                elif st == "in_progress":
                    block["status"] = "in_progress"
                    block["note"] = "未完成（可能 token 過期或中斷）；請換 token 後 --resume 重跑"
                    block.pop("count", None)
                else:
                    if block.get("status") != "complete":
                        block["status"] = "pending"
                        block.pop("count", None)
                block["updatedAt"] = _utcnow_iso()
            self._doc["updatedAt"] = _utcnow_iso()
            self._doc["summary"] = _progress_summary(self._doc["countries"])
            _atomic_write_json(self._path, self._doc)


def write_country_meta_in_progress(
    output_dir: str,
    iso_key: str,
    tier1_codes: List[str],
    base_meta: Dict[str, Any],
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    meta = {
        **base_meta,
        "crawlStatus": "in_progress",
        "isoCountryCode": "" if iso_key == "_EMPTY" else iso_key,
        "isoFolder": _iso_fs_dir(iso_key),
        "tier1RootCodes": tier1_codes,
    }
    with open(_meta_json_path(output_dir), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _crawl_bfs(
    session: requests.Session,
    url: str,
    lang: str,
    delay: float,
    jitter: float,
    timeout: float,
    include_parent_code: bool,
    max_nodes: int,
    progress_interval: int,
    q: "deque[Tuple[str, Optional[str]]]",
    seen: Set[str],
    results: List[Dict[str, Any]],
    *,
    log_prefix: str = "",
) -> int:
    """
    BFS 遞迴抓取。佇列元素：(parentDestinationCode, 子節點要寫入的 parentCode)。
    回傳 API 請求次數。
    """
    fetch_count = 0
    prog_iv = max(1, int(progress_interval))
    pf = log_prefix or ""

    while q:
        if len(results) >= max_nodes:
            logger.error("{}已達 max_nodes={} 上限（目前 {} 筆）", pf, max_nodes, len(results))
            raise RuntimeError(
                f"已達 --max-nodes={max_nodes} 上限，請調高上限或檢查是否迴圈。"
            )

        parent_query, parent_code_for_record = q.popleft()
        fetch_count += 1
        logger.debug(
            "{}佇列深度 {}，第 {} 次請求，parent={!r}",
            pf,
            len(q),
            fetch_count,
            parent_query,
        )
        try:
            items = fetch_page(session, url, parent_query, lang, timeout)
        except requests.HTTPError as e:
            logger.error(
                "{}HTTP 失敗 parentDestinationCode={!r}: {}",
                pf,
                parent_query,
                e,
            )
            raise SystemExit(f"HTTP 錯誤 parentDestinationCode={parent_query!r}: {e}") from e

        if fetch_count == 1 or fetch_count % prog_iv == 0:
            logger.info(
                "{}進度 第 {} 次請求 parent={!r} | 本層 {} 筆 | 累計節點 {} | 佇列待鑽 {}",
                pf,
                fetch_count,
                parent_query,
                len(items),
                len(results),
                len(q),
            )

        _sleep_between_requests(delay, jitter)

        for raw in items:
            code = raw.get("code") or raw.get("destinationCode") or raw.get("id")
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)

            norm = _normalize_item(
                raw,
                parent_code_for_record,
                include_parent_code=include_parent_code,
            )
            results.append(norm)

            has_h = norm.get("hasHierarchy")
            if has_h:
                q.append((str(code), str(code)))

    logger.success(
        "{}遞迴結束：共 {} 次 API 請求，收集 {} 筆唯一 destination",
        pf,
        fetch_count,
        len(results),
    )
    return fetch_count


def crawl_all(
    session: requests.Session,
    url: str,
    lang: str,
    delay: float,
    jitter: float,
    timeout: float,
    include_parent_code: bool,
    max_nodes: int,
    progress_interval: int,
) -> List[Dict[str, Any]]:
    q: deque[Tuple[str, Optional[str]]] = deque()
    q.append(("", None))
    seen: Set[str] = set()
    results: List[Dict[str, Any]] = []

    logger.info(
        "開始遞迴抓取（全樹）base_url={} lang={} delay={} jitter={} max_nodes={}",
        url,
        lang,
        delay,
        jitter,
        max_nodes,
    )
    _crawl_bfs(
        session,
        url,
        lang,
        delay,
        jitter,
        timeout,
        include_parent_code,
        max_nodes,
        progress_interval,
        q,
        seen,
        results,
        log_prefix="",
    )
    return results


def _session_from_headers(hdrs: Dict[str, Any]) -> requests.Session:
    """每條並行 worker 獨立 Session（requests.Session 非 thread-safe）。"""
    s = requests.Session()
    for k, v in hdrs.items():
        if v is None:
            continue
        s.headers[str(k)] = v if isinstance(v, str) else str(v)
    return s


def _headers_snapshot(session: requests.Session) -> Dict[str, str]:
    return {str(k): str(v) for k, v in session.headers.items() if v is not None}


def _execute_one_iso_country(
    session: requests.Session,
    iso_key: str,
    group: List[Dict[str, Any]],
    subdir: str,
    url: str,
    lang: str,
    delay: float,
    jitter: float,
    timeout: float,
    include_parent_code: bool,
    max_nodes: int,
    progress_interval: int,
    base_meta_template: Dict[str, Any],
) -> int:
    """單一 ISO：寫 in_progress → BFS → bundle。回傳節點筆數。"""
    tier1_codes = [str(x.get("code") or "") for x in group if x.get("code")]
    logger.info(
        "by-country：開始 iso={} tier1 根 {} 個 → {}",
        iso_key,
        len(group),
        subdir,
    )

    write_country_meta_in_progress(subdir, iso_key, tier1_codes, base_meta_template)

    seen: Set[str] = set()
    results: List[Dict[str, Any]] = []
    q: deque[Tuple[str, Optional[str]]] = deque()

    for root in group:
        rc = root.get("code")
        if not rc:
            continue
        if rc in seen:
            continue
        seen.add(str(rc))
        results.append(root)
        if root.get("hasHierarchy"):
            q.append((str(rc), str(rc)))

    t_iso = time.time()
    _crawl_bfs(
        session,
        url,
        lang,
        delay,
        jitter,
        timeout,
        include_parent_code,
        max_nodes,
        progress_interval,
        q,
        seen,
        results,
        log_prefix=f"[{iso_key}] ",
    )
    elapsed_iso = time.time() - t_iso

    meta_out = {
        **base_meta_template,
        "fetchedAtUtc": datetime.now(timezone.utc).isoformat(),
        "elapsedSeconds": round(elapsed_iso, 3),
        "crawlStatus": "complete",
        "isoCountryCode": "" if iso_key == "_EMPTY" else iso_key,
        "isoFolder": _iso_fs_dir(iso_key),
        "tier1RootCodes": tier1_codes,
        "count": len(results),
    }
    write_performance_bundle(subdir, meta_out, results)
    logger.success("by-country：已寫入 {}（{} 筆）", subdir, len(results))
    return len(results)


def crawl_by_country_to_dirs(
    session: requests.Session,
    output_root: str,
    url: str,
    lang: str,
    delay: float,
    jitter: float,
    timeout: float,
    include_parent_code: bool,
    max_nodes: int,
    progress_interval: int,
    *,
    resume: bool,
    only_iso: Optional[Set[str]],
    base_meta_template: Dict[str, Any],
    parallel_iso: int,
) -> None:
    """
    先打 parent="" 取得 tier1，依 isoCountryCode 分組，每組寫入 output_root/{ISO}/ 獨立 bundle。
    同一 ISO 可能對應多個 tier1 根節點，會合併為一次 BFS。
    """
    logger.info("by-country：抓取 tier1（parent=\"\"）…")
    try:
        raw_tier1 = fetch_page(session, url, "", lang, timeout)
    except requests.HTTPError as e:
        logger.error("tier1 請求失敗：{}", e)
        raise SystemExit(f"tier1 HTTP 錯誤: {e}") from e
    _sleep_between_requests(delay, jitter)

    roots: List[Dict[str, Any]] = []
    for raw in raw_tier1:
        code = raw.get("code") or raw.get("destinationCode") or raw.get("id")
        if not code:
            continue
        roots.append(
            _normalize_item(raw, None, include_parent_code=include_parent_code)
        )

    by_iso: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in roots:
        ik = _iso_key(r.get("isoCountryCode"))
        by_iso[ik].append(r)

    output_root = os.path.abspath(output_root)
    tier1_fetched_at = _utcnow_iso()
    progress_doc = build_crawl_progress_document(
        output_root, by_iso, only_iso, tier1_fetched_at
    )
    progress_tr = CrawlProgressTracker(output_root, progress_doc)
    progress_tr.write_file_unlocked_initial()
    logger.info(
        "已預先建立各國資料夾並寫入進度檔：{}",
        _crawl_progress_path(output_root),
    )

    jobs: List[Tuple[str, List[Dict[str, Any]], str]] = []
    for iso_key in sorted(by_iso.keys()):
        if only_iso and iso_key not in only_iso:
            logger.debug("only-iso：略過 {}", iso_key)
            continue

        group = by_iso[iso_key]
        subdir = os.path.join(output_root, _iso_fs_dir(iso_key))
        if resume and read_crawl_status(subdir) == "complete":
            logger.info("resume：略過已完成 iso={} → {}", iso_key, subdir)
            continue

        jobs.append((iso_key, group, subdir))

    pi = max(1, int(parallel_iso))
    if pi > 8:
        logger.warning(
            "--parallel-iso={} 偏高，gateway 可能 429/403；已建議上限 8，仍依你指定執行",
            pi,
        )

    if len(jobs) > 1 and pi > 1:
        logger.info(
            "by-country：{} 國待跑，並行 worker={}（每國內仍 delay={} jitter={}）",
            len(jobs),
            min(pi, len(jobs)),
            delay,
            jitter,
        )

    if pi <= 1 or len(jobs) <= 1:
        for iso_key, group, subdir in jobs:
            progress_tr.mark(
                iso_key,
                status="in_progress",
                startedAt=_utcnow_iso(),
                note="抓取中…",
            )
            n = _execute_one_iso_country(
                session,
                iso_key,
                group,
                subdir,
                url,
                lang,
                delay,
                jitter,
                timeout,
                include_parent_code,
                max_nodes,
                progress_interval,
                base_meta_template,
            )
            progress_tr.mark(
                iso_key,
                status="complete",
                count=n,
                finishedAt=_utcnow_iso(),
                note="",
            )
    else:
        hdrs = _headers_snapshot(session)
        workers = min(pi, len(jobs))

        def _run_one(job: Tuple[str, List[Dict[str, Any]], str]) -> None:
            iso_key, group, subdir = job
            progress_tr.mark(
                iso_key,
                status="in_progress",
                startedAt=_utcnow_iso(),
                note="抓取中…",
            )
            th_session = _session_from_headers(hdrs)
            n = _execute_one_iso_country(
                th_session,
                iso_key,
                group,
                subdir,
                url,
                lang,
                delay,
                jitter,
                timeout,
                include_parent_code,
                max_nodes,
                progress_interval,
                base_meta_template,
            )
            progress_tr.mark(
                iso_key,
                status="complete",
                count=n,
                finishedAt=_utcnow_iso(),
                note="",
            )

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_run_one, j) for j in jobs]
            for fu in as_completed(futures):
                fu.result()

    progress_tr.refresh_from_disk(by_iso, only_iso)
    logger.info("已更新進度檔（與各國 meta 對齊）：{}", _crawl_progress_path(output_root))

    # 根目錄索引（方便看各國狀態／筆數）
    idx_path = os.path.join(output_root, "by_country_index.json")
    entries: List[Dict[str, Any]] = []
    for ik in sorted(by_iso.keys()):
        sd = os.path.join(output_root, _iso_fs_dir(ik))
        st = read_crawl_status(sd)
        cnt: Optional[int] = None
        if st == "complete" and os.path.isfile(_meta_json_path(sd)):
            try:
                with open(_meta_json_path(sd), "r", encoding="utf-8") as mf:
                    cnt = int(json.load(mf).get("count", 0))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass
        entries.append(
            {
                "isoCountryCode": ik,
                "folder": _iso_fs_dir(ik),
                "crawlStatus": st,
                "count": cnt,
            }
        )
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "outputRoot": output_root,
                "entries": entries,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("已寫入索引：{}", idx_path)


def write_performance_bundle(
    output_dir: str,
    meta: Dict[str, Any],
    destinations: List[Dict[str, Any]],
) -> None:
    """
    將資料寫入同一資料夾，方便離線高效讀取：
    - meta.json：本次抓取摘要（不含大陣列）
    - destinations.jsonl：每行一筆 JSON，適合串流 / 分批載入
    - destinations.sqlite：以 code 為 PK，並建 parent / tier / iso 索引，適合隨機查詢與 JOIN
    """
    os.makedirs(output_dir, exist_ok=True)
    logger.info("寫入效能 bundle → {}", os.path.abspath(output_dir))
    meta_path = os.path.join(output_dir, "meta.json")
    jsonl_path = os.path.join(output_dir, "destinations.jsonl")
    db_path = os.path.join(output_dir, "destinations.sqlite")

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for row in destinations:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute(
            """
            CREATE TABLE destinations (
                code TEXT PRIMARY KEY NOT NULL,
                parent_code TEXT,
                name TEXT NOT NULL DEFAULT '',
                iso_country_code TEXT NOT NULL DEFAULT '',
                tier INTEGER,
                status TEXT NOT NULL DEFAULT '',
                has_hierarchy INTEGER NOT NULL DEFAULT 0,
                languages_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_destinations_parent ON destinations(parent_code);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_destinations_iso_tier ON destinations(iso_country_code, tier);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_destinations_tier ON destinations(tier);")

        rows = []
        for d in destinations:
            code = d.get("code") or ""
            parent = d.get("parentCode")
            langs = d.get("languages") or {}
            if not isinstance(langs, dict):
                langs = {}
            rows.append(
                (
                    code,
                    parent,
                    d.get("name") or "",
                    d.get("isoCountryCode") or "",
                    d.get("tier"),
                    d.get("status") or "",
                    1 if d.get("hasHierarchy") else 0,
                    json.dumps(langs, ensure_ascii=False),
                )
            )
        conn.executemany(
            """
            INSERT INTO destinations (
                code, parent_code, name, iso_country_code, tier, status, has_hierarchy, languages_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "bundle 完成：meta.json、destinations.jsonl、destinations.sqlite（{} 筆）",
        len(destinations),
    )


def main() -> None:
    p = argparse.ArgumentParser(description="遞迴抓取 BE2 destination 階層（stage）")
    p.add_argument(
        "--base-url",
        default=os.environ.get("KKDAY_BE2_GEO_BASE", DEFAULT_BASE),
        help="hierarchy-with-groups API 完整 URL（不含 query）",
    )
    p.add_argument("--lang", default="zh-tw")
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="輸出單一 JSON；若未同時指定 --output-dir，則不寫預設 bundle（僅 -o）",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help=(
            "輸出資料夾（bundle）。未指定時預設：腳本同層 be2_destinations_dump/<UTC時間戳>/"
        ),
    )
    p.add_argument(
        "--delay",
        type=float,
        default=_env_float("KKDAY_BE2_REQUEST_DELAY", DEFAULT_REQUEST_DELAY),
        help=(
            "每次請求成功後至少間隔秒數（預設 1.0；可用環境變數 KKDAY_BE2_REQUEST_DELAY）"
        ),
    )
    p.add_argument(
        "--jitter",
        type=float,
        default=_env_float("KKDAY_BE2_REQUEST_JITTER", DEFAULT_REQUEST_JITTER),
        help=(
            "每次請求後額外隨機等待 0～jitter 秒（預設 0.5；環境變數 KKDAY_BE2_REQUEST_JITTER）"
        ),
    )
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument(
        "--max-nodes",
        type=int,
        default=500_000,
        help="安全上限：最多收集幾筆 destination（防無限迴圈）",
    )
    p.add_argument(
        "--no-parent-code",
        action="store_true",
        help="輸出不附 parentCode（僅保留你指定的 7 個欄位）",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("KKDAY_BE2_BEARER_TOKEN", ""),
        help="Bearer token；建議改用環境變數 KKDAY_BE2_BEARER_TOKEN 或 KKDAY_BE2_BEARER_TOKEN_FILE",
    )
    p.add_argument(
        "--log-level",
        default=os.environ.get("KKDAY_BE2_LOG_LEVEL", "INFO"),
        help="loguru 等級：TRACE/DEBUG/INFO/SUCCESS/WARNING/ERROR（環境變數 KKDAY_BE2_LOG_LEVEL）",
    )
    p.add_argument(
        "--log-file",
        default=(os.environ.get("KKDAY_BE2_LOG_FILE") or "").strip() or None,
        help="額外寫入日誌檔（rotation 50MB；環境變數 KKDAY_BE2_LOG_FILE）",
    )
    p.add_argument(
        "--progress-interval",
        type=int,
        default=_env_int("KKDAY_BE2_PROGRESS_INTERVAL", 20),
        help="每隔幾次成功請求打一筆 INFO 進度（環境變數 KKDAY_BE2_PROGRESS_INTERVAL，預設 20）",
    )
    p.add_argument(
        "--by-country",
        action="store_true",
        help="依 tier1 的 isoCountryCode 分子資料夾（預設 output-dir 同一般模式）；見 --resume / --only-iso",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="by-country 時略過子資料夾 meta.crawlStatus 已為 complete 的國家（中斷國別會重撈）",
    )
    p.add_argument(
        "--only-iso",
        default=None,
        help="by-country 時只處理這些 ISO，逗號分隔，例如 TW,JP（空白國家用 _EMPTY）",
    )
    p.add_argument(
        "--parallel-iso",
        type=int,
        default=_env_int("KKDAY_BE2_PARALLEL_ISO", 1),
        help=(
            "by-country 時同時跑幾個國家（thread 並行，每國獨立 Session；國內仍節流）。"
            "預設 1；>1 可能觸發 gateway 限流（環境變數 KKDAY_BE2_PARALLEL_ISO）"
        ),
    )
    p.add_argument(
        "--no-refresh-at-start",
        action="store_true",
        help=(
            "已設 KKDAY_BE2_REFRESH_TOKEN(_FILE) 時，預設會在進 geo 前先打一次 refresh；"
            "此旗標可關閉（等同 KKDAY_BE2_REFRESH_AT_START=0）"
        ),
    )
    args = p.parse_args()

    _configure_loguru(args.log_level, args.log_file)

    token = (args.token or "").strip()
    if not token:
        path = (os.environ.get("KKDAY_BE2_BEARER_TOKEN_FILE") or "").strip()
        if path:
            try:
                raw = open(path, "r", encoding="utf-8").read()
                token = raw.strip()
            except OSError as e:
                logger.error("無法讀取 KKDAY_BE2_BEARER_TOKEN_FILE（{}）：{}", path, e)
                sys.exit(2)
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        logger.error(
            "請設定 Bearer token，例如：\n"
            "  export KKDAY_BE2_BEARER_TOKEN='eyJ...'\n"
            "或（避免出現在 shell history）：\n"
            "  export KKDAY_BE2_BEARER_TOKEN_FILE=\"$HOME/.kkday_be2_bearer\"\n"
            "  printf '%s' 'eyJ...' > \"$KKDAY_BE2_BEARER_TOKEN_FILE\" && chmod 600 \"$KKDAY_BE2_BEARER_TOKEN_FILE\"\n"
            "不要把 token 寫進 git。"
        )
        sys.exit(2)

    forwarded = os.environ.get("KKDAY_BE2_FORWARDED_ID", "BE2-DESTINATIONS")
    x_auth = os.environ.get("KKDAY_BE2_X_AUTH_ID", "be2")
    # 與瀏覽器 curl 對齊，部分環境的 gateway / WAF 會擋非瀏覽器 UA
    default_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    user_agent = os.environ.get("KKDAY_BE2_USER_AGENT", default_ua).strip() or default_ua
    accept_language = os.environ.get("KKDAY_BE2_ACCEPT_LANGUAGE", "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7")

    session = requests.Session()
    hdrs: Dict[str, str] = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "kkday-forwarded-id": forwarded,
        "origin": "https://be2.stage.kkday.com",
        "referer": "https://be2.stage.kkday.com/",
        "user-agent": user_agent,
        "x-auth-id": x_auth,
    }
    if accept_language:
        hdrs["accept-language"] = accept_language
    session.headers.update(hdrs)

    use_file = bool((os.environ.get("KKDAY_BE2_BEARER_TOKEN_FILE") or "").strip())
    use_refresh = bool(_load_refresh_token())
    logger.info(
        "Session 就緒：base_url={} lang={} token_file_mode={} Bearer 長度={} auto_refresh={}（內文永不寫入 log）",
        args.base_url,
        args.lang,
        use_file,
        len(token),
        use_refresh,
    )

    refresh_at_start = use_refresh and _refresh_at_program_start_enabled(
        bool(args.no_refresh_at_start)
    )
    maybe_refresh_tokens_at_program_start(
        session, args.timeout, enabled=refresh_at_start
    )

    include_parent = not args.no_parent_code

    if args.by_country:
        if args.output:
            logger.error("不可同時使用 -o / --output 與 --by-country")
            sys.exit(2)
        out_dir_bc = args.output_dir or default_run_output_dir()
        only_iso_set = _parse_only_iso_csv(args.only_iso)
        base_meta_template: Dict[str, Any] = {
            "source": args.base_url,
            "lang": args.lang,
            "includeParentCode": include_parent,
            "mode": "by-country",
            "parallelIsoWorkers": max(1, int(args.parallel_iso)),
            "requestThrottle": {
                "delaySeconds": args.delay,
                "jitterSecondsMax": args.jitter,
            },
            "bundleFiles": {
                "meta": "meta.json",
                "jsonl": "destinations.jsonl",
                "sqlite": "destinations.sqlite",
            },
        }
        t0 = time.time()
        logger.info("by-country 輸出根目錄：{}", os.path.abspath(out_dir_bc))
        crawl_by_country_to_dirs(
            session,
            out_dir_bc,
            args.base_url,
            args.lang,
            args.delay,
            args.jitter,
            args.timeout,
            include_parent,
            args.max_nodes,
            args.progress_interval,
            resume=bool(args.resume),
            only_iso=only_iso_set,
            base_meta_template=base_meta_template,
            parallel_iso=max(1, int(args.parallel_iso)),
        )
        elapsed = time.time() - t0
        logger.success(
            "by-country 流程結束（總歷時 {:.1f}s），根目錄：{}",
            elapsed,
            os.path.abspath(out_dir_bc),
        )
        return

    t0 = time.time()
    destinations = crawl_all(
        session,
        args.base_url,
        args.lang,
        args.delay,
        args.jitter,
        args.timeout,
        include_parent_code=include_parent,
        max_nodes=args.max_nodes,
        progress_interval=args.progress_interval,
    )
    elapsed = time.time() - t0

    meta = {
        "source": args.base_url,
        "lang": args.lang,
        "fetchedAtUtc": datetime.now(timezone.utc).isoformat(),
        "count": len(destinations),
        "elapsedSeconds": round(elapsed, 3),
        "includeParentCode": include_parent,
        "crawlStatus": "complete",
        "requestThrottle": {
            "delaySeconds": args.delay,
            "jitterSecondsMax": args.jitter,
        },
        "bundleFiles": {
            "meta": "meta.json",
            "jsonl": "destinations.jsonl",
            "sqlite": "destinations.sqlite",
        },
    }

    out_path = args.output
    out_dir = args.output_dir
    if not out_path and not out_dir:
        out_dir = default_run_output_dir()
        logger.info("未指定輸出路徑，使用預設 bundle 目錄：{}", os.path.abspath(out_dir))

    if out_dir:
        bundle_dir = os.path.abspath(out_dir)
        write_performance_bundle(bundle_dir, meta, destinations)
        logger.success("已寫入效能 bundle：{}/", bundle_dir)
        logger.info("  - meta.json / destinations.jsonl / destinations.sqlite")

    if out_path:
        payload = {"meta": meta, "destinations": destinations}
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.success("已寫入單檔 JSON：{}", out_path)

    logger.success("完成：共 {} 筆 destination，耗時 {:.1f}s", len(destinations), elapsed)


if __name__ == "__main__":
    main()
