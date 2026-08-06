# 提案:device_id 可編輯參數 + test_exp 10 碼化

> 狀態:**已實作 (2026-08-06)** — 定案:test_exp 全鏈 string 且前端直接帶入不驗證;device_id 抽到前端設定,空 = 後端預設。測試:`backend/test_device_id_test_exp_plumbing.py`
> 日期:2026-07-24
> 背景:為了做個性化搜尋巡檢,需要把 `device_id` 從 `kkday_api.py` 內部 env 讀取抽成可編輯參數;同時 `test_exp` 將從單碼版本號變成 10 碼,對應前端設定頁 / 欄頭的 test_exp A/B 輸入。

兩個改動性質不同:

- **改動 A(device_id)**:新增一個 pass-through 參數,完全照 PR #28(lang/locale/channel)的既有模式做,風險低。
- **改動 B(test_exp 10 碼)**:型別問題,關鍵決策是 int → string,牽涉 DB migration 與舊 run 相容。

---

## 改動 A:device_id 抽成可編輯參數

現狀:`backend/kkday_api.py:221` 在函式內部讀 env `KKDAY_SEARCH_DEVICE_ID`,寫死 fallback,呼叫端完全碰不到。

### 後端(照 lang/locale/channel 的模式)

| 檔案 | 調整 |
|------|------|
| `kkday_api.py` | `fetch_kkday_products_v3()` 加 `device_id: str = None` 參數;抽 `DEFAULT_DEVICE_ID` 常數(env → hardcode fallback),參數為空時 fallback |
| `main.py` Pydantic models | `UnifiedSearchRequest`、`ABCheckRequest`、`ABCheckStartRequest`、`BatchRunRequest`、`CompareRequest` 各加 `device_id: Optional[str] = None`(main.py:100-164) |
| `main.py:641` `_process_version` | 加 `device_id` 參數,v3 時塞進 kwargs;unified-search 兩處呼叫(main.py:802、807)跟著帶 |
| `ab_check.py:65` `_fetch_results` | 加 `device_id` 參數並傳入 fetch;**cache key 加入 device_id**(跟 lang/locale/channel 一致——個性化搜尋下,同 query 同版本但不同 device_id 結果會不同) |
| `ab_check.py` | `_compare_row` / `_compare_broad_group` / `run_ab_check` / `_run_precise` / `_run_broad` 全部把 device_id 穿透下去 |
| `ab_check_runner.py` | **run-level 釘住**,完全複製 locale 的做法:`ab_check_runs` 表加 `device_id` 欄(`CREATE TABLE` + `ALTER TABLE ADD COLUMN` 雙寫 migrate);`start_run` 收到 `resume_run_id` 時從 parent 讀回蓋掉 caller 值(個性化結果跟 device 綁定,續跑混用不同 device_id 會讓 ok rows 跨 device 混合,跟跨 locale 混合是同一種錯);`_row_to_run_dict` 回傳它 |
| `batch_engine.py` | `process_keyword` / `run_batch_sync` / `run_batch` 加參數穿透;main.py:252 排程呼叫處 `s.get("device_id")` 跟上 |

### 前端

| 檔案 | 調整 |
|------|------|
| `context/AppContext.jsx` | 加 `const [deviceId, setDeviceId] = useState('')`,空字串 = 用後端預設;跟 channel 一樣 Home/Batch 共用 |
| `SettingsPanel.jsx` | Channel 下方加一個 Device ID 文字輸入框,placeholder 顯示「留空使用預設」,加 title 說明是個性化搜尋巡檢用 |
| `api.js` | `fetchUnifiedSearch`、`startABCheckRun`、`startBatch`、`fetchCompare` 加 `device_id` 欄位 |
| `HomePage.jsx` / `ABCheckRunPanel.jsx` / `BatchPage.jsx` | 呼叫處帶入 ctx 的 deviceId |
| `RunStatusBar` / `ABCheckRunPanel` 進度行 / `ABCheckHistoryTable` | 比照 run-level locale 的三處顯示,加 device_id(建議截斷顯示前 8 碼,hover 看全值),讓使用者知道「這個 run 是用哪個 device 跑的」 |

---

## 改動 B:test_exp 變 10 碼

### 關鍵決策:int → string

**強烈建議整條鏈改成 string**,理由:

