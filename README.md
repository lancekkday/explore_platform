# 搜尋巡檢平台 / Search Audit Platform

KKDay 搜尋結果品質巡檢工具，支援單次/批次關鍵字巡檢、A/B 版本對比、Baseline 守門商品監控。

## 快速開始

```bash
cp .env.example .env   # 填入必要的環境變數
./start.sh             # 啟動 backend (:8000) + frontend (:5173)
```

詳細架構、API 端點、環境變數說明請參考 [CLAUDE.md](./CLAUDE.md)。

## 主要功能

- **統一巡檢** — 輸入關鍵字，同時取得 A/B 兩版搜尋結果，自動判定每個商品的意圖匹配度 (T1/T2/T3/MISS)
- **Baseline 標註** — 自動標記精準詞 Top1/Top2 與泛詞利潤排名前 10 的守門商品
- **A/B 對比** — 比較兩個演算法版本間 baseline 商品的排名變化，產生嚴重度分級告警
- **批次巡檢** — 多關鍵字自動化巡檢，支援排程與 Slack 通知
- **CSV 匯出** — 一鍵匯出巡檢結果，BOM+UTF-8 確保 Excel/Numbers 相容
- **人工校正** — PM 可手動覆寫商品 Tier，校正結果持久化並自動套用

## 技術架構

- **Frontend**: React + Vite + Tailwind CSS (無 TypeScript)
- **Backend**: FastAPI + SQLite
- **Search API**: KKDay v3 search API，透過 `test_exp` 參數切換演算法版本
