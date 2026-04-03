#!/bin/bash

PROJECT_DIR="/Users/kkday_borrow_f/Documents/workspace/search-intent-platform"

echo "======================================"
echo "Restarting Search Intent Verification..."
echo "======================================"

# Function to kill process by port
kill_port() {
  local port=$1
  pid=$(lsof -t -i:$port)
  if [ -n "$pid" ]; then
    echo "Found process running on port $port (PID: $pid). Killing it..."
    kill -9 $pid
    echo "Port $port has been cleared."
  else
    echo "No process running on port $port. Clear."
  fi
}

echo "🧹 [1/3] Clearing Ports (8000, 5173)..."
# Backend API Port
kill_port 8000
# Vite Frontend Port
kill_port 5173

# Give OS a moment to free up the sockets
sleep 1

echo "🚀 [2/3] Executing start.sh..."
cd "$PROJECT_DIR" || exit
if [ -f "./start.sh" ]; then
  bash ./start.sh
else
  echo "Error: start.sh not found in $PROJECT_DIR"
fi

echo "✅ [3/3] Restart completed!"
