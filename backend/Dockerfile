# Use the official Playwright Python image which includes Chromium
# Version must match playwright==1.58.0 in requirements.txt
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers are pre-installed in the base image; link chromium for runtime
RUN playwright install chromium

COPY . .

# Ensure data directory exists for SQLite / JSON persistence
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
