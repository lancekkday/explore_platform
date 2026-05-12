# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A **Search Audit Platform (搜尋巡檢平台)** for auditing KKDay e-commerce search results. It supports:

- **Unified search inspection** — single keyword A/B comparison across algorithm versions (via `test_exp` parameter)
- **Baseline monitoring** — checks whether "守門商品" (guardian products) from precise/broad baseline CSVs maintain their expected rankings
- **Tier judgment** — rule-based + optional GPT-4o-mini classification of each product's relevance to the search intent
- **Batch inspection** — automated multi-keyword audit with scheduling support
- **CSV export** — export inspection results for offline review

## Commands

### Start / Restart

```bash
./start.sh        # Starts backend (port 8000) + frontend (port 5173)
./restart.sh      # Kills existing processes on both ports, then starts
```

Manual start:
```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev
```

### Frontend

```bash
cd frontend
npm run dev        # Dev server (port 5173)
npm run build      # Production build → frontend/dist/
npm run preview    # Preview production build
npm run lint       # ESLint
```

### Testing

```bash
./run_tests.sh     # E2E suite (requires backend running on :8000)

# Run individual test files
cd backend && source venv/bin/activate
pytest test_intent_matcher.py -v          # Unit tests for IntentMatcher
pytest ../tests/test_e2e_api.py -v        # E2E API tests (14 cases, all endpoints)
```

## Architecture

```
Frontend (React + Vite, :5173)
    ↓ REST
Backend (FastAPI, :8000)
    ├── main.py              — all API endpoints (compare, unified-search, ab-check, batch, etc.)
    ├── kkday_api.py         — KKDay product fetching (stage & prod), paginated 50/page, test_exp for AB
    ├── ab_check.py          — AB version check engine: precise/broad baseline comparison
    ├── baseline_service.py  — singleton: loads baseline CSVs into memory, provides annotation helpers + reload()
    ├── baseline_version_manager.py — versioned baseline snapshots (timestamp dirs, symlink switching, archive)
    ├── be2_api.py           — Be2Session: reusable requests wrapper with auto token refresh (importable)
    ├── fetch_be2_destination_hierarchy.py — CLI tool: crawl BE2 svc-geo destination tree → data/be2_destinations_dump/
    ├── batch_engine.py      — batch keyword processing (supports AB mode), SQLite persistence
    └── skills/
        ├── intent_judger.py     — orchestrates judgment + calibration overrides
        ├── intent_matcher.py    — rule-based tier assignment (T1/T2/T3/Miss), POI detection
        ├── ai_agent.py          — GPT-4o-mini: parse keyword into intent metadata
        ├── data_sanitizer.py    — normalize product data, resolve destination codes
        ├── calibration_manager.py — read/write human corrections (feedback.json)
        ├── synonym_service.py   — bidirectional synonym table (synonyms.json), AI auto-accumulation
        └── metrics.py           — NDCG@K, Recall@K, mismatch rate, rank delta
```

### Unified Search Pipeline (per keyword)

1. `kkday_api.py` fetches products via v3 search API with `test_exp=version_a` (and optionally `test_exp=version_b`)
2. Optionally, `ai_agent.py` parses the keyword into `{location, category, product}` via GPT-4o-mini
3. `intent_matcher.py` assigns each product a tier (1=exact, 2=related, 3=loose, 0=miss) based on destination/category rules and `unified_destinations.json`; POI keywords (e.g. 環球影城) use a dedicated Route E that skips destination matching
4. `baseline_service.py` annotates products with baseline tags (⭐ precise / 📊 broad) and profit ranks
5. `main.py._compute_ab_comparison()` compares A vs B rankings of baseline products, generates alerts
6. `calibration_manager.py` overrides tiers where a human has manually corrected them (stored in `feedback.json`)
7. `metrics.py` computes quality scores
8. Results auto-saved to `history.db` (SQLite)

### AB Version Check (`ab_check.py`)

Separate from unified search — a standalone check that runs all baseline keywords (precise + broad CSVs) against two algorithm versions to detect ranking regressions. Uses `ThreadPoolExecutor` with request-local cache for thread safety.

