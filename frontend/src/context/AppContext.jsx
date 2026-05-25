import { createContext, useContext, useEffect, useRef, useState } from 'react'
import {
  fetchGuestCookie,
  fetchKeywords, updateKeywords,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
  fetchBaselineKeywords,
  startABCheckRun, getABCheckStatus, cancelABCheckRun,
} from '../api'

const POLL_INTERVAL_MS = 2000

function emptyRun() {
  // rowsMap: idx → checkpoint row (live state)
  return { runId: null, status: null, total: 0, doneCount: 0,
           runningIdx: null, rowsMap: new Map(), sinceIdx: 0,
           limitN: null, summary: null, errorMsg: null, error: null }
}

const TERMINAL = new Set(['done', 'failed', 'cancelled', 'interrupted'])

// Backend `detail` payloads can be string (HTTPException) or Array
// (FastAPI 422 ValidationError). React crashes if we render an Array, so
// always coerce to a printable string before setting state.
function errToStr(detail, fallback) {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    return detail.map(d => d?.msg || JSON.stringify(d)).join('; ') || fallback
  }
  if (detail && typeof detail === 'object') {
    try { return JSON.stringify(detail) } catch { return fallback }
  }
  return fallback
}

const AppContext = createContext(null)

// 同檔匯出 hook + provider 是慣例。react-refresh 規則只接受純元件 export,
// 這裡刻意忽略 (HMR 在 dev 模式下會略微降級,影響可忽略)
// eslint-disable-next-line react-refresh/only-export-components
export function useAppContext() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useAppContext must be used inside <AppContextProvider>')
  return ctx
}

