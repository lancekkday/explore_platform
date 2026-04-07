"""
be2_api.py — BE2 stage API 認證工具（可 import 的 skill）

封裝 token 載入、自動 refresh（proactive + reactive on 401/403）、輪替寫回。
與瀏覽器行為一致：
  GET svc-geo → 403 → PATCH refresh-token → response 含新 accessToken + refreshToken
                     → 用新 accessToken 繼續打 API

環境變數:
  KKDAY_BE2_BEARER_TOKEN_FILE          access JWT 檔案路徑（每次請求前重讀，支援中途熱換）
  KKDAY_BE2_BEARER_TOKEN               直接傳入 access JWT
  KKDAY_BE2_REFRESH_TOKEN_FILE         refresh JWT 檔案路徑（refresh 成功後自動輪替寫回）
  KKDAY_BE2_REFRESH_TOKEN              直接傳入 refresh JWT
  KKDAY_BE2_AUTH_COOKIE                瀏覽器 Cookie 字串（解決 AU9997，通常必要）
  KKDAY_BE2_AUTH_BASE                  auth service 根 URL（預設 https://auth.stage.kkday.com）
  KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC  提前幾秒主動 refresh（預設 120；0 = 關閉）
  KKDAY_BE2_FORWARDED_ID               kkday-forwarded-id header（預設 BE2-DESTINATIONS）
  KKDAY_BE2_X_AUTH_ID                  x-auth-id header（預設 be2）
  KKDAY_BE2_USER_AGENT                 User-Agent（預設 Chrome/macOS 風格）
  KKDAY_BE2_ACCEPT_LANGUAGE            Accept-Language（預設 zh-TW,...；空字串可關閉）

用法:
  from be2_api import Be2Session

  with Be2Session() as s:
      resp = s.get(
          "https://api-gateway.stage.kkday.com/svc-geo/api/admin/destinations/hierarchy-with-groups",
          params={"lang": "zh-tw", "parentDestinationCode": ""},
      )
      data = resp.json()

  # 或不用 context manager：
  s = Be2Session()
  try:
      ...
  finally:
      s.close()
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
_DEFAULT_AUTH_BASE = "https://auth.stage.kkday.com"


# ─── JWT helpers ─────────────────────────────────────────────────────────────


def jwt_exp(token: str) -> Optional[float]:
    """Extract `exp` (unix seconds) from JWT payload without verifying signature."""
    parts = token.strip().split(".")
    if len(parts) < 2:
        return None
    b64 = parts[1]
    b64 += "=" * ((-len(b64)) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(b64.encode()))
        return float(payload["exp"])
    except Exception:
        return None


def _expiring_soon(token: str, buffer_sec: float) -> bool:
    if buffer_sec <= 0:
        return False
    exp = jwt_exp(token)
    return exp is not None and (exp - time.time()) <= buffer_sec


# ─── Token file I/O ──────────────────────────────────────────────────────────


def _read_env_token(file_env: str, direct_env: str) -> Optional[str]:
    """Read token from file path env var, then fall back to direct env var."""
    path = (os.environ.get(file_env) or "").strip()
    if path and os.path.isfile(path):
        try:
            raw = open(path, encoding="utf-8").read().strip()
            raw = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
            if raw:
                return raw
        except OSError:
            pass
    direct = (os.environ.get(direct_env) or "").strip()
    if direct.lower().startswith("bearer "):
        direct = direct[7:].strip()
    return direct or None


def _write_env_token(file_env: str, value: str) -> None:
    """Atomically write token to file configured in env var (no-op if not set)."""
    path = (os.environ.get(file_env) or "").strip()
    if not path:
        return
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(value.strip() + "\n")
        os.replace(tmp, path)
    except OSError as e:
        logger.warning("寫入 {} 失敗：{}", file_env, e)


# ─── Response token extraction ───────────────────────────────────────────────


def _collect_by_key(obj: Any, keys: Tuple[str, ...], out: List[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and len(v) > 20:
                out.append(v.strip())
            _collect_by_key(v, keys, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _collect_by_key(item, keys, out, depth + 1)


def _extract_token_from_response(body: Any, keys: Tuple[str, ...]) -> Optional[str]:
    """Search common paths in auth response JSON for a token by key names."""
    if not isinstance(body, dict):
        return None
    for container in (body.get("data"), body):
        if not isinstance(container, dict):
            continue
        for k in keys:
            v = container.get(k)
            if isinstance(v, str) and len(v) > 30:
                return v.strip()
    # Deep fallback search
    walked: List[str] = []
    _collect_by_key(body, keys, walked)
    return next((s for s in walked if len(s) > 30), None)


# ─── Be2Session ──────────────────────────────────────────────────────────────


class Be2Session:
    """
    requests.Session wrapper with automatic BE2 token refresh.

    Token refresh flow (mirrors the browser):
      1. Proactive: refreshes KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC seconds before expiry
      2. Reactive:  on 401/403, calls PATCH refresh-token then retries once
      After each successful refresh, both accessToken and refreshToken are
      written back to their respective files.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        refresh_buffer_sec: Optional[float] = None,
    ) -> None:
        self._timeout = timeout
        self._refresh_buffer_sec = float(
            os.environ.get("KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC") or refresh_buffer_sec or 120.0
        )
        self._lock = threading.Lock()
        self._session = self._build_session()
        self._load_access_into_session()

    # ── Setup ──────────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        ua = (os.environ.get("KKDAY_BE2_USER_AGENT") or _DEFAULT_UA).strip()
        fwd = (os.environ.get("KKDAY_BE2_FORWARDED_ID") or "BE2-DESTINATIONS").strip()
        x_auth = (os.environ.get("KKDAY_BE2_X_AUTH_ID") or "be2").strip()
        accept_lang = (
            os.environ.get("KKDAY_BE2_ACCEPT_LANGUAGE")
            if "KKDAY_BE2_ACCEPT_LANGUAGE" in os.environ
            else "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        )
        hdrs: Dict[str, str] = {
            "accept": "application/json",
            "content-type": "application/json",
            "kkday-forwarded-id": fwd,
            "x-auth-id": x_auth,
            "origin": "https://be2.stage.kkday.com",
            "referer": "https://be2.stage.kkday.com/",
            "user-agent": ua,
        }
        if accept_lang:
            hdrs["accept-language"] = accept_lang.strip()
        s.headers.update(hdrs)
        return s

    def _load_access_into_session(self) -> None:
        token = _read_env_token("KKDAY_BE2_BEARER_TOKEN_FILE", "KKDAY_BE2_BEARER_TOKEN")
        if not token:
            raise ValueError(
                "找不到 access token。請設定 KKDAY_BE2_BEARER_TOKEN_FILE 或 KKDAY_BE2_BEARER_TOKEN"
            )
        self._session.headers["authorization"] = f"Bearer {token}"

    def _sync_access_from_file(self) -> None:
        """Re-read access token from file into session (supports mid-run rotation)."""
        token = _read_env_token("KKDAY_BE2_BEARER_TOKEN_FILE", "")
        if token:
            self._session.headers["authorization"] = f"Bearer {token}"

    def _current_access(self) -> Optional[str]:
        self._sync_access_from_file()
        h = str(self._session.headers.get("authorization") or "")
        t = h[7:].strip() if h.lower().startswith("bearer ") else h.strip()
        return t or None

    # ── Refresh ────────────────────────────────────────────────────────────

    def refresh(self) -> bool:
        """
        Call PATCH auth.stage/api/v1/refresh-token/{refreshJWT}.
        On success: writes new accessToken + refreshToken to their files.
        Returns True on success.
        """
        refresh_jwt = _read_env_token("KKDAY_BE2_REFRESH_TOKEN_FILE", "KKDAY_BE2_REFRESH_TOKEN")
        if not refresh_jwt:
            logger.debug("未設定 refresh token，略過 refresh")
            return False

        access = self._current_access()
        if not access:
            logger.warning("無法讀取 access token，無法 refresh")
            return False

        auth_base = (os.environ.get("KKDAY_BE2_AUTH_BASE") or _DEFAULT_AUTH_BASE).rstrip("/")
        url = f"{auth_base}/api/v1/refresh-token/{refresh_jwt}"

        fwd = (
            os.environ.get("KKDAY_BE2_AUTH_FORWARDED_ID")
            or str(self._session.headers.get("kkday-forwarded-id") or "BE2-DESTINATIONS")
        ).strip()
        x_auth = (
            os.environ.get("KKDAY_BE2_AUTH_X_AUTH_ID")
            or str(self._session.headers.get("x-auth-id") or "be2")
        ).strip()

        hdrs: Dict[str, str] = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {access}",
            "kkday-forwarded-id": fwd,
            "origin": "https://be2.stage.kkday.com",
            "referer": "https://be2.stage.kkday.com/",
            "user-agent": str(self._session.headers.get("user-agent") or _DEFAULT_UA),
            "x-auth-id": x_auth,
            "request-uuid": str(uuid.uuid4()),
        }
        accept_lang = str(self._session.headers.get("accept-language") or "").strip()
        if accept_lang:
            hdrs["accept-language"] = accept_lang
        cookie = (os.environ.get("KKDAY_BE2_AUTH_COOKIE") or "").strip()
        if cookie:
            hdrs["Cookie"] = cookie

        try:
            r = requests.patch(url, headers=hdrs, timeout=self._timeout)
        except requests.RequestException as e:
            logger.warning("refresh 連線失敗：{}", e)
            return False

        if not r.ok:
            logger.warning("refresh HTTP {}：{}", r.status_code, r.text[:300])
            return False

        try:
            body = r.json()
        except json.JSONDecodeError:
            logger.warning("refresh 回應非 JSON")
            return False

        new_access = _extract_token_from_response(
            body, ("accessToken", "access_token", "token")
        )
        if not new_access:
            logger.warning(
                "refresh 回應找不到 accessToken，keys={}",
                list(body.keys()) if isinstance(body, dict) else type(body),
            )
            return False

        # Persist and update session
        self._session.headers["authorization"] = f"Bearer {new_access}"
        _write_env_token("KKDAY_BE2_BEARER_TOKEN_FILE", new_access)

        new_refresh = _extract_token_from_response(body, ("refreshToken", "refresh_token"))
        if new_refresh:
            _write_env_token("KKDAY_BE2_REFRESH_TOKEN_FILE", new_refresh)
            logger.info("refresh token 已輪替")

        exp = jwt_exp(new_access)
        ttl = int(exp - time.time()) if exp else "?"
        logger.success("refresh 成功，新 access 長度 {}，剩餘約 {}s", len(new_access), ttl)
        return True

    def _maybe_proactive_refresh(self) -> None:
        """Refresh proactively if access token is expiring soon."""
        if self._refresh_buffer_sec <= 0:
            return
        if not _read_env_token("KKDAY_BE2_REFRESH_TOKEN_FILE", "KKDAY_BE2_REFRESH_TOKEN"):
            return
        with self._lock:
            self._sync_access_from_file()
            acc = self._current_access()
            if acc and _expiring_soon(acc, self._refresh_buffer_sec):
                exp = jwt_exp(acc)
                secs_left = int((exp or time.time()) - time.time())
                logger.info("access 約 {}s 後過期（<= buffer {}s），主動 refresh",
                            secs_left, int(self._refresh_buffer_sec))
                self.refresh()
            self._sync_access_from_file()

    # ── HTTP methods ───────────────────────────────────────────────────────

    def get(self, url: str, **kwargs) -> requests.Response:
        """
        GET with auto token refresh.
        - Proactive: checks expiry before each request
        - Reactive: on 401/403, refreshes and retries once
        """
        self._maybe_proactive_refresh()
        self._sync_access_from_file()

        headers = dict(kwargs.pop("headers", {}) or {})
        headers["request-uuid"] = str(uuid.uuid4())
        kwargs.setdefault("timeout", self._timeout)

        r = self._session.get(url, headers=headers, **kwargs)

        if r.status_code in (401, 403):
            logger.info("收到 {}，嘗試 refresh 後重試", r.status_code)
            with self._lock:
                refreshed = self.refresh()
            if refreshed:
                self._sync_access_from_file()
                headers["request-uuid"] = str(uuid.uuid4())
                r = self._session.get(url, headers=headers, **kwargs)

        return r

    # ── Context manager ────────────────────────────────────────────────────

    def __enter__(self) -> "Be2Session":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()
