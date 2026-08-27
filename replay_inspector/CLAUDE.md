# CLAUDE.md

Search Personalization Replay Inspector(個性化搜尋事件回放器)— 回答「同一個
keyword,treatment 與 control 看到的結果差在哪、為什麼」。唯讀工具。

規格:`spec/v1-spec.md`(資料與領域邏輯,權威)+ `spec/ui-spec.md`(畫面,計量學視覺
系統 — 顏色只給值得查的事,不可判讀的主動退場)。實作計畫:`docs/superpowers/plans/`。

## 紅線(違反即 bug)

1. ~~任何程式路徑不得查原始事件 view~~ —— **2026-08-27 撤除,改回直查**
   `dw_analysis_record.stream_search_record`(跟 RD 討論後定案)。原因:
   - 該表是 VIEW 且 `data` 為原生 JSON 型別 → per-path 計費有效(`sql/*.sqlx`
     內註記:1hr 窗 dry-run 估 9.17GB、實際計費 12.6MB,728 倍差;
     dry-run 數字僅為上限,不是實際帳單)
   - Slack 討論(2026-08-26,D07NAF7UGKH)實測:kkud/event_id 等值過濾會拉到
     12.9~35.7GB;RD(Duncan)澄清這是「過程查詢量」(bytes processed 計費),
     不是硬碟(storage)占用,不會累積成本
   - 帳單 project 指到 `kkday-data-dap-ui`(見下方環境變數表),跟主平台
     backend 用的 `-sit` 隔開
   `src/repo/bigquery.py` 的 JSON path 對映以 `sql/*.sqlx`(資料團隊 review 過
   的 dataform 初稿)為準;標 TODO(verify) 的路徑尚未逐一實測(對照
   `kkday-data-dap-ui` 帳單 project 實跑,event_date=2026-08-24,keyword=福岡)。
   **已用真資料驗證並修正 3 個 sqlx 原稿寫錯的路徑**(2026-08-27):
   - `$.request_type` 欄位在真實 payload 裡根本不存在(完整 dump 過的 content
     事件沒這個 key)——原本的 `request_type='product.list'` 過濾條件會把
     所有列表濾光,已移除
   - `cf.hour` / `cf.weekday` 不存在,實際巢狀在 `cf.time_context.hour` /
     `cf.time_context.weekday` 底下
   - `uf.user_type` / `uf.membership_tier` 不是獨立欄位,是 `uf.profile`
     這個 `{feature_name:{d,v,t}}` 扁平特徵表裡兩個具名 feature 的值,要用
     `$.uf.profile.uf_user_type.d` / `$.uf.profile.uf_membership_tier.d`
     (第一輪隨機抽樣剛好抽到都沒算出這兩個特徵的使用者,一度誤判成「欄位
     不存在」,換一個有訂單歷史的使用者重測才驗到)
   其餘 `TODO(verify)` 路徑(`query.lang/locale/currency`、`kkud`、`source`、
   `member_uuid`、`ip`)已用同一筆真資料核對過,皆正確。
2. **`event_date` 分區條件必填**:API 層缺 `date` 回 400 且查詢不得送出。
   BigQuery `require_partition_filter` 會穿透 view,不能靠 BQ 擋。
3. **PII**:`member_uuid` / `user_id` / ip 不進 URL query string(member_uuid
   過濾走 `POST /api/events/search` body);ip 僅以 /24 出現;列表回應永不含 `cf_raw`。
