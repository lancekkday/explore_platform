# 個性化搜尋事件回放器 · V1 開發規格

> Search Personalization Replay Inspector — V1
> 狀態：草案，待搜尋 RD 確認第 9 節未決事項
> 最後更新：2026-08-18

---

## 1. 目的

回答一個問題：**同一個 keyword，個性化實驗組（treatment）與對照組（control）看到的結果差在哪，為什麼。**

使用者：QA、搜尋 RD、AM/OP（回報「排序怪怪的」時附上連結）。

### 1.1 V1 要能回答的三個問題

| 問題 | 對應畫面 | 判定依據 |
|---|---|---|
| 個性化到底有沒有生效？ | 對照面板 · 個性化強度 | 強度 < 5% ⇒ 疑似未生效 |
| 這個排序差異是真的還是浮點噪音？ | 排序表 · 同分帶判讀 | 跨同分帶才算真實變動 |
| 差異是哪個維度造成的？ | 相關性六格燈號 + uf/cf 面板 | 六碼逐位比對 |

### 1.2 明確不做（V1 out of scope）

不要實作以下項目，即使看起來很容易：

- prod_mid 反查（「這個商品出現在哪些 keyword」）
- 時間趨勢圖、日對日比較
- 完整 recall → rerank → 曝光漏斗還原
- `ltr_features` 逐特徵數值比對
- 多人（>2）矩陣比較
- 任何寫入行為（本工具唯讀）

---

## 2. 資料來源與成本紅線

### 2.1 硬性限制(2026-08-27 更新)

> **狀態變更記錄**:本節原版本（早期草案）評估 `dl_base.ar-stream_search_record`
> 一天全表掃描約 193GB，超過 75GB 紅線，因此定案「前端/API 一律不得查原表」。
> 2026-08-19 改查正確表名 `dw_analysis_record.stream_search_record`（VIEW），
> 2026-08-26 一度改用資料團隊自建的 `stream_search_record_flat` 中繼表。
> **2026-08-27 跟 RD 討論後改回直查原表**，理由：
> - 該表是 VIEW 且 `data` 為原生 JSON 型別 → per-path 計費有效，dry-run 顯示的
>   是整欄上限，不是實際帳單（`sql/*.sqlx` 實測：1hr 窗 dry-run 估 9.17GB、
>   實際計費 12.6MB）
> - Slack 討論（2026-08-26）實測 kkud/event_id 等值過濾會到 12.9~35.7GB，
>   RD（Duncan）澄清這是「過程查詢量」（bytes processed 計費），不是硬碟
>   （storage）占用，不會累積成本
> - 帳單 project 改指到 `kkday-data-dap-ui`，跟主平台 backend 用的 `-sit` 隔開
> 上面「193GB / 75GB 紅線」是早期用錯表名時的估算，並非本表的實測數字，
> 保留在此僅供歷史脈絡；當前的成本認知以本段上方三點為準。

現行表：`kkday-data-dap.dw_analysis_record.stream_search_record`（VIEW）：

- `data` 欄位是 JSON，逐 path 抽取計費（per-path billing）
- `event_date` 分區條件必填（見紅線 2）；`keyword` / `kkud` 至少一項必填
  （見 `ClusterKeyRequired`）—— 此表無實體叢集，這條規則是正確性考量
  （鎖定唯一事件），不是省成本

> 若在程式碼中看到查詢缺 `event_date` 分區條件、或缺 keyword/kkud 直接
> event_id 點查，視為 bug。

### 2.2 資料流

```
dw_analysis_record.stream_search_record (VIEW,原始表)
        │
        ↓  src/repo/bigquery.py 直接 JSON_VALUE/JSON_QUERY 抽取(不經 dataform)
        │
  FastAPI 服務層
        ↓
  Streamlit 前端
```

`sql/*.sqlx`（dataform 初稿，2026-08-26 曾用來餵 flat 中繼表）目前不接線，
保留作 JSON path 對映參考——`src/repo/bigquery.py` 的欄位抽取邏輯即依此對映。

### 2.3 為什麼必須 join recall

實測（2026-08-17，抽樣 08-09 10:00–11:00）：

