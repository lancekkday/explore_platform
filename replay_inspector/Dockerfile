# 個性化搜尋事件回放器 — 單一 image,由 docker-compose 以不同 command 起兩個 service:
#   replay-api: uvicorn src.api.main:app  (預設 CMD)
#   replay-ui : streamlit run app/streamlit_app.py
FROM python:3.11-slim

WORKDIR /app

# 先裝依賴再 COPY 程式碼,改 code 不會重裝 (layer cache)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    "fastapi>=0.110" "uvicorn>=0.29" "numpy>=1.26" \
    "google-cloud-bigquery>=3.20" "streamlit>=1.36" "requests>=2.31"

COPY src ./src
COPY app ./app

EXPOSE 8000 8501

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
