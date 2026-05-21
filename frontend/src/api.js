const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

export const fetchCompare = (keyword, cookie, count, ai_enabled, search_api) =>
  fetch(`${API_BASE}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, cookie, count, ai_enabled, search_api }),
  }).then(r => r.json())

export const fetchGuestCookie = (env = 'stage') =>
  fetch(`${API_BASE}/guest-cookie?env=${env}`).then(r => r.json())

export const saveFeedback = (keyword, product_id, user_tier, comment, synonyms) =>
  fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, product_id, user_tier, comment, synonyms }),
  }).then(r => r.json())

export const fetchKeywords = () =>
  fetch(`${API_BASE}/keywords`).then(r => r.json())

export const updateKeywords = (keywords) =>
  fetch(`${API_BASE}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  }).then(r => r.json())

export const startBatch = (cookie, search_api, version_a, version_b) =>
  fetch(`${API_BASE}/batch/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie, search_api, version_a, version_b: version_b ?? null }),
  }).then(r => r.json())

export const stopBatch = () =>
  fetch(`${API_BASE}/batch/stop`, { method: 'POST' }).then(r => r.json())

export const fetchBatchStatus = () =>
  fetch(`${API_BASE}/batch/status`).then(r => r.json())

export const fetchBatchResults = () =>
  fetch(`${API_BASE}/batch/results`).then(r => r.json())

export const fetchBatchHistory = () =>
  fetch(`${API_BASE}/batch/history`).then(r => r.json())

export const fetchBatchHistoryDetail = (id) =>
  fetch(`${API_BASE}/batch/history/${id}`).then(r => r.json())

export const fetchSingleHistory = () =>
  fetch(`${API_BASE}/single/history`).then(r => r.json())

export const fetchSingleHistoryDetail = (id) =>
  fetch(`${API_BASE}/single/history/${id}`).then(r => r.json())

export const fetchSchedules = () =>
  fetch(`${API_BASE}/batch/schedule`).then(r => r.json())

export const addSchedule = (config) =>
  fetch(`${API_BASE}/batch/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  }).then(r => r.json())

export const updateSchedule = (id, fields) =>
  fetch(`${API_BASE}/batch/schedule/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  }).then(r => r.json())

export const deleteSchedule = (id) =>
  fetch(`${API_BASE}/batch/schedule/${id}`, { method: 'DELETE' }).then(r => r.json())

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
  }).then(r => r.json())

export const runABCheck = (version_a, version_b, cookie, skip_precise, skip_broad) =>
  fetch(`${API_BASE}/ab-check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version_a, version_b, cookie, skip_precise, skip_broad }),
  }).then(r => r.json())

export const fetchUnifiedSearch = (keyword, cookie, count, ai_enabled, search_api, version_a, version_b) =>
  fetch(`${API_BASE}/unified-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, cookie, count, ai_enabled, search_api, version_a, version_b }),
  }).then(r => r.json())

export const fetchBaselineKeywords = () =>
  fetch(`${API_BASE}/baseline/keywords`).then(r => r.json())

export const uploadBaseline = (file, type) => {
  const form = new FormData()
  form.append('file', file)
  if (type) form.append('type', type)
  return fetch(`${API_BASE}/baseline/upload`, { method: 'POST', body: form }).then(r => r.json())
}

export const fetchBaselineVersions = () =>
  fetch(`${API_BASE}/baseline/versions`).then(r => r.json())

export const rollbackBaseline = (timestamp) =>
  fetch(`${API_BASE}/baseline/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timestamp }),
  }).then(r => r.json())

export const archiveBaselineVersion = (timestamp) =>
  fetch(`${API_BASE}/baseline/versions/${timestamp}`, { method: 'DELETE' }).then(r => r.json())

export const refreshBaselineFromBQ = () =>
  fetch(`${API_BASE}/baseline/refresh-from-bq`, { method: 'POST' }).then(r => r.json())

export const fetchBaselineSourceStatus = () =>
  fetch(`${API_BASE}/baseline/source-status`).then(r => r.json())

export const fetchBaselineCronSchedule = () =>
  fetch(`${API_BASE}/baseline/cron-schedule`).then(r => r.json())

export const updateBaselineCronSchedule = (hour, minute, enabled = true) =>
  fetch(`${API_BASE}/baseline/cron-schedule`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hour, minute, enabled }),
  }).then(r => r.json())
