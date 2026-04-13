# Search Intent Platform

KKDay 搜尋意圖驗證平台，用於稽核 stage / production 兩套搜尋引擎的商品排序品質。

## 功能概覽

- **雙環境比對**：同一關鍵字同時打 stage 與 production API，並排顯示結果差異
- **意圖判定**：自動將每個商品分為四個等級
  - T1 完全相關 / T2 部分相關 / T3 疑似相關 / MISS 不相關
- **排名追蹤**：顯示商品在兩個環境之間的名次變動（▲▼）
- **品質指標**：NDCG@10/50/150、Recall@K、Mismatch Rate
- **AI 解釋**：點擊每個商品的 AI 按鈕，以繁體中文說明判定理由
- **人工校正**：對判定有疑問的商品可手動設定正確 tier，下次搜尋自動套用
- **批次巡檢**：設定關鍵字清單，一次跑完所有詞並留存歷史紀錄

## 快速開始

### 本地開發

```bash
# 1. 複製環境變數設定
cp .env.example .env
# 填入 OPENAI_API_KEY（選填，AI 功能需要）

# 2. 啟動服務（backend :8000 + frontend :5888）
./start.sh

# 重啟（自動 kill 舊 process）
./restart.sh
```

### Docker 部署

```bash
cp .env.example .env
# 視需要調整 BACKEND_PORT / FRONTEND_PORT / VITE_BASE_URL

docker compose up -d --build
```

EC2 子路徑部署範例（`/explore_platform/`）：
```env
VITE_BASE_URL=/explore_platform/
VITE_API_URL=/explore_platform/api
```

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `OPENAI_API_KEY` | — | AI 判定與解釋功能（選填） |
| `AI_MODEL_NAME` | `gpt-4o-mini` | 使用的 OpenAI 模型 |
| `DEST_DUMP_DIR` | `backend/data` | 目的地資料目錄 |
| `BACKEND_PORT` | `19426` | Docker backend host port (EC2) |
| `FRONTEND_PORT` | `8086` | Docker frontend host port (EC2) |
| `VITE_BASE_URL` | `/` | 前端 base path |
| `VITE_API_URL` | `/api` | API base path |

## 意圖判定邏輯

### 關鍵字類型拆解

系統會先判斷關鍵字的類型，再選擇對應的判定路徑：

| 類型 | 範例 | 判定依據 |
|------|------|----------|
| 純類別 | `esim`、`美食` | 商品 category code + 關鍵字是否出現於名稱/描述 |
| 目的地 + 類別 | `日本eSIM`、`東京一日遊` | 地點比對 + category code 比對 |
| 目的地 + 主題 | `北海道滑雪`、`沖繩潛水` | 地點比對 + 主題詞彙是否出現於名稱/描述 |
| 純目的地 | `九份`、`京都` | 地點比對為主 |

### Tier 判定矩陣

| Tier | 說明 | 條件 |
|------|------|------|
| T1 完全相關 | 精準命中 | 目的地 ✓ + 類別完全符合（或主題出現於商品名稱） |
| T2 部分相關 | 有關但不精準 | 目的地 ✓ 但類別不符，或類別 ✓ 但目的地不符 |
| T3 疑似相關 | 邊緣相關 | 目的地 ✓ 但關鍵字只出現於描述；或商品名稱含搜尋詞但 category 不符 |
| MISS 不相關 | 明顯無關 | 目的地與類別皆不符，且商品名稱/描述均未提及搜尋詞 |

### 地點比對：階層式推論

地點比對不限字串精確比對，支援三層邏輯：

1. **字串比對**：商品 destination 清單直接包含搜尋地點
2. **Ancestor 推論**：搜尋「日本」→ 命中 destination 為「福岡」（福岡的 ancestor 是日本）；搜尋「北海道」→ 命中「札幌」
3. **國家 ISO fallback**：若搜尋詞為國家名稱（如「日本」）但在 code 表中查無對應，改用 ISO 代碼（JP）與商品 destination 的 `isoCountryCode` 比對

目的地階層資料來源：`backend/data/be2_destinations_dump/`（從 BE2 svc-geo API 爬取的完整樹狀結構）。

### 支援的類別關鍵字

| 關鍵字 | 對應 Category |
|--------|---------------|
| `esim`、`sim`、`wifi`、`上網` | CATEGORY_081 |
| `門票`、`景點門票`、`ticket` | CATEGORY_001 |
| `一日遊`、`tour` | CATEGORY_020 |
| `美食`、`餐廳`、`自助餐`、`buffet` | CATEGORY_079 |
| `交通`、`接送`、`新幹線`、`jr` | CATEGORY_120 |

---

## AI 輔助功能

平台整合 GPT-4o-mini 提供兩種 AI 輔助，均為**選填**（未設定 `OPENAI_API_KEY` 時自動 fallback 為規則判定）。

### 1. 關鍵字意圖解析（搜尋時啟用）

在批次關鍵字設定中可為每個詞開啟 AI 解析。開啟後，系統會先讓 GPT 將關鍵字結構化：

```
輸入：「北海道溫泉旅館」
輸出：{ location: "北海道", category: null, theme: "溫泉", core_product: "旅館" }
```

解析結果用於精準拆解複合詞，補足規則無法處理的模糊表達。未開啟時改用正則規則拆解。

### 2. 商品判定解釋（逐筆查詢）

在巡檢清單中點擊每個商品旁的 **AI** 按鈕，GPT 會以 2～3 句繁體中文說明：

- 為什麼這個商品被判為該 tier
- 判定是否合理，以及潛在的疑慮點

解釋邏輯會優先點出**最關鍵的不符原因**（類別不符 > 地點不符），避免次要原因掩蓋主因。

AI 用量（token 數、費用）會記錄於 `history.db` 的 `ai_usage_log` 資料表，可透過 `GET /api/ai/usage` 查詢彙總。

## 資料說明

| 檔案 | 用途 |
|------|------|
| `backend/data/history.db` | SQLite — 批次與單次巡檢紀錄、AI 用量 |
| `backend/data/keywords.json` | 批次關鍵字清單 |
| `backend/data/feedback.json` | 人工校正紀錄（append-only） |
| `backend/data/unified_destinations.json` | 目的地名稱 ↔ code 對照表 |

## 執行測試

```bash
# 需先啟動 backend
./run_tests.sh

# 單一測試
cd backend && source venv/bin/activate
pytest tests/test_e2e_api.py -v
```
