import argparse
import sys
import os
import json
from skills.intent_judger import judger
from skills.calibration_manager import calibration_manager
from kkday_api import fetch_kkday_products

def run_judge(args):
    """
    CLI command to judge a keyword or a specific product.
    Usage: python -m backend.skills.cli judge --kw "esim" [--pid "12345"]
    """
    keyword = args.kw
    pid = args.pid
    ai_enabled = args.ai
    
    print(f"🔎 Analyzing Keyword: [{keyword}] (AI: {ai_enabled})")
    ai_meta = judger.get_ai_metadata(keyword, ai_enabled=ai_enabled)
    print(f"📊 AI Metadata: {json.dumps(ai_meta, indent=2, ensure_ascii=False)}")
    
    if pid:
        # Fetch actual products to find the target PID
        # For simplicity, we search and filter
        prods, _, _ = fetch_kkday_products(keyword, "production", "", 50)
        target = next((p for p in prods if str(p.get("oid") or p.get("product_id")) == str(pid)), None)
        
        if target:
            res = judger.judge_product(target, keyword, ai_meta)
            # Check calibration
            calib = calibration_manager.get_correction(keyword, pid)
            if calib:
                print(f"👨‍💻 FOUND CALIBRATION: {json.dumps(calib, indent=2, ensure_ascii=False)}")
                res["tier"] = calib["user_tier"]
                res["is_calibrated"] = True
            
            print(f"✅ Judgment for PID {pid}:")
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(f"❌ Product {pid} not found in top 50 results for '{keyword}'.")

def run_calibrate(args):
    """
    CLI command to manually calibrate a product.
    Usage: python -m backend.skills.cli calibrate --kw "esim" --pid "123" --tier 1 --comment "Fix"
    """
    success = calibration_manager.save_feedback(args.kw, args.pid, args.tier, args.comment)
    if success:
        print(f"✅ Calibration saved for {args.kw} | PID {args.pid} -> Tier {args.tier}")
    else:
        print("❌ Failed to save calibration.")

def main():
    parser = argparse.ArgumentParser(description="Search Intent Skill CLI Tool")
    subparsers = parser.add_subparsers(dest="command")
    
    # Judge
    p_judge = subparsers.add_parser("judge", help="Judge intent for keyword or product")
    p_judge.add_argument("--kw", required=True, help="Search keyword")
    p_judge.add_argument("--pid", help="Specific product ID to judge")
    p_judge.add_argument("--ai", action="store_true", help="Enable AI intent parsing")
    
    # Calibrate
    p_cal = subparsers.add_parser("calibrate", help="Manually calibrate a result")
    p_cal.add_argument("--kw", required=True, help="Keyword")
    p_cal.add_argument("--pid", required=True, help="Product ID")
    p_cal.add_argument("--tier", type=int, required=True, choices=[0,1,2,3], help="Human tier (0=Miss, 1=T1...)")
    p_cal.add_argument("--comment", required=True, help="Reasoning")
    
    args = parser.parse_args()
    
    if args.command == "judge":
        run_judge(args)
    elif args.command == "calibrate":
        run_calibrate(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