### Data Persistence

| File | Purpose |
|------|---------|
| `backend/data/history.db` | SQLite — `inspection_history` (batch runs) + `single_inspections` + `ai_usage_log` |
| `backend/data/keywords.json` | Keyword list for batch audit (with `ai_enabled` flag per keyword) |
| `backend/data/feedback.json` | Human calibrations: `{keyword: {product_id: {user_tier, comment}}}` |
| `backend/data/batch_state.json` | Batch progress/state (survives restarts) |
| `handoff/data/search_keyword_precise.csv` | Baseline precise keywords — Top1/Top2 prod_mid per query (symlink to active version) |
| `handoff/data/search_keyword_broad.csv` | Baseline broad keywords — profit_rank 1-10 per query (symlink to active version) |
| `handoff/data/versions/` | Versioned baseline snapshots (timestamp dirs with CSV + meta.json, max 5 active) |
| `backend/data/synonyms.json` | Synonym accumulation table — bidirectional, auto-populated by AI |
| `backend/data/unified_destinations.json` | Destination name ↔ code mapping (used by `intent_matcher.py`) |
| `backend/data/be2_destinations_dump/` | Raw destination JSONL dump — source for rebuilding `unified_destinations.json` |

#### Destination Data Notes

`intent_matcher.py` loads `unified_destinations.json` from the **parent directory** of `DEST_DUMP_DIR`:

```
backend/data/
├── unified_destinations.json        ← loaded at runtime by intent_matcher
└── be2_destinations_dump/           ← raw dump, used to rebuild unified_destinations.json
    └── <UTC timestamp>/             ← one folder per crawl run
        ├── meta.json
        ├── destinations.jsonl
        └── destinations.sqlite
```

`DEST_DUMP_DIR` defaults to `backend/data`. Override via env var for Docker or other environments:
```env
DEST_DUMP_DIR=/app/data   # Docker default
```

#### Re-crawling BE2 Destination Hierarchy

Use `fetch_be2_destination_hierarchy.py` to pull the full destination tree from BE2 stage (`svc-geo`). Output lands in `backend/data/be2_destinations_dump/<UTC timestamp>/`.

**Prerequisites — tokens (never commit these):**
```bash
# access JWT — read from file on every request (supports mid-run hot-swap)
export KKDAY_BE2_BEARER_TOKEN_FILE="$HOME/.kkday_be2_bearer"
printf '%s\n' 'eyJ...' > "$KKDAY_BE2_BEARER_TOKEN_FILE" && chmod 600 "$KKDAY_BE2_BEARER_TOKEN_FILE"

# refresh JWT (optional but recommended for long runs — auto-rotates on each refresh)
export KKDAY_BE2_REFRESH_TOKEN_FILE="$HOME/.kkday_be2_refresh"
printf '%s\n' 'eyJ...' > "$KKDAY_BE2_REFRESH_TOKEN_FILE" && chmod 600 "$KKDAY_BE2_REFRESH_TOKEN_FILE"
```

**Run:**
```bash
cd backend && source venv/bin/activate

# Full crawl — by country, into data/be2_destinations_dump/<timestamp>/
python fetch_be2_destination_hierarchy.py --by-country

# Resume an interrupted run (same output-dir)
python fetch_be2_destination_hierarchy.py --by-country --resume \
  --output-dir data/be2_destinations_dump/<previous-timestamp>

# Crawl only specific countries
python fetch_be2_destination_hierarchy.py --by-country --only-iso TW,JP

# Adjust throttle (default: 1s delay + 0.5s jitter)
python fetch_be2_destination_hierarchy.py --by-country --delay 0.5 --jitter 0.3
```

Each completed run produces three files per country folder:
- `meta.json` — crawl metadata and counts
- `destinations.jsonl` — one destination per line (code, name, isoCountryCode, tier, status, hasHierarchy, parentCode)
- `destinations.sqlite` — same data as SQLite with indexes on parent / tier / iso

