# 搜尋詞 AB 巡檢工具

## 對 Claude Code 的指引

請依以下順序進行:

1. **先讀 `CONTEXT.md`** — 這個任務的具體規格、CSV 路徑、API 對接點、跟 PM 對齊過的閾值
2. **再讀 `~/.claude/skills/search-keyword-ab-check/SKILL.md`** — 通用方法論,解釋為什麼是這樣設計
3. **動工前先探勘**(`grep -r "search" src/`、看 `tests/`、看 `requirements.txt` / `pyproject.toml`),搞清楚:
   - search API client 在 repo 哪個位置、回傳格式長什麼樣
   - 既有的測試框架(pytest? unittest?)
   - 既有的 CLI 結構(有 typer / click 嗎?)
4. **接 API**:把 `scripts/keyword_ab_check.py` 開頭的 `call_search_api` stub 換成 import 既有 client(找 `TODO[CC]` 標記)
5. **跑單元測試**:`pytest tests/test_check_logic.py -v`(這些測試不打 API,純邏輯驗證)
6. **跑 sample 巡檢**(假設 PM 已給 version 字串):
   ```
   python scripts/keyword_ab_check.py --version-a v1 --version-b v2
   ```
7. **檢查輸出** `reports/ab_alerts_*.csv`,看告警量合理嗎

## 檔案結構

```
search_intention/
├── CONTEXT.md                          # 這次任務的規格(讀這個)
├── README.md                           # 這份檔
├── data/
│   ├── search_keyword_precise.csv      # 精準詞 baseline (sample 200 row)
│   └── search_keyword_broad.csv        # 泛詞 baseline (sample 60 query / 586 row)
├── scripts/
│   ├── parse_html.py                   # 從 Joyce 報告 HTML 重新產 baseline
│   └── keyword_ab_check.py             # 巡檢主腳本(需要接 API)
├── tests/
│   └── test_check_logic.py             # 純邏輯測試,不打 API
└── reports/                            # 巡檢輸出(自動建立)
```

## 重要提醒

- **目前 CSV 是 sample 不是全量**。CONTEXT.md 有寫怎麼拿全量。
- **A、B 版本由 PM 指定**,不要寫死在程式裡。
- **不要重新實作 API client**,用 repo 裡既有的。
- **同 query 同 version 必須 cache**(已在腳本用 `lru_cache` 處理),確保不會重複呼叫 API。

## skill 安裝

`skill/SKILL.md` 是給未來其他類似巡檢任務複用的。建議 copy 到:

```
~/.claude/skills/search-keyword-ab-check/SKILL.md
```

讓 Claude Code 之後在 KKday 其他類似巡檢場景(例如香港市場、其他詞表)可以複用方法論。
