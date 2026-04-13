#!/bin/bash

PROJECT_DIR="/Users/kkday_borrow_f/Documents/workspace/search-intent-platform"

echo "======================================"
echo "Starting Search Intent Verification..."
echo "======================================"

# Start Backend
echo "[1/2] Starting Backend Server (FastAPI) on port 19426..."
cd "$PROJECT_DIR/backend" || exit
source venv/bin/activate
# Run in background and redirect output to a log file
nohup uvicorn main:app --host 0.0.0.0 --port 19426 > backend.log 2>&1 &
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