**Programmatic use (`be2_api.py`):**
```python
from be2_api import Be2Session

with Be2Session() as s:
    resp = s.get(
        "https://api-gateway.stage.kkday.com/svc-geo/api/admin/destinations/hierarchy-with-groups",
        params={"lang": "zh-tw", "parentDestinationCode": ""},
    )
    data = resp.json()
```
`Be2Session` handles proactive refresh (before expiry) and reactive refresh (on 401/403) automatically. Both tokens are rotated back to their files after each successful refresh.

### Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/unified-search` | Main inspection: keyword search with AB comparison + baseline annotations |
| `POST /api/compare` | Legacy single keyword comparison (stage vs. prod) |
| `POST /api/ab-check` | Standalone AB baseline check (all keywords, precise + broad) |
| `POST /api/explain` | AI explanation for a product's tier/mismatch |
| `POST /api/feedback` | Save manual tier correction (+ optional synonyms) |
| `GET/POST /api/keywords` | Fetch or update keyword list |
| `GET /api/baseline/keywords` | List all keywords from baseline CSVs |
| `POST /api/baseline/upload` | Upload baseline CSV or HTML report (auto-versioned) |
| `GET /api/baseline/versions` | List all baseline versions |
| `POST /api/baseline/rollback` | Switch active baseline to a specific version |
| `DELETE /api/baseline/versions/:ts` | Archive (soft-delete) a baseline version |
| `POST /api/baseline/reload` | Manually reload baseline CSVs into memory |
| `POST /api/batch/run` | Start batch processing (supports `version_a`/`version_b` for AB) |
| `POST /api/batch/stop` | Stop running batch |
| `GET /api/batch/status` | Poll batch progress |
| `GET /api/batch/results` | Current batch results |
| `GET /api/batch/history` | Batch run history |
| `GET /api/batch/history/:id` | Batch run detail |
| `GET/POST/PATCH/DELETE /api/batch/schedule` | Scheduled batch CRUD |
| `GET /api/single/history` | Single inspection history |
| `GET /api/guest-cookie` | Fetch fresh KKDay session cookie via Playwright |

### Frontend Structure

`frontend/src/App.jsx` is the root component. Unified single-page layout (no tabs). Extracted components:

```
src/
├── api.js                          — all fetch calls as named exports
├── utils/safeString.js             — safeString(), normalizeKw()
└── components/
    ├── icons/Icons.jsx             — all SVG icon components
    ├── ui/
    │   ├── Tooltip.jsx
    │   ├── TierBadge.jsx           — tier badges with hover tooltips (T1/T2/T3/MISS)
    │   ├── NdcgGauge.jsx
    │   └── CompactMetricBar.jsx
    ├── UnifiedSearchBar.jsx        — search bar with AB version inputs, filter & export buttons
    ├── AnnotatedResultList.jsx     — product list with baseline annotations & product hyperlinks
    ├── ABComparisonSummary.jsx     — A/B baseline ranking comparison summary
    ├── BaselineAlertBar.jsx        — alerts for missing/dropped baseline products
    ├── SettingsPanel.jsx           — cookie, search API, AB toggle, AI toggle, baseline upload/version management
    ├── BatchPanel.jsx              — collapsible batch run controls & results
    ├── ResultList.jsx              — legacy product inspection list
    ├── CalibrationModal.jsx        — tier correction modal
    └── KeywordEditorModal.jsx      — batch keyword config modal
```

Layout: search bar at top → results (Version A left, Version B right) → collapsible batch panel at bottom.

## Environment

