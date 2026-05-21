-- Source: kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_broad (VIEW)
-- View 自動取 dw_analysis_record.kkday_search_keyword_broad 近 7 天內最新 log_date 的快照
-- 業務邏輯(泛詞嚴格定義、profit_rank 1-10 等)由 RD 在底層 pipeline 維護,
-- 詳細口徑見 Joyce 2026-05-08 v4 HTML「搜尋場景關鍵字巡檢:精準詞 / 泛詞上線表 schema 預覽」
-- ----------------------------------------------------------------------------
-- 輸出欄位:query, prod_nm, prod_mid, profit, ctr, profit_rank

SELECT
   query
  ,prod_nm
  ,prod_mid
  ,profit
  ,ctr
  ,profit_rank
FROM `kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_broad`
WHERE LOWER(market) = 'tw'
ORDER BY query, profit_rank
