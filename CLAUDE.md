# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A **Search Intent Verification Platform** for auditing KKDay e-commerce search results. It compares products returned by stage vs. production search APIs for a given keyword, judges whether each product matches the user's intent (rule-based + optional GPT-4o-mini), and tracks calibrations/metrics over time.

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
pytest ../tests/e2e_api_test.py -v        # E2E API tests
```

## Architecture

```
Frontend (React + Vite, :5173)
    ↓ REST
Backend (FastAPI, :8000)
    ├── main.py              — all API endpoints
    ├── kkday_api.py         — KKDay product fetching (stage & prod), paginated 50/page
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
| `backend/data/history.db` | SQLite — `inspection_history` (batch runs) + `single_inspections` |
| `backend/data/keywords.json` | Keyword list for batch audit (with `ai_enabled` flag per keyword) |
| `backend/data/feedback.json` | Human calibrations: `{keyword: {product_id: {user_tier, comment}}}` |
| `backend/data/batch_state.json` | Batch progress/state (survives restarts) |
| `backend/data/unified_destinations.json` | Destination name ↔ code mapping |

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

`frontend/src/App.jsx` is a single ~1500-line component with three tabs:
- **Discovery** — single keyword search + inline calibration
- **Audit** — batch keyword management + batch run controls
- **Results** — batch history viewer + drilldown per keyword

## Environment

Backend reads `backend/.env` for:
- `OPENAI_API_KEY` — required for AI-powered intent parsing (`ai_enabled: true` keywords)
- `SECRET_SERVICE_URL` / `AUTOMATION_TOKEN` — KKDay internal QA service (Playwright cookie fetching)

AI parsing is optional and falls back gracefully if the key is missing or the call fails.

## Key Design Decisions

- **Batch runs are single-threaded** (sequential per keyword), not async — simplifies state management
- **Calibrations are additive** — feedback.json is append-only; re-running a search re-applies all saved corrections automatically
- **No TypeScript** — frontend is plain JavaScript/JSX
- **No DB migration system** — SQLite schema is created inline in `batch_engine.py` on startup
