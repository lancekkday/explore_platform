"""
E2E API tests — validates all endpoints used by the React frontend components.
Requires backend running on http://localhost:8000.

Run:
    cd backend && source venv/bin/activate
    pytest ../tests/test_e2e_api.py -v
"""
import pytest
import requests

BASE = "http://localhost:8000/api"


@pytest.fixture(scope="session")
def cookie():
    """Fetch a real guest cookie once for the whole session."""
    r = requests.get(f"{BASE}/guest-cookie?env=production", timeout=60)
    assert r.status_code == 200, f"guest-cookie failed: {r.text}"
    data = r.json()
    assert data.get("cookie"), "No cookie returned"
    return data["cookie"]


# ── /api/guest-cookie ─────────────────────────────────────────────────────────

def test_guest_cookie_production():
    r = requests.get(f"{BASE}/guest-cookie?env=production", timeout=60)
    assert r.status_code == 200
    body = r.json()
    assert body.get("cookie"), "cookie field missing"
    assert "csrf" in body["cookie"].lower() or len(body["cookie"]) > 50


def test_guest_cookie_invalid_env():
    r = requests.get(f"{BASE}/guest-cookie?env=invalid")
    assert r.status_code == 400


# ── /api/keywords ─────────────────────────────────────────────────────────────

def test_get_keywords():
    r = requests.get(f"{BASE}/keywords")
    assert r.status_code == 200
    body = r.json()
    assert "keywords" in body
    assert isinstance(body["keywords"], list)


def test_update_keywords():
    payload = {"keywords": ["esim", "東京一日遊"]}
    r = requests.post(f"{BASE}/keywords", json=payload)
    assert r.status_code == 200
    assert r.json().get("success")

    # verify the update persisted
    r2 = requests.get(f"{BASE}/keywords")
    kws = [k["keyword"] if isinstance(k, dict) else k for k in r2.json()["keywords"]]
    assert "esim" in kws
    assert "東京一日遊" in kws


# ── /api/batch/status ─────────────────────────────────────────────────────────

def test_batch_status():
    r = requests.get(f"{BASE}/batch/status")
    assert r.status_code == 200
    body = r.json()
    assert "is_running" in body
    assert "progress" in body
    assert isinstance(body["progress"], (int, float))


# ── /api/batch/results ────────────────────────────────────────────────────────

def test_batch_results():
    r = requests.get(f"{BASE}/batch/results")
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert isinstance(body["results"], dict)


# ── /api/batch/history ────────────────────────────────────────────────────────

def test_batch_history():
    r = requests.get(f"{BASE}/batch/history")
    assert r.status_code == 200
    body = r.json()
    assert "history" in body
    assert isinstance(body["history"], list)


def test_batch_history_detail_not_found():
    r = requests.get(f"{BASE}/batch/history/999999")
    assert r.status_code == 404


# ── /api/single/history ───────────────────────────────────────────────────────

def test_single_history():
    r = requests.get(f"{BASE}/single/history")
    assert r.status_code == 200
    body = r.json()
    assert "history" in body
    assert isinstance(body["history"], list)


def test_single_history_detail_not_found():
    r = requests.get(f"{BASE}/single/history/999999")
    assert r.status_code == 404


# ── /api/compare ─────────────────────────────────────────────────────────────

def test_compare_basic(cookie):
    payload = {"keyword": "esim", "cookie": cookie, "count": 10, "ai_enabled": False}
    r = requests.post(f"{BASE}/compare", json=payload, timeout=120)
    assert r.status_code == 200
    body = r.json()
    assert body.get("success")
    assert "stage" in body and "production" in body

    stage = body["stage"]
    assert "results" in stage
    assert "metrics" in stage
    assert isinstance(stage["results"], list)

    metrics = stage["metrics"]
    assert "ndcg_at_10" in metrics
    assert "mismatch_rate" in metrics


def test_compare_stage_metrics_range(cookie):
    """NDCG and mismatch_rate must be in [0, 1]."""
    payload = {"keyword": "esim", "cookie": cookie, "count": 10, "ai_enabled": False}
    r = requests.post(f"{BASE}/compare", json=payload, timeout=120)
    body = r.json()
    m = body["stage"]["metrics"]
    assert 0.0 <= m["ndcg_at_10"] <= 1.0
    assert 0.0 <= m["mismatch_rate"] <= 1.0


def test_compare_product_schema(cookie):
    """Each product result must have expected fields."""
    payload = {"keyword": "esim", "cookie": cookie, "count": 5, "ai_enabled": False}
    r = requests.post(f"{BASE}/compare", json=payload, timeout=120)
    results = r.json()["stage"]["results"]
    assert len(results) > 0
    for p in results:
        assert "rank" in p
        assert "id" in p
        assert "name" in p
        assert "tier" in p
        assert isinstance(p["tier"], int)
        assert p["tier"] in (0, 1, 2, 3)


def test_compare_saves_single_record(cookie):
    """After a compare call the single inspection history should grow."""
    before = requests.get(f"{BASE}/single/history").json()["history"]
    before_ids = {h["id"] for h in before}

    payload = {"keyword": "wifi", "cookie": cookie, "count": 5, "ai_enabled": False}
    requests.post(f"{BASE}/compare", json=payload, timeout=120)

    after = requests.get(f"{BASE}/single/history").json()["history"]
    after_ids = {h["id"] for h in after}
    assert after_ids - before_ids, "No new single inspection record was saved"


# ── /api/feedback ─────────────────────────────────────────────────────────────

def test_feedback_submit(cookie):
    """Submitting calibration feedback must succeed."""
    # First get a real product ID from a compare call
    payload = {"keyword": "esim", "cookie": cookie, "count": 5, "ai_enabled": False}
    compare_res = requests.post(f"{BASE}/compare", json=payload, timeout=120).json()
    product_id = compare_res["stage"]["results"][0]["id"]

    feedback = {
        "keyword": "esim",
        "product_id": product_id,
        "user_tier": 1,
        "comment": "e2e test calibration"
    }
    r = requests.post(f"{BASE}/feedback", json=feedback)
    assert r.status_code == 200
    assert r.json().get("success")


# ── /api/ai/usage ─────────────────────────────────────────────────────────────

def test_ai_usage():
    r = requests.get(f"{BASE}/ai/usage?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body.get("success")
    assert "aggregate" in body
    assert "recent" in body
    agg = body["aggregate"]
    assert "total_calls" in agg
    assert "total_cost_usd" in agg
