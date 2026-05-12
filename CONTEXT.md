# 搜尋詞 AB 巡檢任務 CONTEXT

> 這份檔案描述一次具體的巡檢任務規格。
> 通用方法論看 `~/.claude/skills/search-keyword-ab-check/SKILL.md`。

## 任務目標

對 KKday 台灣市場的搜尋演算法做 AB 版本巡檢:
1. **精準詞巡檢**:Top1/Top2 商品在 B 版是否還在前面位置(雙重防護:展示 + 守門)
2. **泛詞巡檢**:詞下商品順序在 B 版是否出現大幅變化

A、B 兩個版本由 PM 指定。本工具不關心 A/B 是哪兩個版本(可能是 staging vs candidate、上一版 vs 新版等),**只負責拿 PM 指定的 version 參數呼叫 API 並比對**。

## 資料源

兩份 CSV 已產出於 `data/`:
- `data/search_keyword_precise.csv` — 精準詞 baseline(目前 sample 200 row,full 預期 887 row)
- `data/search_keyword_broad.csv` — 泛詞 baseline(目前 sample 586 row / 60 query,full 預期 22,560 row / 2,370 query)

CSV 是從 Joyce 的搜尋詞巡檢報告 HTML 解析出來的。產出腳本在 `scripts/parse_html.py`。當 Joyce 出新版報告時,**重跑這個腳本即可更新 baseline**。

### 重要:目前 CSV 是 sample,不是全量

精準詞報告的全量是 887 row(報告中只放了「按 search_pv 排序前 200 row」)、泛詞全量是 2,370 query × ~10 row(報告中只放了「取詞下總 profit 前 60 個 query」)。

工具上線前必須:
1. 跟 Joyce 索取完整 CSV / SQL,或
2. 等 Joyce 報告 HTML 改成輸出全量,再重跑 `scripts/parse_html.py`

## 巡檢規則(已跟 PM 對齊)

### 精準詞守門
- Top1 不在 B 版結果中 → P0 告警
- Top1 在 B 版排名比 A 版掉超過 5 名 → P1 告警
- Top2 (若存在) 不在 B 版 → P1 告警
- Top2 在 B 版掉超過 5 名 → P2 告警

### 泛詞守門
- baseline profit_rank 1~10 全部追蹤(不過濾長尾)
- 任一 prod_mid 在 B 版消失 → 告警
- 任一 prod_mid 在 A vs B 之間位置變動超過 5 名(**雙向**,上升下降都算) → 告警
- baseline_rank ≤ 3 → P1,≥4 → P2

### A 版本身穩定性旁路告警(INFO)
- 精準詞 baseline Top1 在 A 版找不到或 > 第 10 位
- 精準詞 baseline Top2 在 A 版找不到或 > 第 15 位
- 泛詞 baseline_rank ≤ 3 的商品在 A 版找不到
- 泛詞 baseline 商品在 A 版偏離 baseline_rank > 20 名

## API 對接

`call_search_api(query, version)` 已在這個 repo 實作。

**Claude Code 動工前的第一步**:先 grep 本 repo 找出 search API client 的位置(可能在 `src/`、`api/`、`clients/` 等目錄),確認:

1. 函式簽名(回傳是 `list[int]` 還是 `list[dict]`?需要 `.get('mid')` 嗎?)
2. version 參數怎麼傳(`?version=` query string?還是 dict 參數?)
3. API 回傳深度(規格說最多 300 個,實際呢?)
4. 限流 / 認證(rate limit、API key、token refresh 等)
5. 錯誤處理(timeout、5xx 怎麼回應?)

**不要重新寫 API client**,直接 import 使用。

## 並行與性能

- 精準詞 200 query × 2 版本 + 泛詞 60 query × 2 版本 = 520 次呼叫(sample)
- 全量會放大到 ~6,500 次
- 建議用 `concurrent.futures.ThreadPoolExecutor`,worker 數從 10 起,看 API 限流調整
- 同 query 同 version 必須 cache(同個 query 的精準詞、泛詞檢查邏輯都會打,不能打兩次)

## 輸出格式

CSV 檔名:`reports/ab_alerts_{VERSION_A}_vs_{VERSION_B}_{YYYYMMDD_HHMMSS}.csv`

欄位:
```
alert_type, keyword_type, query, prod_mid, baseline_rank,
a_rank, b_rank, severity, reason
```

並 print 摘要:
- 總告警數
- 按 severity 分組計數
- P0 告警逐筆列出

## 已知限制與後續

1. 目前 sample CSV 不夠完整,不能上 production 巡檢
2. 4 個極致集中精準詞需特別關注:伊藤潤二、山嵐號、蘭陽動植物、追風(這些詞下只有 1 個成交商品)
3. 第一次跑可能會有大量旁路告警(代表 A 版本身就跟 baseline 不一致),這正常,主告警才是真正要看的

## 跟現有系統的關係

這個工具預計會接到「意圖巡檢中心」(`explore_platform`),作為其中一個巡檢項目。但 v1 先做 standalone CLI,跑通後再考慮整合。

## 動工順序建議

1. **探勘現有 repo** — 看 search API client、現有的測試檔結構、CI 設定
2. **跑通 sample 版本** — 用 `data/*.csv`(目前的 sample)+ 真實 API,先跑出第一份 alerts CSV
3. **單元測試** — 至少測試:rank 比對函數、嚴重度判定、A 版旁路判定
4. **整合到現有 CLI / 巡檢系統**(如果有)
5. **等 Joyce 出全量資料,切換 baseline**
