#!/bin/bash

# --- Environment Setup ---
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
export PYTEST_BASE_URL="http://localhost:8000"

# --- Colors ---
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' 

echo "======================================"
echo "🚀 Running E2E Automation Suite (v1.6)"
echo "======================================"

# 1. 檢查後端是否在線
if ! curl --silent --fail "$PYTEST_BASE_URL/api/keywords" > /dev/null; then
    echo -e "${RED}❌ Error: Backend server is not running on $PYTEST_BASE_URL${NC}"
    echo "Please run ./restart.sh before testing."
    exit 1
fi

# 2. 執行 pytest
echo "🧪 Executing API Tests..."
pytest tests/e2e_api_test.py -v

# 3. 檢查結果
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ Success: All E2E tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Error: Some tests failed. Please check the logs above.${NC}"
    exit 1
fi