4. **`maximum_bytes_billed` 不能當這張表的成本護欄**(2026-08-27 實測推翻)——
   使用者原本要求「單次查詢 20GB 硬上限」,設下去後連平常 keyword-only 的單人
   回放查詢都被 BigQuery 直接拒絕執行(job 送出前的預估值超標,連跑都不跑)。
   用 `dry_run=True` 測發現:同一句 SQL 不管拿掉 keyword 過濾、拿掉 ORDER BY、
   砍到只剩 3 個欄位,BigQuery 的預估值全部釘死在同一個數字(~113~163GB,
   視日期而定,含 UTC+8 ±8h buffer 幾乎等於整個分區視窗的 `data` 欄大小)——
   BigQuery 的預估器對 JSON 欄位沒有 per-path 概念,一律以「整欄上限」估算,
   跟 sql/*.sqlx 裡「dry-run 估 9.17GB、實跑計費 12.6MB,728 倍差」是同一件事,
   只是這次落差沒那麼誇張。拿掉預估限制後真的跑,實際計費(`total_bytes_billed`)
   是 ~20GB(vs 預估 112.92GB,約 5.7 倍差)。**結論:預估值跟實際帳單對這張表
   完全兜不起來**,任何低於 ~160GB 的 `maximum_bytes_billed` 都會擋到明明便宜
   的查詢。現行做法:`MAX_BYTES_BILLED_PER_QUERY` 只當「跑到失控」的最後防線
   (預設 300GB,不當日常用量控管),真正的用量顯示改成事後量測
   (`BigQueryEventRepo.last_query_bytes()`,API 回應帶 `bytes_billed`,
   Streamlit 顯示「用量 X GB」)。
   **真實用量參考值**(2026-08-24,keyword=福岡,單一使用者的單人回放明細,
   含 content+recall+prods 三支查詢加總):**約 85GB**;純列表查詢(不含明細)
   單次約 20GB。這遠比原本設想的「一次查詢幾百 MB」高很多,值得知道。
   另外發現並修掉一個放大成本的 bug:Streamlit 每個互動(切事件下拉選單、
   開合特徵面板)都會把整份腳本重跑,原本沒快取的話同一份資料會被重複打好
   幾次 BQ——`app/streamlit_app.py` 的 `_get()` / `_search_events()` 已加
   `st.cache_data(ttl=600)`,同一組條件 10 分鐘內不會重複計費。

## 架構

```
BigQuery dw_analysis_record.stream_search_record (VIEW,原始表,直查)
        ↓
src/repo/bigquery.py    ← JSON_VALUE/JSON_QUERY 抽取 / 分區強制 / PII;EventRepo Protocol
   └── src/repo/fake.py ← FakeEventRepo:測試 + demo(福岡 fixture)
        ↓
src/api/main.py         ← FastAPI(5.2–5.5 + POST /api/events/search)
        ↓
app/streamlit_app.py    ← ui-spec 版面:標題摘要+條件收合 → 讀數列 → 排序對照(同分帶括號)+特徵側欄
```

`sql/*.sqlx`(dataform 初稿)目前不接線,保留作 JSON path 對映參考 ——
2026-08-26 一度改用它們餵的 flat 中繼表,2026-08-27 又改回直查原始表。

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
| `BQ_PROJECT_ID` | `kkday-data-dap` | BQ 專案(資料所在專案,原始表位置) |
| `BQ_DATASET` | `dw_analysis_record` | dataset (2026-08-19 更正,spec 早版寫 dl_qa) |
| `BQ_BILLING_PROJECT` | `kkday-data-dap-ui` | 查詢帳單 project(2026-08-27 改回直查原始表時定案,跟主平台 backend 用的 `-sit` 隔開) |
| `API_BASE` | `http://localhost:8300` | Streamlit 打的 API 位址 |
| `MAIN_APP_URL` | `http://localhost:5888/explore_platform/` | 畫面右上角「搜尋巡檢平台 ↗」連結目標(跟主平台 AppHeader 的「回放」連結是反方向)。docker-compose 的 `replay-ui` service 已覆寫成相對路徑 `/explore_platform/`(同源 nginx 反代下適用) |
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
- **`BQ_PROJECT_ID` 跟主平台 `backend` 撞名**(2026-08-27 SIT 部署踩到):`docker-compose.yml`
  的 `backend`/`replay-api` 兩個 service 共用同一份 `.env`,但兩邊需要指到不同 BQ 專案
  (backend 的 baseline view 在 `kkday-data-dap-sit`;這裡的事件表在 `kkday-data-dap`,
  沒有 `-sit`)。`.env` 裡給主平台設的 `BQ_PROJECT_ID=kkday-data-dap-sit` 會洩漏進
  replay-api 容器蓋掉它自己的程式碼預設值,導致查詢對到錯的專案回 `NotFound`(表在
  正確專案裡確實存在,只是查錯專案)。`docker-compose.yml` 的 `replay-api` service 已加
  `environment: BQ_PROJECT_ID: kkday-data-dap` 覆寫解掉,不用改 `.env` 本身。