- `uf`（user_feature）**只掛在 `recall` / `recall.cache` 事件**，100% 覆蓋
- `content` / `content.cache` **完全沒有 `uf`**（0 / 31,522 筆），只有 `source_event_id`
- 因此 `content.source_event_id → recall.event_id` 的 join 不是最佳化選項，是**唯一路徑**

### 2.4 join 的兩個陷阱

1. **cache 可跨日**：`content.cache` 引用的 `recall.cache` 可能來自前幾天，join 視窗需開 `[D-1, D]`
2. **不可套 `ltr_features` 存在性條件**：`recall.cache` 會被剝掉 `ltr_features` 但保留完整 `uf`。若用同一個 gate 過濾，`uf` 覆蓋率會從約 62% 掉到約 5%

### 2.5 cf 大小

`data.cf` 單筆約 **138 KB**。落表時必須拆出常用子欄位；完整 `cf` 僅在使用者明確點擊「展開」時單筆載入，**絕不隨列表回傳**。

---

## 3. 資料層 Schema

### 3.1 `dl_qa.search_event_daily`

一列 = 一個 content 事件（= 一次結果頁曝光）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `session_id` | STRING | content 的 `event_id`，即 rq_session_id。PK |
| `event_date` | TIMESTAMP | **partition key**。UTC |
| `event_type` | STRING | `content` / `content.cache` |
| `cache_hit` | BOOL | 頂層欄位，非 JSON。優先用此欄判斷快取 |
| `source_event_id` | STRING | 對應的 recall event_id |
| `request_type` | STRING | 固定 `product.list`（V1 只處理這個） |
| `keyword` | STRING | `data.query.keyword`。**cluster key** |
| `normalized_keyword` | STRING | 來自 recall 的 `query_understanding.normalized_keyword` |
| `lang` / `locale` / `currency` | STRING | 多語系維度 |
| `exp_version` | STRING | `data.experiment.exp_version`。**cluster key** |
| `source` | STRING | `web` / app 等 |
| `kkud` | STRING | device_id |
| `member_uuid` | STRING | 登入會員。PII |
| `user_id` | STRING | 來自 recall。PII |
| `ip_masked` | STRING | **落表時遮罩為 /24**，例：`61.216.159.0/24` |
| `filter_json` | STRING | `data.filter`，常為 `{}` |
| `page_start` | INT64 | `pagination.start` |
| `page_count` | INT64 | `pagination.count` |
| `total_count` | INT64 | `pagination.total_count` |
| `prod_cnt` | INT64 | 本頁商品數 |
| `uf_intent` | STRING(JSON) | 原樣保留 `{feature_name:{d,v,t}}`，不展平 |
| `uf_profile` | STRING(JSON) | 同上 |
| `uf_profile_version` | STRING | |
| `uf_lbs` | STRING(JSON) | 新增，dataform 原本未落表 |
| `cf_platform` | STRING | |
| `cf_hour` | INT64 | |
| `cf_weekday` | INT64 | |
| `cf_query_final` | STRING | |
| `cf_query_tokens` | ARRAY\<STRING\> | |
| `cf_raw` | STRING(JSON) | 完整 cf，約 138 KB。**不得出現在列表查詢的 SELECT 中** |
| `ltr_features` | STRING(JSON) | |
| `ltr_features_recovered` | BOOL | 由 cache donor 回收而來 |
| `join_failed` | BOOL | 串不回 recall |
| `uf_absent` | BOOL | 串到了但上游沒推 uf |

分區：`event_date` (DAY)。叢集：`keyword, exp_version, locale`。

### 3.2 `dl_qa.search_event_prod_daily`

一列 = 一個事件中的一個商品。排序畫面的主要來源。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `session_id` | STRING | FK → `search_event_daily` |
| `event_date` | TIMESTAMP | **partition key** |
| `keyword` | STRING | 冗餘欄，**cluster key**，避免查排序還要 join |
| `locale` | STRING | |
| `exp_version` | STRING | **cluster key** |
| `rank` | INT64 | 全域排名 = `page_start + offset + 1` |
| `prod_mid` | STRING | |
| `prod_oid` | STRING | 與 `prod_mid` 相同時前端不重複顯示 |
| `is_ad` | BOOL | |
| `ltr_score` | FLOAT64 | 原始為 float32，注意精度（見 4.2） |
| `relevance_status_code` | STRING | 六碼，保留字串以免掉前導零 |
| `in_rerank_scope` | BOOL | `rank <= 100`。見 4.4 |

