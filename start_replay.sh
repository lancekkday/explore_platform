#!/bin/bash
# 啟動「個性化搜尋事件回放器」(replay_inspector/) — 與主平台 (start.sh) 分開起。
# 用法:
#   ./start_replay.sh          # 真 BQ 模式 (需 GOOGLE_APPLICATION_CREDENTIALS,表由 dataform 產出)
#   USE_FAKE=1 ./start_replay.sh   # demo 模式 (內建福岡 fixture,不打 BQ)
set -e
cd "$(dirname "$0")/replay_inspector"

if [ ! -d venv ]; then
  echo "[replay] 建立 venv 並安裝依賴..."
  python3 -m venv venv
  ./venv/bin/pip install -q -e ".[dev]"
fi

REPLAY_API_PORT="${REPLAY_API_PORT:-8300}"
REPLAY_UI_PORT="${REPLAY_UI_PORT:-8301}"

lsof -ti tcp:"$REPLAY_API_PORT" | xargs kill -9 2>/dev/null || true
lsof -ti tcp:"$REPLAY_UI_PORT" | xargs kill -9 2>/dev/null || true

echo "[replay] API  → http://localhost:$REPLAY_API_PORT (USE_FAKE=${USE_FAKE:-0})"
USE_FAKE="${USE_FAKE:-}" ./venv/bin/uvicorn src.api.main:app --host 0.0.0.0 --port "$REPLAY_API_PORT" > replay_api.log 2>&1 &

echo "[replay] UI   → http://localhost:$REPLAY_UI_PORT"
API_BASE="http://localhost:$REPLAY_API_PORT" ./venv/bin/streamlit run app/streamlit_app.py \
  --server.port "$REPLAY_UI_PORT" --server.headless true \
  --server.baseUrlPath /explore_platform/replay > replay_ui.log 2>&1 &

echo "[replay] done. 入口:主平台 /explore_platform/replay/ (直連: http://localhost:$REPLAY_UI_PORT/explore_platform/replay/)"
