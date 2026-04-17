"""
Global platform settings — persisted as backend/data/settings.json.
"""
import json, os, threading

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

_DEFAULTS = {
    "environments": {
        "stage": True,
        "production": False,
    }
}

_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(_DEFAULTS)


def save_settings(settings: dict):
    envs = settings.get("environments", {})
    if not envs.get("stage") and not envs.get("production"):
        raise ValueError("至少需啟用一個環境")
    _ensure_dir()
    with _lock:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)


def get_enabled_envs() -> list[str]:
    s = load_settings()
    return [env for env, on in s.get("environments", {}).items() if on]
