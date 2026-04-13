#!/bin/bash

echo "======================================"
echo "Stopping Search Intent Verification..."
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

echo "Stopping Backend (port 19426)..."
kill_port 19426

echo "Stopping Frontend (port 5888)..."
kill_port 5888

echo "======================================"
echo "All Services Stopped."
echo "======================================"