1. 「10 碼」通常是 positional code(每一碼代表一個實驗槽位),**前導零有意義**——`0000000001` 用 int 存會變成 `1`,送給 API 就是錯的值。
2. 就算目前沒有前導零,10 碼數字已經超出「版本號」語意,當字串處理才不會之後再改一次。
3. **SQLite 陷阱**:`ab_check_runs.version_a` 是 `INTEGER` affinity(ab_check_runner.py:84-85),就算 Python 丟字串進去,`"0000000001"` 會被 SQLite 自動轉成整數 1,前導零直接消失。**必須新增 TEXT 欄位或改建表**,不能只改 Python 型別。

### 後端

| 檔案 | 調整 |
|------|------|
| `kkday_api.py:200,242` | `test_exp: int = 3` → `test_exp: str = "3"`;body 的 `"test_exp"` 送字串(需跟 RD 確認 API 收 10 碼時 JSON 型別是 string 還是 number——有前導零就一定是 string) |
| `main.py` Pydantic | `version_a` / `version_b` 全部 `int` → `str`;建議加 validator 接受 int 自動轉 str(`Union[int, str]` coerce),舊 client / 排程 JSON 不會炸 |
| `ab_check.py` | `_fetch_results` 的 `version: int` 型別註記改 str;cache key 不用動(tuple 裡型別跟著變) |
| `ab_check_runner.py` | ① 新增 `version_a_txt` / `version_b_txt` TEXT 欄位(ALTER TABLE 雙寫 migrate,讀取時 fallback 舊 INTEGER 欄),或直接 rebuild 表——建議前者,跟既有 migrate 模式一致;② resume 的 A/B mismatch 檢查(runner:510 `parent_va != version_a_new`)兩邊先 `str()` normalize,否則舊 run(int)續跑新 code(str)會誤判 mismatch |
| `main.py:252` 排程 | `s.get("version_a", 0)` 預設值改 `"0"`;既存 schedule JSON 裡的 int 靠 Pydantic coerce 吃掉 |
| `history.db` extra JSON | version 存在 JSON 裡,string 無痛,不用 migrate |
| CLI(ab_check_runner `__main__` 的 argparse) | `type=int` → `type=str` |

### 前端

| 檔案 | 調整 |
|------|------|
| `context/AppContext.jsx:52-53` | `useState(0)` / `useState(1)` → `useState('0')` / `useState('1')`,**state 一律存字串** |
| `SettingsPanel.jsx:207-222` | Version A/B 輸入框 `type="number"` + `parseInt` → `type="text" inputMode="numeric"` + `replace(/\D/g,'')`,`maxLength={10}`,寬度 `w-16` → 約 `w-28` |
| `AnnotatedResultList.jsx:31-41` | 欄頭 test_exp 輸入框 `maxLength={4}` → `10`,寬度 `w-[36px]` → 約 `w-[90px]`(前端 A/B 欄頭對應處) |
| `HomePage.jsx:300-325` | `onVersionChange` 裡的 `parseInt` 拿掉,直接存過濾後字串;`String(versionA)` 包裝可以移除 |
| `ABCheckRunPanel.jsx:266-276` | 同上,`parseInt` → 字串 |
| `ABCheckHistoryTable.jsx:225` | 顯示歷史 run 的 A/B——10 碼會變寬,版面確認一下即可 |

---

## 待確認(等 SASD)

1. **10 碼 test_exp 是否可能有前導零?** 這決定 int/string。建議不管答案都走 string,但 **API body 的 JSON 型別**(`"test_exp": "0000000001"` vs `1234567890`)需要跟 RD 確認一次。
2. **新的預設值**:10 碼制之後 A=`0`、B=`1` 還是合法值嗎?還是有新的 10 碼預設(例如 `0000000000` / `0000000001`)?這影響 AppContext 和 Pydantic 的 default。
3. **device_id 留空的語意**:留空 = 沿用 env 預設(等於現在的匿名巡檢);另可選配「產生隨機 device_id」按鈕模擬全新用戶,是否要做待定。

## 實作順序建議

1. **device_id 先做**——純加參數、風險低,不依賴 SASD 細節。
2. **test_exp 型別改動後做**——碰到 DB migration 和舊 run 相容,且預設值 / JSON 型別要等 SASD 確認。
3. `ab_check_runs` 的兩件 DB 改動(device_id 新欄 + version 轉 TEXT 欄)**建議同一個 PR 一次 migrate 完**,避免兩次 ALTER TABLE 各自處理相容邏輯。
