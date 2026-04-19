#!/bin/bash

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "======================================"
echo "Starting Search Intent Verification..."
echo "======================================"

# 啟動前清理已佔用的 port，避免殘留 process 導致新進程啟動失敗
kill_port() {
  local port=$1
  local pid
  pid=$(lsof -t -i:"$port" 2>/dev/null)
  if [ -n "$pid" ]; then
    echo "⚠️  Port $port 被 PID $pid 佔用，清除中..."
    kill -9 "$pid"
    sleep 0.5
  fi
}

kill_port 19426
kill_port 5888

# Start Backend
echo "[1/2] Starting Backend Server (FastAPI) on port 19426..."
cd "$PROJECT_DIR/backend" || exit
# 自動建 venv 並安裝（新機器首次部署時）
if [ ! -f "venv/bin/uvicorn" ]; then
  echo "⚙️  venv 不存在，初始化中..."
  python3 -m venv venv
  venv/bin/pip install -r requirements.txt
  echo "⚙️  安裝 Playwright 瀏覽器（chromium）..."
  venv/bin/playwright install chromium
  echo "✅ 依賴安裝完成"
fi
# 用 venv 完整路徑，不依賴 source activate（nohup 子 shell 不繼承環境）
nohup venv/bin/uvicorn main:app --host 0.0.0.0 --port 19426 > backend.log 2>&1 &
echo "Backend started. Logs are being written to backend/backend.log"

# Start Frontend
echo "[2/2] Starting Frontend Server (Vite) on port 5888..."
cd "$PROJECT_DIR/frontend" || exit
# 自動安裝 npm 套件（新機器首次部署時）
if [ ! -d "node_modules" ]; then
  echo "⚙️  node_modules 不存在，執行 npm install..."
  npm install
  echo "✅ npm 安裝完成"
fi
nohup npm run dev > frontend.log 2>&1 &
echo "Frontend started. Logs are being written to frontend/frontend.log"

echo "======================================"
echo "All Services Started Successfully!"
echo "👉 預設 Frontend 網址: http://localhost:5888"
echo "👉 預設 Backend API: http://localhost:19426"
echo "若要即時查看前端日誌，可執行: tail -f frontend/frontend.log"
echo "若要停止服務，可執行: ./restart.sh 取代，或自行 kill port。"
echo "======================================"