分區：`event_date`。叢集：`keyword, exp_version`。

### 3.3 dataform 職責

- incremental，以 `event_date` 為增量鍵
- 承接既有 `uf_from_stream.sql` 邏輯，**額外補上原本未落表的 `uf.lbs` 與 `cf`**
- 新增 `search_event_prod_daily` 的 UNNEST 產出
- `recall_key` donor 邏輯（`FARM_FINGERPRINT` of keyword+lang+locale+currency+filter+experiment+ltr_features_version+prod_mids）沿用，用於回收 `recall.cache` 被剝掉的 `ltr_features`

---

## 4. 領域邏輯

以下四段是本工具的核心價值，必須有單元測試。

### 4.1 `relevance_status_code` 解碼

六位數，**由左至右**每位代表一個相關性維度：

| 位置 | 維度 | 備註 |
|---|---|---|
| 1 | 是否可售 | 商品層 |
| 2 | 地點是否相關 | query 中提及的地點 |
| 3 | 類目是否相關 | |
| 4 | IP 是否相關 | ⚠️ 語意待確認，見 9.1 |
| 5 | 主題是否相關 | |
| 6 | 文本是否相關 | |

第 1、2、3、5、6 位是 query × 商品的相關性。**若第 4 位確認為使用者 IP 地理，則它是這串碼中唯一的 user × 商品維度**，也就是唯一能從相關性碼直接解釋個性化差異的位置 → 前端需獨立標色。

實作要求：

```python
RELEVANCE_DIMS = ["sellable", "location", "category", "ip", "theme", "text"]

def decode_relevance(code: str) -> dict[str, int]:
    """'000220' -> {'sellable':0,'location':0,'category':0,'ip':2,'theme':2,'text':0}"""
    if code is None or len(code) != 6 or not code.isdigit():
        return {d: None for d in RELEVANCE_DIMS}   # 不猜，回 None 讓 UI 顯示未知
    return dict(zip(RELEVANCE_DIMS, (int(c) for c in code)))
```

已觀測值域包含 `0` 與 `2`，**因此不是布林**。等級語意待確認（9.2）。解碼函式必須是純函式且集中在一處，答案回來只改這裡。

### 4.2 同分帶（tie band）

**這是最重要的一段邏輯。**

實測資料：`福岡` 前十筆 `ltr_score` 全落在 `110.99571 ~ 110.99751`，全距 0.0018，相對差異 1.6e-5。`110.996254` 這種尾數是 float32 artifact；在 111 量級，float32 的 ULP 約 7.6e-6，**相鄰兩名差距僅 7～15 ULP**。

結論：前十名的相對順序不具統計意義。任何浮點誤差、索引 shard 順序改變、boost 重算都會翻轉它。

若前端只顯示 `Δrank = -1`，RD 會誤以為個性化邏輯有問題而浪費時間排查。**必須把「不可判讀」明講。**

```python
import numpy as np

TIE_ULP_THRESHOLD = 10   # 可調參數，待與 RD 校準（9.4）

def assign_tie_bands(scores: list[float]) -> list[int]:
    """
    scores 需為降冪排列。回傳每筆所屬的同分帶編號（從 0 開始）。
    相鄰間距 <= TIE_ULP_THRESHOLD 個 float32 ULP 者視為同帶。
    """
    if not scores:
        return []
    bands = [0]
    for prev, cur in zip(scores, scores[1:]):
        if prev is None or cur is None:
            bands.append(bands[-1] + 1)
            continue
        ulp = float(np.spacing(np.float32(prev)))
        bands.append(bands[-1] if abs(prev - cur) <= TIE_ULP_THRESHOLD * ulp
                     else bands[-1] + 1)
    return bands
```

前端需顯示的離散度指標：分數全距、相對差異、最小相鄰間距、換算 ULP 數。

### 4.3 對照判讀

對照的預設是 **treatment vs control**，不是任意兩個使用者。control 組即非個性化 baseline，因此個性化強度只有跟 control 比才有意義。

