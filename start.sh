#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo "Starting Search Intent Verification..."
echo "======================================"

# Start Backend
echo "[1/2] Starting Backend Server (FastAPI) on port 19426..."
cd "$PROJECT_DIR/backend" || exit
# 自動建 venv 並安裝（新機器首次部署時）
if [ ! -f "venv/bin/uvicorn" ]; then
  echo "⚙️  venv 不存在，初始化中..."
  python3 -m venv venv
  venv/bin/pip install -r requirements.txt
  echo "✅ 依賴安裝完成"
fi
# 用 venv 完整路徑，不依賴 source activate（nohup 子 shell 不繼承環境）
nohup venv/bin/uvicorn main:app --host 0.0.0.0 --port 19426 > backend.log 2>&1 &
echo "Backend started. Logs are being written to backend/backend.log"

# Start Frontend
echo "[2/2] Starting Frontend Server (Vite) on port 5888..."
cd "$PROJECT_DIR/frontend" || exit
# Run in background and redirect output to a log file
nohup npm run dev > frontend.log 2>&1 &
echo "Frontend started. Logs are being written to frontend/frontend.log"

echo "======================================"
echo "All Services Started Successfully!"
echo "👉 預設 Frontend 網址: http://localhost:5888"
echo "👉 預設 Backend API: http://localhost:19426"
echo "若要即時查看前端日誌，可執行: tail -f frontend/frontend.log"
echo "若要停止服務，可執行: ./restart.sh 取代，或自行 kill port。"
echo "======================================"
