import { createContext, useContext, useEffect, useState } from 'react'
import {
  fetchGuestCookie,
  fetchKeywords, updateKeywords,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
  fetchBaselineKeywords,
  runABCheck,
} from '../api'
import { aggregateAlerts } from '../utils/baselineReport'

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
      alert(`儲存失敗: ${e?.message || e}`)
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
    // Batch run state
    baselineReport, baselineRunning, baselineError, runBaselineCheck,
    batchJustCompleted, setBatchJustCompleted,
    // Modal state
    settingsVisible, setSettingsVisible,
    kwEditorVisible, setKwEditorVisible, kwInputText, setKwInputText, saveKeywords, openKeywordEditor,
    scheduleModalVisible, setScheduleModalVisible, editingSchedule, setEditingSchedule,
    openScheduleModal, handleSaveSchedule, handleToggleSchedule, handleDeleteSchedule,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
