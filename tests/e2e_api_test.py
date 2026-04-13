import os
import requests
import pytest
import time

BASE_URL = os.environ.get("PYTEST_BASE_URL", "http://localhost:19426")

@pytest.fixture(scope="session")
def shared_cookie():
    """獲取一個有效的 KKDay Guest Cookie 以供測試使用"""
    resp = requests.get(f"{BASE_URL}/api/guest-cookie?env=production")
    assert resp.status_code == 200
    data = resp.json()
    assert "cookie" in data
    return data["cookie"]

def test_health_check():
    """基本健康檢查"""
    # 這裡我們假設 FastAPI 啟動後根目錄或某個路徑有響應
    # 既然沒有定義 root, 我們測一個現有的 API
    resp = requests.get(f"{BASE_URL}/api/keywords")
    assert resp.status_code == 200
    assert "keywords" in resp.json()

def test_semantic_search_esim(shared_cookie):
    """測試 AI 驅動的語意搜尋 (esim)"""
    payload = {
        "keyword": "esim",
        "cookie": shared_cookie,
        "count": 10,
        "ai_enabled": True
    }
    resp = requests.post(f"{BASE_URL}/api/compare", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["success"] is True
    # 驗證 Stage/Production 是否都有結果
    assert len(data["stage"]["results"]) > 0
    assert len(data["production"]["results"]) > 0

def test_calibration_loop(shared_cookie):
    """測試人工校正閉環流程"""
    keyword = "東京"
    
    # 1. 執行初始搜尋
    payload = {
        "keyword": keyword,
        "cookie": shared_cookie,
        "count": 5,
        "ai_enabled": False
    }
    resp = requests.post(f"{BASE_URL}/api/compare", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    stage_res = data["stage"]["results"]
    if not stage_res:
        pytest.skip("No products found for test keyword")
        
    target_p = stage_res[0]
    pid = target_p["id"]
    original_tier = target_p["tier"]
    
    # 2. 提交校正
    new_tier = 1 if original_tier != 1 else 2
    feedback_payload = {
        "keyword": keyword,
        "product_id": pid,
        "user_tier": new_tier,
        "comment": "E2E Automated Test Correction"
    }
    f_resp = requests.post(f"{BASE_URL}/api/feedback", json=feedback_payload)
    assert f_resp.status_code == 200
    assert f_resp.json()["success"] is True
    
    # 3. 再次搜尋，驗證校正生效
    resp_again = requests.post(f"{BASE_URL}/api/compare", json=payload)
    assert resp_again.status_code == 200
    updated_results = resp_again.json()["stage"]["results"]
    
    # 找到同一個 PID
    updated_p = next((p for p in updated_results if p["id"] == pid), None)
    assert updated_p is not None
    assert updated_p["tier"] == new_tier
    assert updated_p["is_calibrated"] is True
    assert "人工校正" in updated_p["mismatch_reasons"][0]

def test_batch_status():
    """測試批量巡檢狀態介面"""
    resp = requests.get(f"{BASE_URL}/api/batch/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_running" in data
    assert "progress" in data
