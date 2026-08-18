# V1 實作計畫 — 個性化搜尋事件回放器

> Spec: [spec/v1-spec.md](../../../spec/v1-spec.md)（2026-08-18 草案）
> 日期:2026-08-18
> 原則:spec §9 未決事項不擋開發 — 骨架先行,答案回來只改 `decode_relevance` 與配色。

## 範圍確認

**做**:dataform sqlx 交付物、domain 純函式(4.1–4.4)、FastAPI 唯讀 API(5.2–5.5)、Streamlit 單頁三段(6.1–6.3 + 6.4)、pytest(驗收條件 8)。
**不做**(spec §1.2):prod_mid 反查、趨勢圖、漏斗還原、逐特徵比對、多人矩陣、任何寫入。

## 關鍵決策(spec 沒說死的地方)

1. **BQ 表尚不存在** — `dl_qa.search_event_daily` 由 dataform 產出,dataform repo 由資料團隊管。本專案交付 `sql/*.sqlx` 檔供對方 review 併入;API 層的 BQ client 走 **Repository 介面 + 依賴注入**,測試用 FakeRepo,不需要真表也能完整測 API 契約(含 400 行為、cf_raw 不外洩)。
2. **PII 不進 URL(5.1)與 GET 參數表(5.2)的矛盾** — `member_uuid` / `user_id` 不得出現在 query string,但 5.2 又把 `member_uuid` 列為列表參數。解法:`GET /api/events` 只收非 PII 參數(keyword / kkud / session_id / exp_version / locale / lang / cache_hit;kkud 是 device id,不在 5.1 禁止清單);另開 **`POST /api/events/search`**(JSON body)收全部參數含 `member_uuid`。GET 收到 `member_uuid` 一律 400。
3. **專案位置** — `search_intention/search-replay-inspector/`(explore_platform 的 sibling),獨立 git repo,照 spec §7.1 目錄。
4. **BQ project/dataset 可設定** — env `BQ_PROJECT_ID` / `BQ_DATASET`(預設 `kkday-data-dap` / `dl_qa`),SIT 驗證時可切。
5. **禁查原表的防呆做成 code** — repo 層組出的 SQL 過一個 `assert_no_raw_table()` guard(比對 `ar-stream_search_record` / `ar_stream_search_record`),連工程師手滑都擋(驗收 1)。
6. **UTC+8 → UTC 緩衝**:date 參數為 UTC+8 的日曆日 D → 本地日窗 `[D 00:00+08, D+1 00:00+08)` 轉 UTC 後前後各展 8 小時 → `event_date BETWEEN (D-1)T08:00Z AND (D+1)T00:00Z`,以範圍比較寫進 WHERE(不用 TIMESTAMP_TRUNC)。列回傳時以 `event_date_local`(UTC+8)顯示。

## 分段

### Phase 1 — Domain(TDD,先寫測試)
- `src/domain/relevance.py`:`decode_relevance`(4.1)。非法輸入回 None-dict,不丟例外(驗收 5)。`RELEVANCE_DIMS` 常數集中此處;`ip` 位註記待 9.1。
- `src/domain/tie_band.py`:`assign_tie_bands`(4.2,float32 ULP)+ `dispersion_stats`(全距/相對差/最小相鄰間距/ULP 數)。測試含 float32 邊界:福岡實測值 110.99571~110.99751、None 混入、空list、單筆、負分數。
- `src/domain/compare.py`:`verdict`(4.3)、`personalization_strength`、`strength_warning`(<5% 紅 / >60% 黃)、`merge_rows`(A∪B 合併,rank_a 升冪缺值排後,含 relevance_diff_dims 與 in_rerank_scope)。
- 驗收:pytest 全綠(驗收 8)。

