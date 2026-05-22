import { createContext, useContext, useEffect, useRef, useState } from 'react'
import {
  fetchGuestCookie,
  fetchKeywords, updateKeywords,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
  fetchBaselineKeywords,
  runABCheck,
  startABCheckRun, getABCheckStatus, cancelABCheckRun,
} from '../api'
import { aggregateAlerts } from '../utils/baselineReport'

const POLL_INTERVAL_MS = 2000

function emptyRun() {
  // rowsMap: idx → checkpoint row (live state)
  return { runId: null, status: null, total: 0, doneCount: 0,
           runningIdx: null, rowsMap: new Map(), sinceIdx: 0, error: null }
}

const TERMINAL = new Set(['done', 'failed', 'cancelled', 'interrupted'])

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

  // ── Cookie / connection ──────────────────────────────────────────────────
  const [cookie, setCookie] = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [cookieError, setCookieError] = useState('')

  // ── Baseline metadata ────────────────────────────────────────────────────
  const [baselineKeywords, setBaselineKeywords] = useState([])
  const [baselineCounts, setBaselineCounts] = useState({ precise: 0, broad: 0 })
  const [baselineDropMultiplier, setBaselineDropMultiplier] = useState(3)

  // ── Audit (batch) keyword list + schedules ───────────────────────────────
  const [auditKeywords, setAuditKeywords] = useState([])
  const [schedules, setSchedules] = useState([])

  // ── Batch baseline run (lives in context so promise survives page navigation) ─
  const [baselineReport, setBaselineReport] = useState(null)
  const [baselineRunning, setBaselineRunning] = useState(false)
  const [baselineError, setBaselineError] = useState(null)
  // Toast trigger:running→done 過渡時 set true,Toast 顯示完 set false
  const [batchJustCompleted, setBatchJustCompleted] = useState(false)

  // ── New AB-check runner state (polled, survives tab switch) ───────────────
  const [preciseRun, setPreciseRun] = useState(emptyRun)
  const [broadRun, setBroadRun] = useState(emptyRun)
  const pollTimers = useRef({ precise: null, broad: null })

  const setRunFor = (type) => (type === 'precise' ? setPreciseRun : setBroadRun)
  const getRunFor = (type, snapshot) => (type === 'precise' ? snapshot.precise : snapshot.broad)

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
    let snapshot
    try {
      // 用 functional setState 拿到當前 sinceIdx,避免 closure 鎖住舊值
      snapshot = await new Promise((resolve) => {
        const setter = setRunFor(type)
        setter(prev => { resolve(prev); return prev })
      })
      if (snapshot.runId !== runId) {
        // run 被 reset / 換新 run,這次 polling 是 stale
        return
      }
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
    clearPollTimer(type)
    const setter = setRunFor(type)
    setter({ ...emptyRun(), status: 'starting' })
    try {
      const limitN = (limit == null || limit === '' || isNaN(limit)) ? null : Math.max(1, parseInt(limit, 10))
      const startRes = await startABCheckRun(type, versionA, versionB, cookie, limitN, resumeRunId)
      if (!startRes?.run_id) {
        setter({ ...emptyRun(), error: startRes?.detail || '啟動失敗' })
        return null
      }
      const runId = startRes.run_id
      setter({
        runId,
        status: startRes.status,
        total: startRes.total_queries,
        doneCount: 0,
        runningIdx: null,
        rowsMap: new Map(),
        sinceIdx: 0,
        error: null,
      })
      // 立刻拉一次 status 把 pending rows 渲染出來,再開始 2s polling
      await pollRunOnce(type, runId)
      startPolling(type, runId)
      return runId
    } catch (e) {
      setter({ ...emptyRun(), error: e?.message || '伺服器連線異常' })
      return null
    }
  }

  async function cancelRun(type) {
    const cur = type === 'precise' ? preciseRun : broadRun
    if (!cur.runId) return
    try {
      await cancelABCheckRun(cur.runId)
      // 不主動停 polling — backend status 變 cancelled 時 pollRunOnce 自己會 clearPollTimer
    } catch (e) {
      console.warn('[AB cancel] failed:', e?.message)
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

  async function runBaselineCheck() {
    setBaselineRunning(true)
    setBaselineError(null)
    try {
      const res = await runABCheck(versionA, versionB, cookie, false, false)
      if (res?.success) {
        setBaselineReport(aggregateAlerts(res.alerts || []))
        setBatchJustCompleted(true)
      } else {
        setBaselineError(res?.detail || '巡檢失敗')
      }
    } catch (e) {
      setBaselineError(e?.message || '伺服器連線異常')
    }
    setBaselineRunning(false)
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
    // Cookie
    cookie, cookieInfo, cookieError, autoFetchCookie,
    // Baseline metadata
    baselineKeywords, baselineCounts, baselineDropMultiplier, setBaselineDropMultiplier,
    // Audit
    auditKeywords, fetchAuditData,
    schedules,
    // Batch run state (legacy sync — kept until step 9 removal)
    baselineReport, baselineRunning, baselineError, runBaselineCheck,
    batchJustCompleted, setBatchJustCompleted,
    // New async AB-check runs (polled)
    preciseRun, broadRun, startRun, cancelRun, resetRun,
    // Modal state
    settingsVisible, setSettingsVisible,
    kwEditorVisible, setKwEditorVisible, kwInputText, setKwInputText, saveKeywords, openKeywordEditor,
    scheduleModalVisible, setScheduleModalVisible, editingSchedule, setEditingSchedule,
    openScheduleModal, handleSaveSchedule, handleToggleSchedule, handleDeleteSchedule,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
