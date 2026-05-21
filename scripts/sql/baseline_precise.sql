-- Source: kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_precise (VIEW)
-- View 自動取 dw_analysis_record.kkday_search_keyword_precise 近 7 天內最新 log_date 的快照
-- 業務邏輯（精準詞嚴格定義、search_pv ≥ 100 門檻等）由 RD 在底層 pipeline 維護,
-- 詳細口徑見 Joyce 2026-05-08 v4 HTML「搜尋場景關鍵字巡檢:精準詞 / 泛詞上線表 schema 預覽」
-- ----------------------------------------------------------------------------
-- 輸出欄位:query, is_destination, search_pv,
--          top1_prod_nm, top1_prod_mid, top1_profit, top1_ctr,
--          top2_prod_nm, top2_prod_mid, top2_profit, top2_ctr
-- (View 本身額外帶一個 `market` 欄位用於過濾,不寫入 CSV)

SELECT
   query
  ,is_destination
  ,search_pv
  ,top1_prod_nm
  ,top1_prod_mid
  ,top1_profit
  ,top1_ctr
  ,top2_prod_nm
  ,top2_prod_mid
  ,top2_profit
  ,top2_ctr
FROM `kkday-data-dap-sit.dm_search_keyword.kkday_search_keyword_precise`
WHERE LOWER(market) = 'tw'
ORDER BY search_pv DESC