### Phase 2 — Repo 層
- `src/repo/bigquery.py`:
  - `EventRepo` Protocol + `BigQueryEventRepo` + `FakeEventRepo`(測試/demo 用)
  - `local_date_to_utc_range()`(決策 6)
  - 查詢建構器:list / detail / cf / compare 四種,參數化查詢(防注入),list SELECT 白名單**不含 cf_raw**(驗收 7)
  - **detail / cf 點查必須帶 cluster hint**:表叢集鍵是 `keyword, exp_version, locale`,
    只用 `session_id` 點查會繞過 cluster pruning、掃整個 40 小時分區窗 — 互動工具
    每次點列都掃一次,成本紅線失守。API 收 optional `keyword`/`exp_version`/`locale`
    傳進 WHERE;前端從列表 row 帶入(列表回應本來就有這三欄)
  - `assert_no_raw_table()` guard(驗收 1)
  - `mask_ip_to_24()`(落表時已遮罩,API 層再防一次)
### Phase 3 — API 層
- `src/api/main.py`:FastAPI,端點 5.2–5.5 + `POST /api/events/search`(決策 2)。
  - 缺 `date` → 400 且不建查詢(驗收 2);列表四選一 filter 檢查 → 400
  - detail 回應組裝:decode + tie bands + in_rerank_scope + 三旗標 + uf/cf 摘要 + 覆蓋率基準常數(4.5)
  - compare 回應照 5.5 JSON 契約;**另收 optional `cache_hit`** — compare 各側
    自動選最新 session 時必須尊重 UI 選的快取條件,否則使用者明選
    `cache_hit=false` 要看 live 排序,面板卻可能抓到 cache 事件,比對對象錯置
- `tests/test_api.py`:TestClient + FakeRepo,覆蓋驗收 2/3/4/6/7 的 API 面。
### Phase 4 — Streamlit
- `app/streamlit_app.py`:單頁三段(條件列 → 對照面板四卡 + 排序表 → 特徵面板)。
  - 六格燈號(第 4 格獨立配色,標「⚠ 語意待 9.1」)、only_a/only_b 整列底色、同分帶文案、精排邊界線(4.4)、旗標優先於特徵值(4.5)、cf 展開按鈕才打 5.4
  - `API_BASE` env 指向 FastAPI;demo 模式 = API 以 `USE_FAKE=1` 啟動(Streamlit 一律走 API,不直連 repo — 規則集中一層)
### Phase 5 — dataform sqlx
- `sql/search_event_daily.sqlx` / `sql/search_event_prod_daily.sqlx`:incremental、partition `event_date`、cluster 照 §3;join 視窗 `[D-1, D]`(2.4-1)、**不對 recall 套 ltr_features 存在性 gate**(2.4-2)、ip /24 遮罩、cf 拆欄 + cf_raw 保留、donor 回收邏輯註記沿用 `uf_from_stream.sql`。
  - 這兩檔是**交付給資料團隊 review 的初稿**,欄位對映處未能實測的以 `-- TODO(verify)` 標註。
### Phase 6 — 收尾
- 新專案 `CLAUDE.md`(架構、紅線、如何跑)
- `pyproject.toml` + venv + 全套 pytest
- `/code-review`(雙軸:Standards=本計畫+spec 紅線;Spec=v1-spec.md)
- git commit(initial + 若 review 有修正另一顆)

## 驗收對映

| spec §8 | 驗證方式 |
|---|---|
| 1 原表零查詢 | `assert_no_raw_table` guard + grep 測試 |
| 2 缺 date 400 | test_api:不帶 date → 400,FakeRepo.query_count == 0 |
| 3 福岡雙組取強度 | FakeRepo 內建福岡 fixture,test_api compare 斷言 metrics |
| 4 同分帶顯示 | domain 測試 + compare 回應 verdict 斷言 |
| 5 六碼容錯 | relevance 測試:長度錯/非數字/None → all-None |
| 6 join_failed 置灰 | API 回旗標;UI 灰化(Streamlit 目視) |
| 7 無 cf_raw / ip /24 | test_api 斷言列表回應 key set;mask 函式測試 |
| 8 單元測試 | Phase 1 全部 |

## 風險

- sqlx 無法在本機驗證(dataform + 原表權限在資料團隊)→ 標 TODO(verify),PR 給資料團隊。
- spec §9 四題未決 → 全部收斂在 `relevance.py` 常數與 UI 配色,已隔離。

<!-- agy-peer-reviewed: 2026-08-18T13:31:21Z rounds=2 verdict=approved -->
