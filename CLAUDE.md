# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A **Search Intent Verification Platform** for auditing KKDay e-commerce search results. It compares products returned by stage vs. production search APIs for a given keyword, judges whether each product matches the user's intent (rule-based + optional GPT-4o-mini), and tracks calibrations/metrics over time.

## Commands

### Start / Restart

```bash
./start.sh        # Starts backend (port 19426) + frontend (port 5888)
./restart.sh      # Kills existing processes on both ports, then starts
```

Manual start:
```bash
# Backend
cd backend && source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 19426

# Frontend
cd frontend && npm run dev
```

### Frontend

```bash
cd frontend
npm run dev        # Dev server (port 5888)
npm run build      # Production build → frontend/dist/
npm run preview    # Preview production build
npm run lint       # ESLint
```

### Testing

```bash
./run_tests.sh     # E2E suite (requires backend running on :19426)

# Run individual test files
cd backend && source venv/bin/activate
pytest test_intent_matcher.py -v          # Unit tests for IntentMatcher
pytest ../tests/test_e2e_api.py -v        # E2E API tests (14 cases, all endpoints)
```

## Architecture

```
Frontend (React + Vite, :5888)
    ↓ REST
Backend (FastAPI, :19426)
    ├── main.py              — all API endpoints
    ├── kkday_api.py         — KKDay product fetching (stage & prod), paginated 50/page
    ├── be2_api.py           — Be2Session: reusable requests wrapper with auto token refresh (importable)
    ├── fetch_be2_destination_hierarchy.py — CLI tool: crawl BE2 svc-geo destination tree → data/be2_destinations_dump/
    ├── batch_engine.py      — batch keyword processing, SQLite persistence
    └── skills/
        ├── intent_judger.py     — orchestrates judgment + calibration overrides
        ├── intent_matcher.py    — rule-based tier assignment (T1/T2/T3/Miss)
        ├── ai_agent.py          — GPT-4o-mini: parse keyword into intent metadata
        ├── data_sanitizer.py    — normalize product data, resolve destination codes
        ├── calibration_manager.py — read/write human corrections (feedback.json)
        └── metrics.py           — NDCG@K, Recall@K, mismatch rate, rank delta
```

### Judgment Pipeline (per keyword + products)

1. `kkday_api.py` fetches up to 300 products from both stage & production
2. Optionally, `ai_agent.py` parses the keyword into `{location, category, product}` via GPT-4o-mini
3. `intent_matcher.py` assigns each product a tier (1=exact, 2=related, 3=loose, 0=miss) based on destination/category rules and `unified_destinations.json`
4. `calibration_manager.py` overrides tiers where a human has manually corrected them (stored in `feedback.json`)
5. `metrics.py` computes quality scores
6. Results auto-saved to `history.db` (SQLite)

### Data Persistence

| File | Purpose |
|------|---------|
| `backend/data/history.db` | SQLite — `inspection_history` (batch runs) + `single_inspections` + `ai_usage_log` |
| `backend/data/keywords.json` | Keyword list for batch audit (with `ai_enabled` flag per keyword) |
| `backend/data/feedback.json` | Human calibrations: `{keyword: {product_id: {user_tier, comment}}}` |
| `backend/data/batch_state.json` | Batch progress/state (survives restarts) |
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
| `POST /api/compare` | Single keyword comparison (stage vs. prod) |
| `POST /api/feedback` | Save manual tier correction |
| `GET/POST /api/keywords` | Fetch or update keyword list |
| `POST /api/batch/run` | Start batch processing |
| `GET /api/batch/status` | Poll batch progress |
| `GET /api/batch/history` | Batch run history |
| `GET /api/guest-cookie` | Fetch fresh KKDay session cookie via Playwright |

### Frontend Structure

`frontend/src/App.jsx` is the root component (~300 lines after refactor). Extracted components live under `frontend/src/`:

