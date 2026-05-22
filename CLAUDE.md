# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A **Search Audit Platform (搜尋巡檢平台)** for auditing KKDay e-commerce search results. It supports:

- **Unified search inspection** — single keyword A/B comparison across algorithm versions (via `test_exp` parameter); search state survives SPA route changes (back from `/batch` keeps last keyword + results)
- **Baseline monitoring** — checks whether "守門商品" (guardian products) from precise/broad baseline CSVs maintain their expected rankings
- **Tier judgment** — rule-based + optional GPT-4o-mini classification of each product's relevance to the search intent
- **Batch inspection (async + checkpointed)** — independent `/batch` route runs all baseline keywords through an async sqlite-checkpointed runner; supports cancel mid-flight, resume from where the previous run stopped, and 50-row history. Polling timer lives in AppContext so the run keeps progressing while the user is on `/`
- **BigQuery baseline pipeline** — daily APScheduler cron + manual UI button pulls baseline from `kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_{precise,broad}` views; status banner surfaces failures or row-count drops
- **CSV export** — export inspection results for offline review

Companion docs:
- [Confluence — 功能與判斷邏輯說明](https://kkday.atlassian.net/wiki/spaces/QS/pages/1969225751) — PM/QA-facing feature & logic spec
- [README.md](./README.md) — short overview + deploy quick-start

## Commands

### Start / Restart

```bash
./start.sh        # Starts backend (port 19426) + frontend (port 5888)
./restart.sh      # Kills existing processes on both ports, then starts
```

Local dev URL: <http://localhost:5888/explore_platform/> (note `VITE_BASE_URL` subpath).

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

### Manual BigQuery baseline fetch (CLI)

```bash
cd backend && source venv/bin/activate
python ../scripts/fetch_baseline_bq.py             # writes CSV to handoff/data/
python ../scripts/fetch_baseline_bq.py --dry-run   # print SQL only
python ../scripts/fetch_baseline_bq.py --version   # write via BaselineVersionManager (auto-activate)
```

Same code path is invoked by `POST /api/baseline/refresh-from-bq` and the daily cron job.

## Architecture

```
Frontend (React + Vite + React Router, :5888)
    ↓ REST
Backend (FastAPI + APScheduler, :19426)
    ├── main.py              — all API endpoints (compare, unified-search, ab-check, batch, baseline, etc.)
    ├── kkday_api.py         — KKDay product fetching (stage & prod), paginated 50/page, test_exp for AB
    ├── ab_check.py          — AB version check engine: per-query helpers (process_one_{precise,broad}_query) consumed by both legacy sync run_ab_check() and the new runner
    ├── ab_check_runner.py   — NEW (PR #27): async + sqlite-checkpointed batch runner with cancel/resume/sweep; primary entry for /batch UI
    ├── baseline_service.py  — singleton: loads baseline CSVs into memory, provides annotation helpers + reload()
    ├── baseline_version_manager.py — versioned baseline snapshots (timestamp dirs, symlink switching, archive; MAX_VERSIONS=14)
    ├── baseline_bq_fetcher.py — shared core: query BQ views → DataFrame → CSV strings + guardrail; consumed by CLI / cron / API
    ├── baseline_scheduler.py — daily APScheduler cron (default 07:00 Asia/Taipei) + JSON config persistence (backend/data/baseline_cron.json)
    ├── stage_product_check.py — stage HEAD probe (TTL cache, singleton) — disambiguates "missing" baseline rows into removed / out_of_window / check_failed
    ├── be2_api.py           — Be2Session: reusable requests wrapper with auto token refresh (importable)
    ├── fetch_be2_destination_hierarchy.py — CLI tool: crawl BE2 svc-geo destination tree → data/be2_destinations_dump/
    ├── batch_engine.py      — batch keyword processing (supports AB mode), SQLite persistence (still wired but not surfaced in new UI; kept for backwards compat)
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

Separate from unified search — a standalone check that runs all baseline keywords (precise + broad CSVs) against two algorithm versions to detect ranking regressions. Exposes two public per-query helpers (`process_one_precise_query` / `process_one_broad_query`) shared by both the legacy synchronous `run_ab_check()` (ThreadPool, 10 workers) and the new `ab_check_runner.py` (sequential per run).

### Async AB-check Runner (`ab_check_runner.py`) — PR #27

Primary entry for batch baseline AB checks. Replaces the synchronous `/api/ab-check` flow (which was hitting 3-5 min runtime and triggering SIT proxy 504s; the old endpoint stays for one release with a deprecation log).

- **Persistence** — runs + per-query checkpoints in two sqlite tables (`ab_check_runs`, `ab_check_checkpoints`) inside the existing `history.db`. WAL mode enabled so polling readers don't serialize against the worker's writes.
- **Threading model** — each `start_run()` spawns a daemon thread; precise + broad can run in parallel; same type runs serially (UI in-flight guard). The worker itself is single-threaded inside one run (finer cancel granularity, lower 504 risk than the legacy ThreadPool path).
- **Cancel** — `_cancel_flags` registry (in-memory `threading.Event`). Worker checks the flag at each iteration boundary; cancel returns immediately, status flips at the next boundary.
- **Resume** — `_copy_parent_done_rows()` copies the parent run's `status='ok'` checkpoints (alerts_json preserved) into the new run, then worker skips those idx. Validates parent type / version_a / version_b / baseline_version / per-idx query text before copying — any drift falls back to a clean re-run (avoids misattributing alerts).
- **Startup sweep** — `sweep_interrupted_runs()` at FastAPI `startup_event`:
  - Marks any DB `status='running'` runs as `'interrupted'` (worker died with the previous process) + writes `finished_at`
  - Resets orphan `ab_check_checkpoints` rows from `'running'` to `'pending'` so the history detail view doesn't show phantom "executing" rows
- **Phantom recovery** — `force_interrupt_run(run_id)` lets `/api/ab-check/cancel` unstick a run whose DB says `running` but no live in-process worker exists (process restart, OOM kill). Returns `{ok: true}` once flipped to `interrupted`.

### Frontend AB-check state (`AppContext.jsx`)

Runs are not local to the panel — they live at provider level so polling survives SPA route changes:

- `preciseRun` / `broadRun` — `{ runId, status, total, doneCount, rowsMap: Map<idx, row>, sinceIdx, limitN, summary, errorMsg, error }`
- `pollTimers.current` ref holds `setInterval` handles per type; `runStateRef.current` mirror is read inside `pollRunOnce` to avoid stale-closure / StrictMode double-fire issues
- `since_idx` advances to the first non-terminal row's idx (sequential-worker assumption) so polling only re-fetches unfinished rows
- Each tick auto-stops the timer when status enters {`done`, `failed`, `cancelled`, `interrupted`}
- `api.js` wraps every fetch in `jsonOrThrow` — non-JSON proxy errors (SIT 504 HTML body) throw a typed `NetworkError` instead of `SyntaxError: Unexpected token '<'`
- `getABCheckStatus()` uses `AbortController` with 8 s timeout so slow status responses don't pile up behind the 2 s `setInterval`

### BigQuery Baseline Pipeline (`baseline_bq_fetcher.py` + `baseline_scheduler.py`)

Replaces the old HTML-report-upload flow as the primary baseline source.

- `baseline_bq_fetcher.fetch_from_bq()` queries the two SIT views (`kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_{precise,broad}`) using the SQL files in `scripts/sql/`. Returns a `FetchResult` with CSV strings + row counts.
- `baseline_bq_fetcher.apply_and_activate(result)` writes via `BaselineVersionManager.create_version()` (auto-versioned + auto-activated). Guardrail: if new row count `< previous × 50%` or `0`, the version is still activated but `warnings` is populated so the UI banner can surface the anomaly.
- `baseline_scheduler._run_fetch()` glues the two together, then calls `baseline_service.reload()` so in-memory CSVs pick up the new version without restart. Persists `last_run` to `backend/data/baseline_cron.json` (read by `GET /api/baseline/source-status`).
- The same `_run_fetch` is invoked by daily cron and `POST /api/baseline/refresh-from-bq` (manual). CLI (`scripts/fetch_baseline_bq.py`) imports the same fetcher.

Underlying view rebuild SQL is owned by RD (Joyce 2026-05-08 v4 spec); `scripts/sql/baseline_*.sql` only `SELECT` from those views + `WHERE LOWER(market)='tw'`.

### Data Persistence

| File | Purpose |
|------|---------|
| `backend/data/history.db` | SQLite (WAL mode) — `inspection_history` + `single_inspections` + `ai_usage_log` + **NEW: `ab_check_runs` + `ab_check_checkpoints`** (gitignored — runtime state) |
| `backend/data/baseline_cron.json` | BQ cron config + `last_run` outcome (gitignored — runtime state, read by source-status banner) |
| `backend/data/keywords.json` | Legacy batch keyword list (no longer wired into new BatchPage; backend `batch_engine` retained for compat) |
| `backend/data/feedback.json` | Human calibrations: `{keyword: {product_id: {user_tier, comment}}}` |
| `backend/data/batch_state.json` | Batch progress/state (survives restarts) |
| `handoff/data/search_keyword_precise.csv` | Baseline precise keywords — Top1/Top2 prod_mid per query (symlink to active version) |
| `handoff/data/search_keyword_broad.csv` | Baseline broad keywords — profit_rank 1-10 per query (symlink to active version) |
| `handoff/data/versions/` | Versioned baseline snapshots (timestamp dirs with CSV + meta.json, **max 14 active** ≈ 2 weeks of daily cron) |
| `handoff/_secrets/` | (gitignored) deploy-only directory for SA JSON / API keys; mounted into Docker container via `./handoff:/app/handoff` |
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
| `POST /api/ab-check` | **(Deprecated — kept one release)** Legacy synchronous AB baseline check. Logs a deprecation warning per call; UI now uses the runner endpoints below |
| `POST /api/ab-check/start` | **NEW** — Kick off async AB-check (body: `{type, version_a, version_b, cookie, limit?, resume_run_id?}`); returns `{run_id, status, total_queries}` immediately |
| `GET /api/ab-check/status?run_id=&since_idx=` | **NEW** — Live progress; returns `{run, progress:{done,total,running_idx}, rows:[…]}`. `since_idx` lets polling fetch only non-terminal rows |
| `POST /api/ab-check/cancel` | **NEW** — Request cancel; for phantom runs (DB=running, no worker) auto-flips to `interrupted` so UI recovers |
| `GET /api/ab-check/history?type=&limit=50` | **NEW** — Recent runs (filterable by `precise`/`broad`) |
| `GET /api/ab-check/history/{run_id}` | **NEW** — Single run detail with checkpoint rows |
| `POST /api/explain` | AI explanation for a product's tier/mismatch |
| `POST /api/feedback` | Save manual tier correction (+ optional synonyms) |
| `GET/POST /api/keywords` | Fetch or update keyword list |
| `GET /api/baseline/keywords` | List all keywords from baseline CSVs |
| `POST /api/baseline/upload` | Upload baseline CSV (Plan B; HTML upload deprecated and now rejected with 400) |
| `GET /api/baseline/versions` | List all baseline versions |
| `POST /api/baseline/rollback` | Switch active baseline to a specific version |
| `DELETE /api/baseline/versions/:ts` | Archive (soft-delete) a baseline version |
| `POST /api/baseline/reload` | Manually reload baseline CSVs into memory |
| `POST /api/baseline/refresh-from-bq` | Manually trigger BQ fetch + version + activate + reload (does NOT wait for daily cron) |
| `GET /api/baseline/source-status` | Last BQ fetch outcome + active version meta (drives UI status banner) |
| `GET /api/baseline/cron-schedule` | Read current cron config (`enabled`, `hour`, `minute`) |
| `PATCH /api/baseline/cron-schedule` | Update cron time / enabled state at runtime (re-registers APScheduler job) |
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

`frontend/src/App.jsx` wires `BrowserRouter` + `AppContextProvider` + `ErrorBoundary`. Two routes split into separate pages:

```
src/
├── App.jsx                         — Router, ErrorBoundary, global Layout (AppHeader + BaselineStatusBanner + modals)
├── api.js                          — all fetch calls; `jsonOrThrow` guard turns non-JSON proxy errors into typed NetworkError; getABCheckStatus has 8s AbortController timeout
├── context/AppContext.jsx          — shared state including `preciseRun` / `broadRun` polling state + cancel-flag refs + `homeKeyword` / `homeFilterMode` / `homeResults` (HomePage state survives route changes)
├── utils/safeString.js             — safeString(), normalizeKw()
├── pages/
│   ├── HomePage.jsx                — 巡檢 route /  (single keyword + A/B columns); reads/writes home search state via context
│   └── BatchPage.jsx               — 批次 route /batch (3-tab shell only)
└── components/
    ├── icons/Icons.jsx
    ├── ui/
    │   ├── Tooltip.jsx
    │   ├── TierBadge.jsx           — tier pill T1/T2/T3/MISS (px-1.5 py-0.5 text-[9px])
    │   ├── NdcgGauge.jsx
    │   └── CompactMetricBar.jsx
    ├── AppHeader.jsx               — sticky top bar (title + 巡檢/批次 nav + cookie status; in-flight pulse dot reads preciseRun/broadRun status)
    ├── BaselineStatusBanner.jsx    — red/amber banner under header, polls /api/baseline/source-status every 60s; dismissible per last_run.ts
    ├── UnifiedSearchBar.jsx        — search bar with version inputs + filter + export
    ├── AnnotatedResultList.jsx     — product row (h locked to min-h-[42px]; hover surfaces AI/校正 inline in meta row); query click in batch view navigates to / with ?keyword=
    ├── ABComparisonSummary.jsx
    ├── BaselineAlertBar.jsx
    ├── ABCheckRunPanel.jsx         — NEW (PR #27): precise / broad batch tab content. limit input + A/B inline editor + 啟動/取消/重新啟動 (with confirm dialog) + live progress + per-row dot-status table + severity hover popup + click query → jump to /?keyword=&filter=diff
    ├── ABCheckHistoryTable.jsx     — NEW (PR #27): 歷史紀錄 tab — last 50 runs with type filter; click row → detail view (run meta + checkpoint table)
    ├── RunStatusBar.jsx            — NEW (PR #27): amber (cancelled/interrupted) / green (done) / red (failed) status bar with run_id + copy + progress + 續跑 CTA. running 不出現 — spec §5.3
    ├── SettingsPanel.jsx           — search settings + Baseline 管理 (BQ auto-fetch section + CSV upload fallback + version list)
    ├── CalibrationModal.jsx        — compact tier correction modal
    ├── KeywordEditorModal.jsx      — kept for compat with `batch_engine` keywords.json
    └── ScheduleModal.jsx           — kept for compat with `batch_engine` schedules
```

Removed in PR #27 (legacy sync path retired): `BatchToast.jsx`, `ABCheckPanel.jsx`, `utils/baselineReport.js`.

Layout per route:
- `/` (HomePage) — search bar → A/B columns + alert bar + drawer → optional explanation rows
- `/batch` — 3 sub-tabs (精準詞 / 泛詞 / 歷史紀錄). Each tab content:
  - `ABCheckRunPanel`: 5 visible states — empty (no run) / running (no status bar, only inline progress) / cancelled (amber bar + 續跑 CTA + 待續跑 row tint) / done (green bar + summary pills) / failed (red bar + error message)
  - Severity chip hover shows popup with per-alert detail (baseline rank, A/B rank, reason)
  - Click query text → `navigate('/?keyword=X&filter=diff')` to inspect that keyword in single-keyword mode

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
| `FRONTEND_PORT` | `8086` | Docker host port for frontend |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Absolute path to GCP service-account JSON for BQ fetch (both host AND container side; mounted via docker-compose volume substitution). Recommended deploy location: `handoff/_secrets/<your-sa>.json` (gitignored) |
| `BQ_PROJECT_ID` | `kkday-data-dap-sit` | BQ billing project; this SA has `bigquery.jobUser` here + `dataViewer` on `dm_search_keyword.*` views |
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
- **Batch AB-check is async + checkpointed** (PR #27) — `ab_check_runner.py` is the primary path; per-query checkpoints stream to sqlite so the UI sees progress from query 0. Worker is single-threaded within one run (precise/broad can be parallel runs). Legacy synchronous `/api/ab-check` kept for one release with a deprecation log.
- **AppContext owns polling timers** — `setInterval` handles in a `useRef`; runs survive SPA navigation between `/` and `/batch`. Polling stops automatically when status enters {done, failed, cancelled, interrupted}.
- **HomePage search state lives in context** — `homeKeyword` / `homeFilterMode` / `homeResults` survive route changes (`/` → `/batch` → `/` no longer resets to default "esim")
- **Calibrations are additive** — feedback.json is append-only; re-running a search re-applies all saved corrections automatically
- **No TypeScript** — frontend is plain JavaScript/JSX
- **No DB migration system** — SQLite schema is created inline in `batch_engine.py` on startup
- **Product links point to stage** — `https://www.stage.kkday.com/zh-tw/product/{prod_mid}` since API uses stage environment
- **BQ baseline pipeline as primary upstream** — daily 07:00 Asia/Taipei cron runs via APScheduler in-process (shares main.py's scheduler instance). Manual CSV upload remains as Plan B; HTML upload is rejected (front-end input dropped, backend returns 400).
- **Guardrail = warn, not hold** — if new fetch row count < 50% of previous OR == 0, the new version is still activated (no manual rollback bottleneck), but `last_run.warnings` is set and the UI banner highlights it. Operator can manually rollback through SettingsPanel version list.
- **`baseline_service.reload()` after every activation** — both manual upload (existing) and BQ fetch (`_run_fetch` in scheduler) call reload so the in-memory singleton stays fresh without restart.
- **Row UI height locked at min-h-[42px]** — all chips (TierBadge / mismatch chip / AI / 校正) share `text-[9px]`; AI/校正 are absolute-positioned to keep row height stable on hover. AI explanation block expands the row beyond 42px when active.
- **Baseline alert status 5 級** — `baseline_service.find_baseline_alerts()` 不再把「沒出現在前 300 結果」一律當 `missing`,改成:
  - `present` — 在前 300 內且在 `expected_rank × BASELINE_DROP_MULTIPLIER` 內
  - `rank_drop` — 在前 300 內但偏離 baseline (原 `dropped` 改名)
  - `out_of_window` — 不在前 300,但 stage HEAD 確認商品還存在 (僅是排到 300 名外)
  - `removed` — 不在前 300,且 stage HEAD 回 404 (商品確實下架)
  - `check_failed` — 不在前 300,且 stage 檢查 timeout/5xx (UI 顯示「未確認」)
  Stage 檢查走 `stage_product_check.py` 的 module-level singleton (執行緒安全 + TTL cache,預設 600s)。同個 prod_mid 跨 request 共享快取;`/api/ab-check` 與 `/api/unified-search` 共用。可用 `STAGE_CHECK_ENABLED=false` 關掉,所有原 missing 商品會 fallback 成 check_failed。

## Known Limitations & Gotchas

### Destination Matching Granularity
`intent_matcher.py` matches destinations using string containment against product API `destinations[]` field (district-level codes like 新宿, 銅鑼灣). Hierarchical lookups (e.g. 札幌 → 北海道 → 日本) are **not** supported natively. The matcher adds a fallback: if the searched location appears in the product's **name or description**, `dest_match` is still True. This handles common cases like "日本eSIM" products whose title contains 日本 but whose destination field lists only a district code.

### POI Keyword Handling
Keywords like "環球影城" or "迪士尼" are attractions (POI), not geographic locations. `intent_matcher.py` uses `_is_known_geo()` to distinguish — if a keyword is NOT a recognized country/city/destination, it routes to `_verify_poi_keyword()` (Route E) which skips destination matching and instead checks if the keyword appears in the product title/description.

### Calibration API Method Name
`CalibrationManager` exposes `save_feedback()` (not `add_feedback()`). `main.py` must call `calibration_manager.save_feedback(...)`.

### eslint-plugin-react-hooks v7
Version 7 adds `react-hooks/set-state-in-effect` and `react-hooks/immutability` rules that flag async setState in effects (a common pattern here). These are downgraded to `warn` in `eslint.config.js` — the pattern is intentional.