```python
def verdict(a_rank, b_rank, a_band, b_band):
    if a_rank is not None and b_rank is None:
        return "only_a"          # 個性化的實質證據
    if a_rank is None and b_rank is not None:
        return "only_b"
    if a_rank == b_rank:
        return "identical"
    if a_band == b_band:
        return "tie_unresolvable"   # 同分帶內位移，不可判讀
    return "real_move"              # 跨同分帶，真實排序變動
```

個性化強度：

```python
def personalization_strength(a_top: list[str], b_top: list[str], k: int = 10) -> float:
    overlap = len(set(a_top[:k]) & set(b_top[:k]))
    return 1 - overlap / k
```

警示門檻（V1 先用，之後校準）：

| 強度 | 判定 | 顯示 |
|---|---|---|
| < 5% | 疑似個性化未生效 | 紅 |
| 5% – 60% | 正常 | 無 |
| > 60% | 疑似個性化過度，長尾風險 | 黃 |

### 4.4 精排邊界

只有召回 top 100 進精排，第 101 名之後**沒有 `ltr_score`，個性化不生效，僅依召回序排列**。

`total_count` 常達數百（範例為 867），代表使用者翻到第 11 頁之後看到的是純召回序。這是既有產品行為而非 bug，畫面標示出來可擋掉大量「翻到後面排序怪怪的」誤報。

前端要求：

- 分頁指示器上畫出 rank=100 的邊界線
- `in_rerank_scope = false` 的列，`ltr_score` 欄顯示「未進精排」而非空白
- 若查詢的頁碼整頁落在精排範圍外，頂部顯示提示

### 4.5 join 品質三旗標

`uf` 為 NULL 有三種原因，使用者無法從空白分辨。**面板必須先回答「這筆資料能不能信」，再顯示特徵值。**

| 旗標 | 意義 | UI |
|---|---|---|
| `join_failed` | 串不回 recall 事件 | 紅，且整個 uf/cf 區塊置灰 |
| `uf_absent` | 串到了但上游沒推 uf | 黃 |
| `ltr_features_recovered` | 特徵由 cache donor 回收 | 黃，提醒非原生 |

各特徵的覆蓋率必須與數值並列顯示（實測基準：`uf.intent` 63.5%、`uf.profile` 54.0%、`uf.lbs` 20.3%、`cf` 100%）。使用者要能立刻分辨「空白是常態還是異常」——20% 覆蓋的欄位空白很正常，54% 的空白就值得查。

---

## 5. API 契約

FastAPI。所有端點唯讀。

### 5.1 通用規則

- **`event_date` 為必填**，且 API 層必須強制檢查。BigQuery 的 `require_partition_filter` 會穿透 view，漏掉就是全表掃描
- 日期參數以 **UTC+8** 收，內部轉 UTC 並前後各留 8 小時緩衝（`event_date` 為 UTC，範例 `2026-08-13 07:17:10Z` = 台灣 15:17，跨日邊界極易查不到）
- 分區條件用範圍比較，不要用 `TIMESTAMP_TRUNC(event_date, DAY) = ...`
- `ip_masked` / `member_uuid` / `user_id` **不得進入 URL query string**
- 回應一律不含 `cf_raw`，除 5.4

### 5.2 `GET /api/events`

列表。

參數：`date`（必填，UTC+8）、`keyword`、`kkud`、`member_uuid`、`session_id`、`exp_version`、`locale`、`lang`、`cache_hit`

`keyword` / `kkud` / `member_uuid` / `session_id` **至少須提供一項**，否則回 400。

回應：`session_id, event_date_local, event_type, cache_hit, keyword, locale, exp_version, source, page_start, page_count, total_count, prod_cnt, join_failed, uf_absent`

### 5.3 `GET /api/events/{session_id}`

單筆明細。含 4.1 解碼後的相關性、4.2 同分帶、4.4 精排標記、4.5 三旗標、uf/cf 摘要。

需帶 `date` 以利分區裁剪。

### 5.4 `GET /api/events/{session_id}/cf`

完整 `cf_raw`。單筆、需明確呼叫。前端僅在使用者點擊「展開」時觸發。

