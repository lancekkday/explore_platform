---
name: search-keyword-ab-check
description: 對搜尋演算法做 AB 版本巡檢,根據兩張 baseline 表(精準詞、泛詞)判斷 B 版是否相對 A 版出現排名退化。觸發情境包含:RD 改動 search ranking 邏輯後要驗收、PM 要決定新演算法版本能否上線、要回答「這個搜尋詞下的命脈商品還在不在前面」之類的問題。需要 baseline CSV(精準詞 + 泛詞)以及一個能呼叫 search API 並指定版本的方法。本 skill 不負責 baseline 產出,只負責拿到 baseline 後做巡檢。
---

# 搜尋詞 AB 巡檢方法論

## 核心命題

**先知道哪個商品重要,再去搜尋結果驗證它在不在位置上。**

不是從搜尋結果反推哪個商品重要 — 重要性已經由 baseline 表決定了(基於過去 30 天實際成交數據)。巡檢做的是「驗證」而非「探索」。

## 兩張 baseline 表

巡檢需要兩份 CSV,代表兩種不同性質的搜尋詞:

### 表 1:精準詞 (`search_keyword_precise.csv`)

詞下歷史成交極度集中(1~3 個商品),例如「chiikawa」幾乎全部成交都在 chiikawa 公園門票。

欄位:
- `query` — 搜尋詞
- `is_destination` (BOOL) — 是否為景點實體(NER 命中 viewpoint/poi)
- `search_pv` — 30 天搜尋次數
- `top1_prod_nm`, `top1_prod_mid`, `top1_profit`, `top1_ctr` — 詞下 profit 第 1 名商品
- `top2_prod_nm`, `top2_prod_mid`, `top2_profit`, `top2_ctr` — 第 2 名(可能 NULL)

特性:
- 進得了這張表 = 嚴格集中度條件已過,**不需要再做風險分級**,全部都是「需要嚴格守門」的詞
- 約 4 個 query 是 `top2_prod_mid` 為 NULL,代表詞下只有 1 個成交商品 — 這是極致集中,P0 中的 P0
- 約一半 query 是 `top2_profit=0`,代表 Top2 有點擊但無成交,實質等同「只有 Top1 重要」

### 表 2:泛詞 (`search_keyword_broad.csv`)

詞下成交分布廣的搜尋詞,例如「大阪」、「esim」這種大目的地或大類別詞。

欄位 (long format):
- `query`, `prod_nm`, `prod_mid`, `profit`, `ctr`, `profit_rank`
- 每個 query 最多 10 row(profit 排名 1~10)

特性:
- profit_rank 在 query 內必為 1, 2, 3... N(連續、不跳號)
- profit_rank 5~10 的 profit 常為 0(只是排名占位,實際無成交) — **依規則仍然要追蹤**

## 巡檢核心規則

### 精準詞:Top1/Top2 守門

對每個 query,baseline 給的 `top1_prod_mid`(以及 `top2_prod_mid` 若存在)要在 B 版搜尋結果中找到。

判斷:
- **DISAPPEARED**:商品在 A 版中存在,但 B 版完全沒回傳 → 告警
- **DROPPED**:在 A 版第 N 位,B 版第 (N+drop) 位,**drop > 5** → 告警
- A 版本身就找不到該商品 → **不算 B 的鍋**,跳過(baseline 過時、商品下架等)

嚴重度:
- Top1 DISAPPEARED → P0
- Top1 DROPPED > 5 → P1
- Top2 DISAPPEARED → P1
- Top2 DROPPED > 5 → P2

### 泛詞:雙向位置變化

對每個 (query, prod_mid) 比對 A vs B 的位置:
- **DISAPPEARED**:A 有 + B 沒有 → 告警
- **MOVED**:`abs(b_rank - a_rank) > 5`(雙向,上升下降都算)→ 告警
- A 版本身找不到 → 跳過

雙向告警的理由:大幅升上來代表演算法理解變了,可能後面藏 bug,值得看一眼。

嚴重度:
- baseline_rank ≤ 3 + 任何告警類型 → P1
- baseline_rank ≥ 4 + 任何告警類型 → P2

### 旁路告警:A 版本身穩定性