```
src/
├── api.js                          — all fetch calls as named exports
├── utils/safeString.js             — safeString(), normalizeKw()
└── components/
    ├── icons/Icons.jsx             — all SVG icon components
    ├── ui/
    │   ├── Tooltip.jsx
    │   ├── TierBadge.jsx
    │   ├── NdcgGauge.jsx
    │   └── CompactMetricBar.jsx
    ├── ResultList.jsx              — product inspection list
    ├── CalibrationModal.jsx        — tier correction modal
    └── KeywordEditorModal.jsx      — batch keyword config modal
```

Two tabs:
- **單次巡檢** — single keyword search + inline calibration + single history dropdown
- **批次巡檢** — batch keyword management, batch run controls, inspection archives

## Environment

All environment variables are maintained in the **root `.env`** (single source of truth). Copy from `.env.example` to get started.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Required for AI intent parsing |
| `AI_MODEL_NAME` | `gpt-4o-mini` | OpenAI model to use |
| `AI_PRICE_INPUT_PER_1M` | `0.150` | Input token price (USD/1M) for cost tracking |
| `AI_PRICE_OUTPUT_PER_1M` | `0.600` | Output token price (USD/1M) for cost tracking |
| `DEST_DUMP_DIR` | `backend/data` | Path to destination data directory |
| `BACKEND_URL` | `http://localhost:19426` | Vite dev proxy target (local dev only) |
| `VITE_API_URL` | `/api` | API base path baked into frontend build |
| `VITE_BASE_URL` | `/` | Frontend base path (use `/explore_platform/` for EC2 subpath) |
| `BACKEND_PORT` | `19426` | Docker host port for backend |
| `FRONTEND_PORT` | `80` | Docker host port for frontend |
| `SECRET_SERVICE_URL` / `AUTOMATION_TOKEN` | — | KKDay internal QA service (Playwright cookie fetching) |
| `KKDAY_BE2_BEARER_TOKEN_FILE` | — | Path to file containing BE2 access JWT (re-read on every request; supports mid-run hot-swap) |
| `KKDAY_BE2_REFRESH_TOKEN_FILE` | — | Path to file containing BE2 refresh JWT (auto-rotated after each successful refresh) |
| `KKDAY_BE2_REFRESH_BEFORE_EXPIRY_SEC` | `120` | Proactively refresh access token this many seconds before expiry (0 = disabled) |
| `KKDAY_BE2_AUTH_COOKIE` | — | Browser Cookie string for auth requests (may be needed to bypass AU9997) |
| `KKDAY_BE2_GEO_BASE` | BE2 stage svc-geo URL | Override base URL for hierarchy-with-groups API |
| `KKDAY_BE2_REQUEST_DELAY` | `1.0` | Seconds to wait between each geo API request |
| `KKDAY_BE2_REQUEST_JITTER` | `0.5` | Extra random wait (0~jitter seconds) added to each delay |

AI parsing is optional and falls back gracefully if the key is missing or the call fails.

## Key Design Decisions

- **Batch runs are single-threaded** (sequential per keyword), not async — simplifies state management
- **Calibrations are additive** — feedback.json is append-only; re-running a search re-applies all saved corrections automatically
- **No TypeScript** — frontend is plain JavaScript/JSX
- **No DB migration system** — SQLite schema is created inline in `batch_engine.py` on startup

## Known Limitations & Gotchas

### Destination Matching Granularity
`intent_matcher.py` matches destinations using string containment against product API `destinations[]` field (district-level codes like 新宿, 銅鑼灣). Hierarchical lookups (e.g. 札幌 → 北海道 → 日本) are **not** supported natively. The matcher adds a fallback: if the searched location appears in the product's **name or description**, `dest_match` is still True. This handles common cases like "日本eSIM" products whose title contains 日本 but whose destination field lists only a district code.

### Calibration API Method Name
`CalibrationManager` exposes `save_feedback()` (not `add_feedback()`). `main.py` must call `calibration_manager.save_feedback(...)`.

### eslint-plugin-react-hooks v7
Version 7 adds `react-hooks/set-state-in-effect` and `react-hooks/immutability` rules that flag async setState in effects (a common pattern here). These are downgraded to `warn` in `eslint.config.js` — the pattern is intentional.