### 5.5 `GET /api/compare`

參數：`date`、`keyword`（必填）、`locale`、`exp_a`（treatment）、`exp_b`（control）

回應：
```json
{
  "meta": { "keyword": "...", "locale": "...", "exp_a": "...", "exp_b": "..." },
  "metrics": {
    "personalization_strength": 0.2,
    "top10_overlap": 8,
    "rank_changes": 6,
    "tie_unresolvable_changes": 4,
    "warning": null
  },
  "rows": [
    {
      "prod_mid": "248950",
      "rank_a": 1, "rank_b": 2,
      "band_a": 0, "band_b": 0,
      "verdict": "tie_unresolvable",
      "relevance_a": { "sellable": 0, "location": 0, "category": 0, "ip": 2, "theme": 2, "text": 0 },
      "relevance_b": { "...": 0 },
      "relevance_diff_dims": [],
      "in_rerank_scope": true,
      "is_ad": false
    }
  ]
}
```

`rows` 為 A ∪ B 的合併結果，依 `rank_a` 升冪、缺值排後。

---

## 6. 前端畫面規格

Streamlit，單頁三段。**不做多頁跳轉**——排查時失去 context 成本很高。

### 6.1 條件列

- `event_date`（必填，明確標註 **UTC+8**）
- `keyword`
- `lang` / `locale` / `currency`
- 實驗組：`exp_a`（treatment）、`exp_b`（control），預設自動帶入
- 進階（收合）：`kkud`、`member_uuid`、`session_id`、`cache_hit`

### 6.2 對照面板

四張指標卡：個性化強度、Top10 重疊、位置變動數、同分帶內變動數。

強度依 4.3 門檻上色。標題列顯示兩組的身分摘要（登入狀態、exp_version、事件時間）。

### 6.3 排序表

欄位：`prod_mid` | `A` | `B` | 相關性六格燈號 | 判讀

- 六格燈號：六個小方塊，第 4 格獨立配色（待 9.1 確認）。hover 顯示維度名與數值
- 判讀文字直接寫「同分帶，不可判讀」／「僅 A：④ 差異」／「一致」／「真實變動」
- `only_a` / `only_b` 整列上底色——這才是個性化的實質證據，視覺權重要高於 Δrank
- `is_ad = true` 另加標記
- 頂部分頁指示器畫出精排邊界（見 4.4）

### 6.4 特徵面板

順序固定：**串接品質旗標 → uf → cf**。品質在最上面，因為它決定下面的數值能不能信。

- uf 三列：`intent` / `profile` / `lbs`，每列並列覆蓋率徽章與數值，無值顯示「本筆無資料」
- cf 摘要 chips：`platform` / `hour` / `weekday` / `query.final` / `tokens`
- 「展開完整 cf（138 KB，單筆載入）」按鈕 → 呼叫 5.4

---

## 7. 技術選型

| 層 | 選擇 | 理由 |
|---|---|---|
| 資料 | BigQuery + dataform incremental | 成本紅線，唯一可行 |
| API | FastAPI + `google-cloud-bigquery` | 同一層要同時餵 UI 與後續 MCP tool |
| 前端 | Streamlit | 使用者是 QA/RD，UI 精緻度邊際效益低 |
| 測試 | pytest | 4.1–4.4 為純函式，必須有測試 |

**API 層與前端層要分開。** 後續會包一個唯讀 MCP tool（`search-event-inspect`，風險層級 L0）給 AI 診斷流程用，兩者共用同一套領域邏輯，不維護兩份。分區檢查與 PII 遮罩必須做在 API 層，MCP tool 才吃得到。

正式版目標是掛進 TCMS，與 My Workspace 同殼，讓 AM/OP 可直接開連結而不需 QA 代跑。

### 7.1 建議目錄

```
search-replay-inspector/
├── CLAUDE.md
├── spec/v1-spec.md
├── sql/
│   ├── search_event_daily.sqlx
│   └── search_event_prod_daily.sqlx
├── src/
│   ├── domain/
│   │   ├── relevance.py      # 4.1
│   │   ├── tie_band.py       # 4.2
│   │   └── compare.py        # 4.3
│   ├── repo/bigquery.py      # 分區強制、PII 遮罩
│   └── api/main.py
├── app/streamlit_app.py
└── tests/
```

