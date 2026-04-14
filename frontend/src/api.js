const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

export const fetchCompare = (keyword, cookie, count, ai_enabled) =>
  fetch(`${API_BASE}/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, cookie, count, ai_enabled }),
  }).then(r => r.json())

export const fetchGuestCookie = (env = 'stage') =>
  fetch(`${API_BASE}/guest-cookie?env=${env}`).then(r => r.json())

export const saveFeedback = (keyword, product_id, user_tier, comment) =>
  fetch(`${API_BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keyword, product_id, user_tier, comment }),
  }).then(r => r.json())

export const fetchKeywords = () =>
  fetch(`${API_BASE}/keywords`).then(r => r.json())

export const updateKeywords = (keywords) =>
  fetch(`${API_BASE}/keywords`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keywords }),
  }).then(r => r.json())

export const startBatch = (cookie) =>
  fetch(`${API_BASE}/batch/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie }),
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