A 版可能不是穩定 baseline(由 PM 指定的測試版本),這時主告警的可信度要打折。**用旁路告警標記出可信度低的 query**,方便 PM 判讀:

精準詞旁路條件(輸出 INFO,不影響主告警):
- baseline Top1 商品在 A 版找不到,或排到第 10 位之後
- baseline Top2 商品在 A 版找不到,或排到第 15 位之後

泛詞旁路條件(輸出 INFO):
- baseline 中 profit_rank ≤ 3 的商品在 A 版找不到
- baseline 商品在 A 版位置偏離 baseline_rank 超過 20 名

旁路告警的精神:「我的對照組可能本來就壞了 — 主告警僅供參考」。

## 實作要點

### API 呼叫策略

每個 query 要呼叫 A、B 兩版,每次取最多 300 個結果。

- 精準詞 N × 2 + 泛詞 (M 個 query) × 2 ≈ 6,500 次呼叫(假設 887 + 2,370)
- 並行很重要,但要尊重 API 限流
- 同 query 同版本應該 cache,不重複呼叫
- 必須能容忍個別呼叫失敗,不要讓一次 timeout 中斷整輪巡檢

### 比對邏輯

```python
def find_rank(mid: int, results: list[int]) -> Optional[int]:
    """商品在結果列表中的位置(1-indexed),不存在回 None"""
    try:
        return results.index(mid) + 1
    except ValueError:
        return None
```

注意 results 用 `prod_mid` 作 key,**不要用商品名比對**(prod_nm 在 baseline 跟 search API 之間可能因標題改寫而飄)。

### 輸出格式

每個告警一個 record:

```
alert_type        : 'main' | 'side'
keyword_type      : 'precise' | 'broad'
query             : 搜尋詞
prod_mid          : 出問題的商品 mid
baseline_rank     : 在 baseline 中的位置 (Top1=1, Top2=2, profit_rank...)
a_rank            : 商品在 A 版的位置 (None = 找不到)
b_rank            : 商品在 B 版的位置 (None = 找不到)
severity          : 'P0' | 'P1' | 'P2' | 'INFO'
reason            : 人類可讀的描述
```

CSV 輸出檔名建議:`ab_alerts_{VERSION_A}_vs_{VERSION_B}_{timestamp}.csv`

### 邊界處理

- `top2_prod_mid` 可能是 NaN(精準詞詞下只有 1 個成交商品),`pd.isna()` 跳過
- 泛詞 `prod_mid` 重複(極少見但可能):同 query 不同 rank 出現相同 mid,當作分開的 row 處理
- API 回傳順序就是排名順序,不要再依其他欄位排序
- 中文 query(包含日韓字元)直接當 string 處理,不需要 encode

## 校準節奏

第一次跑全量會產生大量告警(可能上千)。標準作業流程:

1. **第 1 輪**:用 sample CSV(200 精準 + 60 泛詞)跑通工具,確認沒程式 bug
2. **第 2 輪**:用全量 baseline 跑一次當前 production vs production(A=B 同版本),預期應該 0 告警 — 若有,代表規則太嚴或 baseline 太舊
3. **第 3 輪**:接到實際 A vs B 演算法,看告警量
4. **跟 PM 校準**:依告警量調整閾值(精準詞 drop=5、泛詞 delta=5、旁路閾值)

## 不在 skill 範圍內的事

- **baseline CSV 的產出** — 由 BQ + 報告管線產出,在報告系統那邊維護,不是巡檢工具的責任
- **搜尋 API 的實作** — 各個專案都有自己的 search client,巡檢工具是消費者
- **告警通知** — 是否要進 Slack、Jira、Email,取決於專案需求,巡檢工具負責產出 CSV / JSON,通知層自行串接

## 完成判斷

巡檢腳本能正確輸出告警 CSV,且滿足以下:
- 精準詞、泛詞都有覆蓋
- 主告警跟旁路告警有區分
- 嚴重度有分級(P0/P1/P2/INFO)
- 同 query 同版本的 API 呼叫有 cache
- 個別 API 失敗不會中斷整輪
- 可以指定 A、B 版本參數(由 PM 決定,不寫死)