---

## 8. 驗收條件

1. ~~全程無任何查詢打到 `dl_base.ar-stream_search_record`~~（此條已隨 2.1 的
   2026-08-27 決策失效——`dl_base.ar-stream_search_record` 是早期用錯的表名，
   平台現在直查 `dw_analysis_record.stream_search_record`，見 2.1）
2. 缺 `event_date` 的 API 呼叫回 400，不會送出查詢
3. 輸入 `keyword=福岡` 能同時取得 treatment 與 control 並算出強度
4. 前十筆同分的情境下，判讀欄顯示「同分帶，不可判讀」而非 `Δ = -1`
5. 六碼解碼在遇到非預期格式時回 `None`，不猜值、不丟例外
6. `join_failed = true` 時 uf/cf 區塊整體置灰
7. 列表回應不含 `cf_raw`；`ip` 僅以 /24 形式出現
8. 4.1–4.3 三個模組有單元測試，含 float32 邊界案例

---

## 9. 未決事項（待搜尋 RD 確認）

前三題不影響畫面骨架，只影響 `decode_relevance` 的解讀。**先按規格開發，答案回來只改解碼函式與配色。**

### 9.1 相關性第 4 位「IP」的語意

是「使用者 IP 的地理相關性」，還是「IP 聯名內容」（如吉卜力、寶可夢主題）？

- 若為前者 → 這是六碼中唯一的個性化維度，需獨立標色，且要與 `uf.lbs` 覆蓋率交叉看
- 若為後者 → 與第 5 位「主題」同性質，一般配色即可

### 9.2 六碼的值域與語意

已觀測到 `0` 與 `2`，因此不是布林。每一位是相關性等級，還是狀態碼？完整值域為何？

### 9.3 第 1 位「可售」= 0 卻能曝光

範例 `000220` 第一位為 0。`0` 是「通過」還是「否」？這個反了會讓整排燈號解讀完全相反。

### 9.4 `ltr_score` 的 110 偏移

`110.99xxx` 看起來像固定 offset（110）加上很小的相關性分數。是否為召回分數帶進精排？

若是，則同分帶問題的**根因在召回端而非精排端** — 這可能值得單獨開票給搜尋 RD，本工具正好能提供證據。同時 4.2 的 `TIE_ULP_THRESHOLD` 需與 RD 校準。

### 9.5 個性化生效旗標（建議新增埋點）

目前 payload 無任何欄位可直接判斷個性化是否套用。建議在 `data` 下新增：

```json
"personalization": { "applied": true, "signals": ["intent", "profile"] }
```

有了 `applied` 這個布林值，畫面就能從「猜」變成「證明」：

- 強度 0% 且 `applied = true` → 明確的 bug
- 強度 0% 且 `applied = false` → 只是沒觸發

這一個欄位可砍掉約一半的誤報，是最值得爭取的項目。

### 9.6 商品名稱（`prod_name`）— 已用 og:title 補值（2026-08-26）

`stream_search_record.prods` payload 本身沒有商品名稱欄位（2026-08-27 改回直查原表後同樣成立，見 2.1）。**已實作短期解法**：`src/repo/product_name_lookup.py`（`ProductNameLookup`，TTL cache 24h + single-flight，仿 `backend/stage_product_check.py`）在 API 層（`event_detail` / `compare`）補上缺值的 `prod_name`，抓 `www.kkday.com` 商品頁公開的 `og:title` meta tag，不需登入。

**locale fallback**（實測發現)：zh-tw 404 常常不是「商品下架」，是「這個商品沒有 zh-tw 語言版本」（案例：`119751`/`164116` 在 zh-tw/zh-cn/zh-hk 皆 404，但 en-us/ja/ko 都有內容）。查不到 zh-tw 時依序試 `en-us → ja-jp → ko-kr → zh-cn → zh-hk`，拿到第一個成功的名稱即可（可能非中文，但比裸 mid 有用）；全部 locale 都 404 才真正視為下架/不存在。