export function AppContextProvider({ children }) {
  // ── Search/AB settings (shared by HomePage & BatchPage) ──────────────────
  const [versionA, setVersionA] = useState(0)
  const [versionB, setVersionB] = useState(1)
  const [enableAB, setEnableAB] = useState(true)
  const [searchApi, setSearchApi] = useState('v3')
  const [aiEnabled, setAiEnabled] = useState(false)

  // ── Locale / channel (per-request API fields, shared by Home & Batch) ────
  // 預設值對齊後端 kkday_api.py 的 DEFAULT_*。lang + locale 給 HomePage 切,
  // channel 給 SettingsPanel 切。
  const [lang, setLang] = useState('zh-tw')
  const [locale, setLocale] = useState('tw')
  const [channel, setChannel] = useState('ios')

  // ── Cookie / connection ──────────────────────────────────────────────────
  const [cookie, setCookie] = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [cookieError, setCookieError] = useState('')

  // ── Baseline metadata ────────────────────────────────────────────────────
  const [baselineKeywords, setBaselineKeywords] = useState([])
  const [baselineCounts, setBaselineCounts] = useState({ precise: 0, broad: 0 })
  const [baselineDropMultiplier, setBaselineDropMultiplier] = useState(3)

  // ── HomePage 單詞巡檢 state (survives SPA route changes) ─────────────────
  // 上次的 keyword、結果四件套、篩選模式;切到 /batch 再切回 / 不會被
  // HomePage local state default 蓋掉。
  const [homeKeyword, setHomeKeyword] = useState('esim')
  const [homeFilterMode, setHomeFilterMode] = useState('all')
  const [homeResults, setHomeResults] = useState({
    versionA: null, versionB: null, baseline: null, abComparison: null,
  })

  // ── Audit (batch) keyword list + schedules ───────────────────────────────
  const [auditKeywords, setAuditKeywords] = useState([])
  const [schedules, setSchedules] = useState([])

  // ── AB-check runner state (polled, survives tab switch) ──────────────────
  const [preciseRun, setPreciseRun] = useState(emptyRun)
  const [broadRun, setBroadRun] = useState(emptyRun)
  const pollTimers = useRef({ precise: null, broad: null })
  // Mirror state for polling — avoids the functional-setState snapshot hack
  // (which doubles up under React StrictMode dev). Refresh on each render so
  // pollRunOnce reads the latest sinceIdx/rowsMap directly from the ref.
  const runStateRef = useRef({ precise: preciseRun, broad: broadRun })
  runStateRef.current = { precise: preciseRun, broad: broadRun }

  const setRunFor = (type) => (type === 'precise' ? setPreciseRun : setBroadRun)

  function clearPollTimer(type) {
    if (pollTimers.current[type]) {
      clearInterval(pollTimers.current[type])
      pollTimers.current[type] = null
    }
  }

  function mergeRows(prevMap, freshRows) {
    if (!Array.isArray(freshRows) || freshRows.length === 0) return prevMap
    const next = new Map(prevMap)
    for (const r of freshRows) next.set(r.query_idx, r)
    return next
  }

  // Sequential worker means rows below the first non-terminal idx are frozen.
  // Next sinceIdx = idx of the first row still pending / running (or maxIdx+1 if all done).
  function computeNextSinceIdx(map) {
    if (map.size === 0) return 0
    const indices = Array.from(map.keys()).sort((a, b) => a - b)
    for (const idx of indices) {
      const s = map.get(idx)?.status
      if (s !== 'ok' && s !== 'error') return idx
    }
    return indices[indices.length - 1] + 1
  }

  async function pollRunOnce(type, runId) {
    // Read latest snapshot from ref (always current; no StrictMode double-fire risk)
    const snapshot = runStateRef.current[type]
    if (snapshot.runId !== runId) {
      // run 被 reset / 換新 run,這次 polling 是 stale
      return
    }
    try {
      const res = await getABCheckStatus(runId, snapshot.sinceIdx)
      if (!res?.run) return
      const merged = mergeRows(snapshot.rowsMap, res.rows)
      const newSinceIdx = computeNextSinceIdx(merged)
      setRunFor(type)(prev => prev.runId === runId ? {
        ...prev,
        status: res.run.status,
        total: res.run.total_queries,
        doneCount: res.progress?.done ?? prev.doneCount,
        runningIdx: res.progress?.running_idx ?? null,
        rowsMap: merged,
        sinceIdx: newSinceIdx,
        limitN: res.run.limit_n,
        summary: res.run.summary ?? prev.summary,    // F2: persist summary for done bar
        errorMsg: res.run.error_msg ?? prev.errorMsg, // F8: surface backend error
      } : prev)
      if (TERMINAL.has(res.run.status)) clearPollTimer(type)
    } catch (e) {
      // 單次 polling 失敗不殺 interval,讓下一輪重試
      console.warn(`[AB poll/${type}] tick failed:`, e?.message)
    }
  }

  function startPolling(type, runId) {
    clearPollTimer(type)
    pollTimers.current[type] = setInterval(() => pollRunOnce(type, runId), POLL_INTERVAL_MS)
  }

  async function startRun(type, limit, resumeRunId = null) {
    // F7: in-flight guard — double-click / racy resume would otherwise spawn
    // a second backend run that the UI immediately forgets about.
    const cur = runStateRef.current[type]
    if (cur.status === 'starting' || cur.status === 'running') {
      console.warn(`[AB start/${type}] ignored: run already ${cur.status}`)
      return null
    }
    clearPollTimer(type)
    const setter = setRunFor(type)
    setter({ ...emptyRun(), status: 'starting' })
    try {
      // F10: empty / '0' / negative / NaN ⇒ null (全跑); otherwise ≥1
      const raw = (limit == null) ? null : parseInt(limit, 10)
      const limitN = (raw == null || isNaN(raw) || raw <= 0) ? null : raw
      const startRes = await startABCheckRun(type, versionA, versionB, cookie, limitN, resumeRunId, lang, locale, channel)
      if (!startRes?.run_id) {
        setter({ ...emptyRun(), error: errToStr(startRes?.detail, '啟動失敗') })
        return null
      }
      const runId = startRes.run_id
      setter({
        ...emptyRun(),
        runId,
        status: startRes.status,
        total: startRes.total_queries,
        limitN,
      })
      // 立刻拉一次 status 把 pending rows 渲染出來,再開始 2s polling
      await pollRunOnce(type, runId)
      startPolling(type, runId)
      return runId
    } catch (e) {
      setter({ ...emptyRun(), error: errToStr(e?.message, '伺服器連線異常') })
      return null
    }
  }

  async function cancelRun(type) {
    const cur = type === 'precise' ? preciseRun : broadRun
    if (!cur.runId) return
    try {
      const res = await cancelABCheckRun(cur.runId)
      // F4: backend may return 200 with {ok:false, reason:'…'} (phantom run,
      // worker dead). Surface it so the user isn't stuck staring at a frozen
      // 'running' state. Polling 自己會在下個 tick 看到 status flip 後停掉 timer。
      if (res && res.ok === false) {
        setRunFor(type)(prev => prev.runId === cur.runId ? {
          ...prev,
          error: `取消失敗:${errToStr(res.reason, '無法判定 worker 狀態,請重新整理')}`
        } : prev)
      }
    } catch (e) {
      setRunFor(type)(prev => prev.runId === cur.runId ? {
        ...prev,
        error: errToStr(e?.message, '取消失敗 — 伺服器連線異常')
      } : prev)
    }
  }

  function resetRun(type) {
    clearPollTimer(type)
    setRunFor(type)(emptyRun())
  }

  // 卸載時清掉 timer (HMR / page reload)
  useEffect(() => () => {
    clearPollTimer('precise')
    clearPollTimer('broad')
  }, [])

  // ── Drawer / modal state (cross-page) ────────────────────────────────────
  const [settingsVisible, setSettingsVisible] = useState(false)
  const [kwEditorVisible, setKwEditorVisible] = useState(false)
  const [kwInputText, setKwInputText] = useState('')
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState(null)

  // ── Actions ──────────────────────────────────────────────────────────────

  async function autoFetchCookie() {
    try {
      const res = await fetchGuestCookie('stage')
      if (res?.cookie) {
        setCookie(res.cookie)
        setCookieInfo(res)
        setCookieError('')
        return res
      }
      return null
    } catch {
      setCookieError('憑證對接異常')
      return null
    }
  }

  async function fetchAuditData() {
    try {
      const [kwRes, schedRes] = await Promise.all([fetchKeywords(), fetchSchedules()])
      if (kwRes?.keywords) setAuditKeywords(kwRes.keywords)
      if (Array.isArray(schedRes)) setSchedules(schedRes)
    } catch (e) { console.error('Failed to fetch audit data:', e) }
  }

  async function saveKeywords() {
    const kws = kwInputText.split(/\n|,/).map(s => s.trim()).filter(s => s)
    await updateKeywords(kws)
    setKwEditorVisible(false)
    fetchAuditData()
  }

  async function handleSaveSchedule(config) {
    try {
      if (config.id) await updateSchedule(config.id, config)
      else await addSchedule(config)
      setScheduleModalVisible(false)
      setEditingSchedule(null)
      fetchAuditData()
    } catch (e) {
      console.error('儲存失敗:', e)
    }
  }

  async function handleToggleSchedule(s) {
    await updateSchedule(s.id, { enabled: s.enabled ? 0 : 1 })
    fetchAuditData()
  }

  async function handleDeleteSchedule(id) {
    await deleteSchedule(id)
    fetchAuditData()
  }

  function openKeywordEditor() {
    setKwInputText(auditKeywords.map(k => k.keyword).join(', '))
    setKwEditorVisible(true)
  }

  function openScheduleModal(schedule = null) {
    setEditingSchedule(schedule)
    setScheduleModalVisible(true)
  }

  // ── Mount: fetch cookie + audit data + baseline keywords ─────────────────
  useEffect(() => {
    autoFetchCookie()
    fetchAuditData()
    fetchBaselineKeywords().then(res => {
      if (res?.keywords) setBaselineKeywords(res.keywords)
      if (res?.precise_count != null || res?.broad_count != null) {
        setBaselineCounts({ precise: res.precise_count || 0, broad: res.broad_count || 0 })
      }
    }).catch(() => {})
  }, [])

  const value = {
    // Search/AB
    versionA, setVersionA, versionB, setVersionB, enableAB, setEnableAB,
    searchApi, setSearchApi, aiEnabled, setAiEnabled,
    // Locale / channel (lang+locale on HomePage, channel in SettingsPanel)
    lang, setLang, locale, setLocale, channel, setChannel,
    // Cookie
    cookie, cookieInfo, cookieError, autoFetchCookie,
    // Baseline metadata
    baselineKeywords, baselineCounts, baselineDropMultiplier, setBaselineDropMultiplier,
    // Audit
    auditKeywords, fetchAuditData,
    schedules,
    // AB-check runs (polled)
    preciseRun, broadRun, startRun, cancelRun, resetRun,
    // HomePage single-keyword inspection (cross-route persistent)
    homeKeyword, setHomeKeyword,
    homeFilterMode, setHomeFilterMode,
    homeResults, setHomeResults,
    // Modal state
    settingsVisible, setSettingsVisible,
    kwEditorVisible, setKwEditorVisible, kwInputText, setKwInputText, saveKeywords, openKeywordEditor,
    scheduleModalVisible, setScheduleModalVisible, editingSchedule, setEditingSchedule,
    openScheduleModal, handleSaveSchedule, handleToggleSchedule, handleDeleteSchedule,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
