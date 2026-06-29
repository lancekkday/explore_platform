// Canonical cross-version match key for a search result row.
//
// Backend contract (kkday_api._coerce_product_id + main._normalize_mid): prod_mid
// is normalized to a non-zero positive integer per real product. A value of 0 / not
// a positive number means "no reliable identity" — an anomaly the backend also
// reports via mid_warnings.
//
// Cross-version (A vs B) matching MUST key on this value and must NOT fall back to
// `id`: `id` can resolve to a per-version rank (_slim_product uses rank when no oid),
// so falling back would key the same anomalous row differently in each column and
// produce a spurious "未出現" / wrong cross-rank. Anomalous rows return null here
// and simply get no cross-match.
export function prodMatchKey(item) {
  const m = item?.prod_mid
  return typeof m === 'number' && m > 0 ? m : null
}
