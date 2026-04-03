from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kkday_api import fetch_kkday_products
from skills.intent_matcher import IntentMatcher

app = FastAPI(title="Search Intent Verification API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize logic matcher with local destination dump path
matcher = IntentMatcher("/Users/kkday_borrow_f/Documents/workspace/Search_data/be2_destinations_dump")

class VerifyRequest(BaseModel):
    keyword: str
    env: str
    cookie: str
    count: int = 50

@app.post("/api/verify")
def verify_keyword(req: VerifyRequest):
    if req.env not in ["stage", "production"]:
        raise HTTPException(status_code=400, detail="env must be stage or production")
        
    products, total, total_page = fetch_kkday_products(req.keyword, req.env, req.cookie, req.count)
    
    results = []
    
    for i, p in enumerate(products):
        result = matcher.verify(p, req.keyword)
        tier = result["tier"]

        img = p.get("img_url") or p.get("image_url") or ""

        results.append({
            "rank": i + 1,
            "id": p.get("id", ""),
            "name": p.get("name", ""),
            "img_url": img,
            "url": p.get("url", ""),
            "main_cat_key": p.get("main_cat_key", ""),
            "main_cat_name": p.get("product_category", {}).get("main", ""),
            "destinations": [d.get("name") for d in p.get("destinations", [])],
            "tier": tier,
            "dest_match": result["dest_match"],
            "cat_match": result["cat_match"],
            "mismatch_reasons": result["mismatch_reasons"],
            "expected_dest": result["expected_dest"],
            "expected_cat": result["expected_cat"],
        })
        
    return {
        "success": True,
        "keyword": req.keyword,
        "env": req.env,
        "total": total,
        "results": results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
