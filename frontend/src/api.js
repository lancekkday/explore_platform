const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

// SIT 上見過上游代理 504 timeout 時前端拿到 nginx HTML body,
// `.then(jsonOrThrow)` 直接噴 SyntaxError('<html>')。
// 改走 jsonOrThrow 統一 guard:Content-Type 不是 JSON 直接 throw NetworkError
// 帶 status + body 前 200 字,呼叫端可以正常 catch 顯示錯誤訊息。
export class NetworkError extends Error {
  constructor(message, { status, contentType, bodyPreview } = {}) {
    super(message)
    this.name = 'NetworkError'
    this.status = status
    this.contentType = contentType
    this.bodyPreview = bodyPreview
  }
}

async function jsonOrThrow(r) {
  const ct = r.headers.get('content-type') || ''
  if (!ct.includes('application/json')) {
    const text = await r.text().catch(() => '')
    throw new NetworkError(
      `non-JSON response (HTTP ${r.status}, ${ct || 'no Content-Type'})`,
      { status: r.status, contentType: ct, bodyPreview: text.slice(0, 200) },
    )
  }
  return r.json()
}

export const fetchCompare = (keyword, cookie, count, ai_enabled, search_api) =>
  fetch(`${API_BASE}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, cookie, count, ai_enabled, search_api }),
  }).then(jsonOrThrow)

export const fetchGuestCookie = (env = 'stage') =>
  fetch(`${API_BASE}/guest-cookie?env=${env}`).then(jsonOrThrow)

export const saveFeedback = (keyword, product_id, user_tier, comment, synonyms) =>
  fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, product_id, user_tier, comment, synonyms }),
  }).then(jsonOrThrow)

export const fetchKeywords = () =>
  fetch(`${API_BASE}/keywords`).then(jsonOrThrow)

export const updateKeywords = (keywords) =>
  fetch(`${API_BASE}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  }).then(jsonOrThrow)

export const startBatch = (cookie, search_api, version_a, version_b) =>
  fetch(`${API_BASE}/batch/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie, search_api, version_a, version_b: version_b ?? null }),
  }).then(jsonOrThrow)

export const stopBatch = () =>
  fetch(`${API_BASE}/batch/stop`, { method: 'POST' }).then(jsonOrThrow)

export const fetchBatchStatus = () =>
  fetch(`${API_BASE}/batch/status`).then(jsonOrThrow)

export const fetchBatchResults = () =>
  fetch(`${API_BASE}/batch/results`).then(jsonOrThrow)

export const fetchBatchHistory = () =>
  fetch(`${API_BASE}/batch/history`).then(jsonOrThrow)

export const fetchBatchHistoryDetail = (id) =>
  fetch(`${API_BASE}/batch/history/${id}`).then(jsonOrThrow)

export const fetchSingleHistory = () =>
  fetch(`${API_BASE}/single/history`).then(jsonOrThrow)

export const fetchSingleHistoryDetail = (id) =>
  fetch(`${API_BASE}/single/history/${id}`).then(jsonOrThrow)

export const fetchSchedules = () =>
  fetch(`${API_BASE}/batch/schedule`).then(jsonOrThrow)

export const addSchedule = (config) =>
  fetch(`${API_BASE}/batch/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  }).then(jsonOrThrow)

export const updateSchedule = (id, fields) =>
  fetch(`${API_BASE}/batch/schedule/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  }).then(jsonOrThrow)

export const deleteSchedule = (id) =>
  fetch(`${API_BASE}/batch/schedule/${id}`, { method: 'DELETE' }).then(jsonOrThrow)

export const explainProduct = (keyword, product) =>
  fetch(`${API_BASE}/explain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      keyword,
      product_name:     product.name,
      tier:             product.tier,
      mismatch_reasons: product.mismatch_reasons || [],
      destinations:     product.destinations     || [],
      main_cat_key:     product.main_cat_key     || '',
    }),
  }).then(jsonOrThrow)

// ── AB-check runner (async + checkpointed) ────────────────────────────────

export const startABCheckRun = (type, version_a, version_b, cookie, limit, resume_run_id) =>
  fetch(`${API_BASE}/ab-check/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, version_a, version_b, cookie, limit, resume_run_id }),
  }).then(jsonOrThrow)

export const getABCheckStatus = (run_id, since_idx = 0, { timeoutMs = 8000 } = {}) => {
  // Polling tick — bail at 8s so slow backend responses don't pile up behind
  // the 2s setInterval. Fast-fail surfaces in AppContext as a warning, next
  // tick retries fresh.
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  return fetch(
    `${API_BASE}/ab-check/status?run_id=${encodeURIComponent(run_id)}&since_idx=${since_idx}`,
    { signal: ctrl.signal },
  ).then(jsonOrThrow).finally(() => clearTimeout(timer))
}

export const cancelABCheckRun = (run_id) =>
  fetch(`${API_BASE}/ab-check/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id }),
  }).then(jsonOrThrow)

export const fetchABCheckHistory = (type, limit = 50) => {
  const params = new URLSearchParams()
  if (type) params.set('type', type)
  params.set('limit', String(limit))
  return fetch(`${API_BASE}/ab-check/history?${params}`).then(jsonOrThrow)
}

export const fetchABCheckHistoryDetail = (run_id) =>
  fetch(`${API_BASE}/ab-check/history/${encodeURIComponent(run_id)}`).then(jsonOrThrow)

export const fetchUnifiedSearch = (keyword, cookie, count, ai_enabled, search_api, version_a, version_b) =>
  fetch(`${API_BASE}/unified-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, cookie, count, ai_enabled, search_api, version_a, version_b }),
  }).then(jsonOrThrow)

export const fetchBaselineKeywords = () =>
  fetch(`${API_BASE}/baseline/keywords`).then(jsonOrThrow)

export const uploadBaseline = (file, type) => {
  const form = new FormData()
  form.append('file', file)
  if (type) form.append('type', type)
  return fetch(`${API_BASE}/baseline/upload`, { method: 'POST', body: form }).then(jsonOrThrow)
}

export const fetchBaselineVersions = () =>
  fetch(`${API_BASE}/baseline/versions`).then(jsonOrThrow)

export const rollbackBaseline = (timestamp) =>
  fetch(`${API_BASE}/baseline/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timestamp }),
  }).then(jsonOrThrow)

export const archiveBaselineVersion = (timestamp) =>
  fetch(`${API_BASE}/baseline/versions/${timestamp}`, { method: 'DELETE' }).then(jsonOrThrow)

export const refreshBaselineFromBQ = () =>
  fetch(`${API_BASE}/baseline/refresh-from-bq`, { method: 'POST' }).then(jsonOrThrow)

export const fetchBaselineSourceStatus = () =>
  fetch(`${API_BASE}/baseline/source-status`).then(jsonOrThrow)

export const fetchBaselineCronSchedule = () =>
  fetch(`${API_BASE}/baseline/cron-schedule`).then(jsonOrThrow)

export const updateBaselineCronSchedule = (hour, minute, enabled = true) =>
  fetch(`${API_BASE}/baseline/cron-schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hour, minute, enabled }),
  }).then(jsonOrThrow)
