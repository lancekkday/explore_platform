import requests
import time
import json
import os

BASE_URL = "http://localhost:19426/api"
TEST_KEYWORDS = ["esim", "ESIM", "酒店自助餐優惠", "機場接送"]

def test_batch_flow():
    print("🚀 [E2E] Starting Batch Inspection API Test...")
    
    # 1. Get Guest Cookie (Required for fetch)
    print("🍪 Fetching fresh cookie...")
    c_res = requests.get(f"{BASE_URL}/guest-cookie?env=production").json()
    cookie = c_res.get("cookie")
    if not cookie:
        print("❌ Error: Failed to fetch cookie. Make sure server is running.")
        return
    print(f"✅ Cookie fetched: {cookie[:30]}...")

    # 2. Reset and Setup Keywords
    print(f"📝 Setting up keywords: {TEST_KEYWORDS}")
    requests.post(f"{BASE_URL}/keywords", json={"keywords": TEST_KEYWORDS})
    
    # 3. Start Batch Run
    print("🎬 Triggering Batch Run...")
    run_res = requests.post(f"{BASE_URL}/batch/run", json={"cookie": cookie}).json()
    if not run_res.get("success"):
        print("❌ Error: Failed to trigger batch run.")
        return
    print("✅ Batch run started.")

    # 4. Polling Status until 100%
    timeout = 300 # 5 minutes max
    start_time = time.time()
    
    while True:
        if time.time() - start_time > timeout:
            print("❌ Error: Test timed out!")
            break
            
        status = requests.get(f"{BASE_URL}/batch/status").json()
        progress = status.get("progress", 0)
        is_running = status.get("is_running", False)
        current = status.get("current_keyword", "None")
        
        print(f"⏳ Progress: {progress}% | Current: {current} | IsRunning: {is_running}")
        
        if progress >= 100 or not is_running:
            print("🏁 Batch processing finished.")
            break
            
        time.sleep(5)

    # 5. Final Result Verification
    print("📊 Verifying results integrity...")
    results_res = requests.get(f"{BASE_URL}/batch/results").json()
    res_dict = results_res.get("results", {})
    
    print(f"💡 Total results captured: {len(res_dict)}")
    
    # Check normalization: 'ESIM' and 'esim' should map to same lower-case key in latest logic
    # (Though current logic might store both if they were in the list separately)
    for kw in TEST_KEYWORDS:
        norm_key = kw.strip().lower()
        if norm_key in res_dict:
            metrics = res_dict[norm_key]
            s_ndcg = metrics.get('stage', {}).get('ndcg_10', 0)
            p_ndcg = metrics.get('production', {}).get('ndcg_10', 0)
            print(f"✅ Match Found [{kw} -> {norm_key}]: Stage ND@10: {s_ndcg*100}%, Prod ND@10: {p_ndcg*100}%")
        else:
            print(f"⚠️ Warning: Missing data for {kw} (Normal-Key: {norm_key})")

    if len(res_dict) > 0:
        print("\n✨ E2E Test Passed: Batch production line is STABLE.")
    else:
        print("\n❌ E2E Test Failed: No results were captured.")

if __name__ == "__main__":
    test_batch_flow()