All environment variables are maintained in the **root `.env`** (single source of truth). Copy from `.env.example` to get started.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Required for AI intent parsing |
| `AI_MODEL_NAME` | `gpt-4o-mini` | OpenAI model to use |
| `AI_PRICE_INPUT_PER_1M` | `0.150` | Input token price (USD/1M) for cost tracking |
| `AI_PRICE_OUTPUT_PER_1M` | `0.600` | Output token price (USD/1M) for cost tracking |
| `DEST_DUMP_DIR` | `backend/data` | Path to destination data directory |
| `BACKEND_URL` | `http://localhost:8000` | Vite dev proxy target (local dev only) |
| `VITE_API_URL` | `/api` | API base path baked into frontend build |
| `VITE_BASE_URL` | `/` | Frontend base path (use `/explore_platform/` for EC2 subpath) |
| `BACKEND_PORT` | `8000` | Docker host port for backend |
| `FRONTEND_PORT` | `80` | Docker host port for frontend |
| `SECRET_SERVICE_URL` / `AUTOMATION_TOKEN` | — | KKDay internal QA service (Playwright cookie fetching) |
| `KKDAY_BE2_BEARER_TOKEN_FILE` | — | Path to file containing BE2 access JWT (re-read on every request; supports mid-run hot-swap) |
| `KKDAY_BE2_REFRESH_TOKEN_FILE` | — | Path to file containing BE2 refresh JWT (auto-rotated after each successful refresh) |
| `KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC` | `120` | Proactively refresh access token this many seconds before expiry (0 = disabled) |
| `KKDAY_BE2_AUTH_COOKIE` | — | Browser Cookie string for auth requests (may be needed to bypass AU9997) |
| `KKDAY_BE2_GEO_BASE` | BE2 stage svc-geo URL | Override base URL for hierarchy-with-groups API |
| `KKDAY_BE2_REQUEST_DELAY` | `1.0` | Seconds to wait between each geo API request |
| `KKDAY_BE2_REQUEST_JITTER` | `0.5` | Extra random wait (0~jitter seconds) added to each delay |
| `KKDAY_SEARCH_AUTH_KEY` | — | Auth key for KKDay search API v3 |
| `KKDAY_SEARCH_DEVICE_ID` | — | Device ID header for search API v3 |
| `KKDAY_SEARCH_COOKIE` | — | Fallback cookie for search API (overridden by guest-cookie at runtime) |

AI parsing is optional and falls back gracefully if the key is missing or the call fails.

## Key Design Decisions

- **AB mode default on** — `enableAB=true` by default (Version A=0, B=1); can be toggled off in SettingsPanel
- **`test_exp` parameter** — KKDay search API v3 uses `test_exp` to select algorithm version (0=control, 1+=experimental)
- **Baseline service singleton** — `baseline_service.py` loads CSVs once into memory; avoids re-reading on every request
- **Request-local cache** — `ab_check.py` creates a new cache dict per `run_ab_check()` call (not module-level) for thread safety
- **Batch runs are single-threaded** (sequential per keyword), not async — simplifies state management
- **Calibrations are additive** — feedback.json is append-only; re-running a search re-applies all saved corrections automatically
- **No TypeScript** — frontend is plain JavaScript/JSX
- **No DB migration system** — SQLite schema is created inline in `batch_engine.py` on startup
- **Product links point to stage** — `https://www.stage.kkday.com/zh-tw/product/{prod_mid}` since API uses stage environment

## Known Limitations & Gotchas

### Destination Matching Granularity
`intent_matcher.py` matches destinations using string containment against product API `destinations[]` field (district-level codes like 新宿, 銅鑼灣). Hierarchical lookups (e.g. 札幌 → 北海道 → 日本) are **not** supported natively. The matcher adds a fallback: if the searched location appears in the product's **name or description**, `dest_match` is still True. This handles common cases like "日本eSIM" products whose title contains 日本 but whose destination field lists only a district code.

### POI Keyword Handling
Keywords like "環球影城" or "迪士尼" are attractions (POI), not geographic locations. `intent_matcher.py` uses `_is_known_geo()` to distinguish — if a keyword is NOT a recognized country/city/destination, it routes to `_verify_poi_keyword()` (Route E) which skips destination matching and instead checks if the keyword appears in the product title/description.

### Calibration API Method Name
`CalibrationManager` exposes `save_feedback()` (not `add_feedback()`). `main.py` must call `calibration_manager.save_feedback(...)`.

### eslint-plugin-react-hooks v7
Version 7 adds `react-hooks/set-state-in-effect` and `react-hooks/immutability` rules that flag async setState in effects (a common pattern here). These are downgraded to `warn` in `eslint.config.js` — the pattern is intentional.