**Code review 補強（同日）**：缺 `prod_mid` 的列改用 `.get()` 避免 `KeyError` 500；「查詢失敗」（timeout/5xx/429 重試用盡）跟「確認查無」（全部 locale 都確定 404）分開快取 —— 前者用短 TTL（`failure_ttl_sec`，預設 5 分鐘），後者才用長 TTL（24h），避免一次線上暫時性故障被誤記成「沒名字」記滿一天；single-flight waiter 的逾時值也改成算入 fallback 鏈的最差總時長，避免 owner 還在跑 fallback 時等待中的 caller 提早拿到 `None`。

**Stage host fallback（同日）**：部署主機若防火牆只放行 stage、沒開對外網路，`www.kkday.com` 整個 host 會連不上（不是 404，是連線失敗）。這種情況（`PRODUCT_HOSTS` 第一個 host 查詢失敗，非乾淨 404）改打 `www.stage.kkday.com`；實測同一批 mid 在 prod/stage 的 `og:title` 一致（商品目錄同步），名稱前綴 `(Stage) ` 標記來源，方便日後目錄不同步時排查。乾淨 404（確認查無）不會多打一輪 stage，只有「查詢失敗」才換 host。

**Re-review 補強**：`_waiter_timeout()` 公式先前漏算「最後一次重試也要 sleep 才回傳」，改成三角數算式並抽成 `_retry_worst_case()`（primary + fallback + 現在的兩個 host 共用同一條）；兩個新測試原本是假陽性（一個提早 return 沒跑到修的那行、一個直接抄 production 算式驗自己），已改成會真的抓到 bug 的寫法。

**第三輪 review 補強**：host escalation 判斷條件原本是「6 次嘗試(zh-tw+5 fallback locale)裡任一次查詢失敗」就整輪重打 stage，這跟「只在整個 host 真的連不上時才換」的設計意圖不符 —— 混在一堆已證實可連通的乾淨 404 之間的單一次孤立逾時，不代表 host 不可達，卻會浪費一整輪 stage 掃描(正是 spec 本身想避免的「浪費呼叫」)。改成「這個 host 6 次全部都查詢失敗，一次明確答案都沒拿到」才判定 host 不可達並換下一個。

**待資料團隊確認的長期解法**（若這個 scrape 方案的延遲/穩定性不夠用時考慮）：是否存在通用商品維度表（`dim_product`/`dm_product` 等）可 join，或建議在 `stream_search_record` 落表時順手 join 商品名稱進 `prods` JSON。已知的窄覆蓋替代方案（`dm_search_keyword.kkday_search_keyword_{precise,broad}`）只覆蓋巡檢關鍵字的 top1/2/top10，蓋不到任意 `prod_mid`，未採用。

### 9.7 `CONTEXT FEATURE`（`cf`）是否漏了「召回管道/訊號」

畫面上 `CONTEXT FEATURE` 欄目前顯示 `platform·hour·weekday`（如 `web·7時·週三`），資料來自原始事件 `data.cf.{platform,hour,weekday,query.final,query.tokens}`（見 `sql/search_event_daily.sqlx`），跟 spec 原始設計（`spec/ui-spec.md` §3 草圖 `cf web·15時·週四`）一致，不是實作走樣。

**待確認**：使用者記得當初跟資料 RD 溝通時，這個商品記錄應該要能看出「根據哪些搜索管道/訊號被召回」，但目前 `cf` 欄位語意是「請求發生當下的環境情境」，不是「商品透過哪個召回管道命中」。全 repo（spec + sql + code）搜尋不到 `recall_channel`/`recall_source`/召回策略這類欄位存在過的痕跡；跟召回較相關的 `uf_intent`（用戶意圖）、`uf_profile`（用戶輪廓）也是個性化訊號，不是召回管道標籤。

需要跟 RD 確認：
1. 系統本來就沒有記錄「召回管道/訊號」這個欄位，還是有但目前的 `stream_search_record`/`search_event_daily.sqlx` 沒有 join 進來？
2. 如果有，欄位叫什麼、掛在哪個原始事件底下（recall？recall.cache？其他？）？
3. 如果沒有，使用者記憶中的說法是否其實是在講「`cf`/`uf` 只掛在 recall 事件上，需要 join 才拿得到」這個技術細節，被口頭轉述成「這欄位在講召回」而混淆了？
