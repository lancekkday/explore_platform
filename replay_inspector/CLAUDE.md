# CLAUDE.md

Search Personalization Replay Inspector(個性化搜尋事件回放器)— 回答「同一個
keyword,treatment 與 control 看到的結果差在哪、為什麼」。唯讀工具。

規格:`spec/v1-spec.md`(資料與領域邏輯,權威)+ `spec/ui-spec.md`(畫面,計量學視覺
系統 — 顏色只給值得查的事,不可判讀的主動退場)。實作計畫:`docs/superpowers/plans/`。

## 紅線(違反即 bug)

1. **任何程式路徑不得查原始事件 view** `dw_analysis_record.stream_search_record`
   (data 欄 JSON 型別,per-path 計費;dry-run 顯示的是整欄上限)。只有 `sql/*.sqlx`
   (dataform incremental)可以碰。`src/repo/bigquery.py:assert_no_raw_table`
   對每句 SQL 防呆,`tests/test_api.py` 另有靜態掃描。
   **無例外** — 2026-08-19 教訓:per-path 計費是「path 大小 × 掃過的分區」,
   不是按命中列算;實測對 view「單筆」回查 prods/uf 實際計費 14~18GB,
   $.cf 更大 → 平台端不存在便宜的直查形狀。cf_raw 落中繼表,
   大 path 的成本統一在 dataform 每日單次掃描付 (spec 原設計)。
2. **`event_date` 分區條件必填**:API 層缺 `date` 回 400 且查詢不得送出。
   BigQuery `require_partition_filter` 會穿透 view,不能靠 BQ 擋。
3. **PII**:`member_uuid` / `user_id` / ip 不進 URL query string(member_uuid
   過濾走 `POST /api/events/search` body);ip 僅以 /24 出現;列表回應永不含 `cf_raw`。

## 架構

```
BigQuery dw_analysis_record.search_event_{daily,prod_daily}   ← sql/*.sqlx (dataform, 資料團隊 review 併入)
        ↓
src/repo/bigquery.py    ← 分區強制 / 成本 guard / PII;EventRepo Protocol
   └── src/repo/fake.py ← FakeEventRepo:測試 + demo(福岡 fixture)
        ↓
src/api/main.py         ← FastAPI(5.2–5.5 + POST /api/events/search)
        ↓
app/streamlit_app.py    ← ui-spec 版面:標題摘要+條件收合 → 讀數列 → 排序對照(同分帶括號)+特徵側欄
```

Domain 純函式(必有測試):
- `src/domain/relevance.py` — 六碼解碼。spec §9.1–9.3 未決,答案回來**只改這個檔**與前端配色
- `src/domain/tie_band.py` — float32 ULP 同分帶(`TIE_ULP_THRESHOLD=10`,待與 RD 校準)
- `src/domain/compare.py` — verdict / 個性化強度(<5% 紅、>60% 黃)/ A∪B 合併
- `src/domain/presentation.py` — 判讀文字/燈號映射/前綴計算/帶間距 (ui-spec §9.2,
  Streamlit 與未來 TCMS 移植共用;§10 可測反模式都在 tests/test_presentation.py)

API 層與前端層分開:後續 MCP tool `search-event-inspect`(L0 唯讀)共用 repo+domain,
分區檢查與 PII 遮罩都在 API/repo 層,MCP 才吃得到。

## 常用指令

```bash
source venv/bin/activate
python -m pytest tests/ -q                      # 全套測試

# 本機 demo(BQ 表未就緒也能跑,吃 FakeEventRepo 福岡 fixture)
USE_FAKE=1 uvicorn src.api.main:app --port 8300
API_BASE=http://localhost:8300 streamlit run app/streamlit_app.py

# 接真 BQ(需 GOOGLE_APPLICATION_CREDENTIALS;表由 dataform 產出後才有資料)
BQ_PROJECT_ID=kkday-data-dap BQ_DATASET=dw_analysis_record uvicorn src.api.main:app --port 8300

# Docker(從 repo 根目錄;與主平台同一份 docker-compose.yml 一起 up)
docker compose up -d replay-api replay-ui
```

## 環境變數

| 變數 | 預設 | 用途 |
|---|---|---|
| `USE_FAKE` | — | `1` = repo factory 回 FakeEventRepo(demo/開發) |
| `BQ_PROJECT_ID` | `kkday-data-dap` | BQ 專案 |
| `BQ_DATASET` | `dw_analysis_record` | dataset (2026-08-19 更正,spec 早版寫 dl_qa) |
| `API_BASE` | `http://localhost:8300` | Streamlit 打的 API 位址 |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | 真 BQ 模式必填 |

## 待決事項(spec §9,骨架不受影響)

- 9.1 六碼第 4 位「IP」語意 → 只影響 `relevance.py` 註解與前端第 4 格配色
- 9.2/9.3 值域與第 1 位方向 → 只影響 `decode_relevance` 解讀與燈號顏色映射
- 9.4 `TIE_ULP_THRESHOLD` 與 RD 校準 → `tie_band.py` 單一常數
- 9.5 建議新增 `personalization.applied` 埋點 → 有了之後對照面板可從「猜」變「證明」

## Gotchas

- 日期參數是 **UTC+8**;`local_date_to_utc_range` 轉 UTC 並前後各留 8h 緩衝,
  分區條件一律範圍比較,不用 `TIMESTAMP_TRUNC`
- `ltr_score` 原始為 float32:同分帶一律用 `np.float32` 的 ULP 判,別用 float64 直覺
- FakeEventRepo 的分數用「升冪累加 gap 再 reverse」建構 — 要讓前段同帶,
  小 gap 要放在升冪序列**尾端**
- sqlx 內 JSON path 標 `TODO(verify)` 處未經實測,以資料團隊 review 為準
