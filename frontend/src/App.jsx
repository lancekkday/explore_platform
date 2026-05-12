import { useState, useEffect, useRef } from 'react'
import { normalizeKw } from './utils/safeString'
import { IconRefresh } from './components/icons/Icons'
import CompactMetricBar from './components/ui/CompactMetricBar'
import AnnotatedResultList from './components/AnnotatedResultList'
import BaselineAlertBar from './components/BaselineAlertBar'
import ABComparisonSummary from './components/ABComparisonSummary'
import UnifiedSearchBar from './components/UnifiedSearchBar'
import BatchPanel from './components/BatchPanel'
import SettingsPanel from './components/SettingsPanel'
import CalibrationModal from './components/CalibrationModal'
import KeywordEditorModal from './components/KeywordEditorModal'
import ScheduleModal from './components/ScheduleModal'
import {
  fetchGuestCookie, saveFeedback,
  fetchKeywords, updateKeywords,
  startBatch as apiBatchStart, stopBatch as apiBatchStop,
  fetchBatchStatus, fetchBatchResults, fetchBatchHistory,
  fetchBatchHistoryDetail,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
  fetchUnifiedSearch, fetchBaselineKeywords,
} from './api'

export default function App() {
  // ── Search state ──────────────────────────────────────────────────────────
  const [keyword, setKeyword] = useState('esim')
  const [cookie, setCookie] = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [searchApi, setSearchApi] = useState('v3')
  const [aiEnabled, setAiEnabled] = useState(false)
  const [versionA, setVersionA] = useState(0)
  const [versionB, setVersionB] = useState(1)
  const [enableAB, setEnableAB] = useState(true)
  const [doubtOnly, setDoubtOnly] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ── Results state ─────────────────────────────────────────────────────────
  const [versionAData, setVersionAData] = useState(null)
  const [versionBData, setVersionBData] = useState(null)
  const [baselineData, setBaselineData] = useState(null)
  const [abComparison, setAbComparison] = useState(null)
  const [baselineKeywords, setBaselineKeywords] = useState([])

  // ── Calibration ───────────────────────────────────────────────────────────
  const [edittingProduct, setEdittingProduct] = useState(null)
  const [calibTier, setCalibTier] = useState(1)
  const [calibComment, setCalibComment] = useState('')

  // ── Batch state ───────────────────────────────────────────────────────────
  const [showBatch, setShowBatch] = useState(false)
  const [auditKeywords, setAuditKeywords] = useState([])
  const [batchStatus, setBatchStatus] = useState({ is_running: false, progress: 0, current_keyword: null })
  const [batchResults, setBatchResults] = useState({})
  const [batchHistory, setBatchHistory] = useState([])
  const [viewingRunId, setViewingRunId] = useState(null)
  const [liveResults, setLiveResults] = useState(null)
  const viewingRunIdRef = useRef(null)

  // ── UI modals ─────────────────────────────────────────────────────────────
  const [kwEditorVisible, setKwEditorVisible] = useState(false)
  const [kwInputText, setKwInputText] = useState('')
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState(null)
  const [settingsVisible, setSettingsVisible] = useState(false)
  const [schedules, setSchedules] = useState([])

  // ── Functions ─────────────────────────────────────────────────────────────

  async function autoFetchCookie() {
    try {
      const res = await fetchGuestCookie('stage')
      if (res?.cookie) { setCookie(res.cookie); setCookieInfo(res); return res }
      return null
    } catch {
      setError('憑證對接異常')
      return null
    }
  }

  async function fetchAuditData() {
    try {
      const [kwRes, statRes, resRes, histRes, schedRes] = await Promise.all([
        fetchKeywords(), fetchBatchStatus(), fetchBatchResults(),
        fetchBatchHistory(), fetchSchedules(),
      ])
      if (kwRes?.keywords) setAuditKeywords(kwRes.keywords)
      if (statRes) setBatchStatus(statRes)
      if (resRes?.results && !viewingRunIdRef.current) setBatchResults(resRes.results)
      if (histRes?.history) setBatchHistory(histRes.history)
      if (Array.isArray(schedRes)) setSchedules(schedRes)
    } catch { /* silent */ }
  }

  async function handleSearch(kw = keyword) {
    if (!kw?.trim()) return
    setLoading(true)
    setError('')
    try {
      const vb = enableAB ? versionB : null
      const res = await fetchUnifiedSearch(kw, cookie, 300, aiEnabled, searchApi, versionA, vb)
      if (res?.success) {
        setVersionAData(res.version_a)
        setVersionBData(res.version_b || null)
        setBaselineData(res.baseline)
        setAbComparison(res.ab_comparison || null)
      } else {
        setError(res?.detail || '返回數據異常')
      }
    } catch {
      setError('伺服器連線異常')
    }
    setLoading(false)
  }

  const findResult = (kw) => {
    if (!kw || !batchResults) return null
    return batchResults[normalizeKw(kw)] || null
  }

  async function loadArchive(id) {
    try {
      viewingRunIdRef.current = id
      const res = await fetchBatchHistoryDetail(id)
      if (!res?.results) { viewingRunIdRef.current = null; return }
      setLiveResults(prev => prev ?? batchResults)
      setBatchResults(res.results)
      setViewingRunId(id)
      setShowBatch(true)
    } catch { viewingRunIdRef.current = null }
  }

  function exitArchive() {
    viewingRunIdRef.current = null
    setBatchResults(liveResults || {})
    setLiveResults(null)
    setViewingRunId(null)
    fetchAuditData()
  }

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    autoFetchCookie()
    fetchAuditData()
    fetchBaselineKeywords().then(res => {
      if (res?.keywords) setBaselineKeywords(res.keywords)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!batchStatus?.is_running) return
    const timer = setInterval(() => fetchAuditData(), 3000)
    return () => clearInterval(timer)
  }, [batchStatus?.is_running])

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleCalibrate = (p) => {
    if (!p) return
    setEdittingProduct(p)
    setCalibTier(p.user_tier || p.tier || 1)
    setCalibComment(p.user_comment || p.comment || '')
  }

  const submitCalibration = async () => {
    if (!edittingProduct) return
    try {
      const res = await saveFeedback(keyword, edittingProduct.id, parseInt(calibTier), calibComment)
      if (res.success) { setEdittingProduct(null); handleSearch() }
    } catch { /* silent */ }
  }

  const handleStartBatch = async () => {
    const vb = enableAB ? versionB : null
    await apiBatchStart(cookie, searchApi, versionA, vb)
    fetchAuditData()
  }
  const handleStopBatch = async () => {
    await apiBatchStop()
    fetchAuditData()
  }

  const saveKeywords = async () => {
    const kws = kwInputText.split(/\n|,/).map(s => s.trim()).filter(s => s)
    await updateKeywords(kws)
    setKwEditorVisible(false)
    fetchAuditData()
  }

  const handleSaveSchedule = async (config) => {
    try {
      if (config.id) {
        await updateSchedule(config.id, config)
      } else {
        await addSchedule(config)
      }
      setScheduleModalVisible(false)
      setEditingSchedule(null)
      fetchAuditData()
    } catch (e) {
      alert(`儲存失敗: ${e?.message || e}`)
    }
  }

  const handleToggleSchedule = async (s) => {
    await updateSchedule(s.id, { enabled: s.enabled ? 0 : 1 })
    fetchAuditData()
  }

  const handleDeleteSchedule = async (id) => {
    await deleteSchedule(id)
    fetchAuditData()
  }

  // ── Export ───────────────────────────────────────────────────────────────

  function handleExportCSV() {
    if (!versionAData) return
    const tierLabel = (t) => ({ 1: 'T1', 2: 'T2', 3: 'T3', 0: 'MISS' }[t] || `T${t}`)
    const getDest = (it) => {
      const dests = Array.isArray(it.destinations) ? it.destinations : []
      if (dests.length === 0) return ''
      const first = dests[0]
      return typeof first === 'object' ? (first.name || '') : String(first)
    }
    const esc = (v) => {
      let s = String(v ?? '')
      if (/^[=+\-@]/.test(s)) s = `'${s}`
      return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
    }

    const headers = ['版本', '排名', '商品ID', '商品名稱', '商品連結', '類別', '地點', 'Tier', '判定原因', 'Baseline標記', 'Baseline利潤排名', '成交量']
    const rows = [headers.join(',')]

    const addRows = (data, label) => {
      if (!data?.results) return
      for (const it of data.results) {
        rows.push([
          label,
          it.rank,
          it.prod_mid || it.id,
          esc(it.name),
          it.prod_mid ? `https://www.stage.kkday.com/zh-tw/product/${it.prod_mid}` : '',
          it.main_cat_key || '',
          esc(getDest(it)),
          tierLabel(it.tier),
          esc((it.mismatch_reasons || []).join(' | ')),
          it.baseline_tag || '',
          it.baseline_profit_rank ?? '',
          it.show_order_count || '',
        ].join(','))
      }
    }

    addRows(versionAData, `Version A (v${versionAData.test_exp})`)
    if (versionBData) addRows(versionBData, `Version B (v${versionBData.test_exp})`)

    const bom = '\uFEFF'
    const blob = new Blob([bom + rows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const date = new Date().toISOString().slice(0, 10)
    a.href = url
    a.download = `巡檢_${keyword}_v${versionAData.test_exp}${versionBData ? `_v${versionBData.test_exp}` : ''}_${date}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const hasResults = !!versionAData

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col h-screen overflow-hidden text-[13px] select-none text-slate-900 antialiased font-sans">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 px-8 py-2.5 flex items-center justify-between shrink-0 z-[100] shadow-sm">
        <div className="flex flex-col text-slate-950">
          <span className="text-[13px] font-black tracking-[4px] uppercase leading-none">搜尋巡檢平台</span>
          <span className="text-[8px] font-black text-indigo-600 uppercase tracking-[3px] mt-1 font-mono">Search Audit Platform</span>
        </div>
        <div className="flex items-center gap-5 text-[10px] font-black">
          {error && <div className="px-3 py-1 bg-red-50 text-red-600 border border-red-100 rounded-lg animate-pulse">{error}</div>}
          <div className="flex items-center gap-3 px-4 py-1.5 bg-slate-50 border border-slate-200 rounded-full">
            <div className={`w-1.5 h-1.5 rounded-full ${cookieInfo ? 'bg-emerald-500 shadow-[0_0_8px_#10B981]' : 'bg-red-500'}`} />
            <span className="text-slate-500 tracking-wider uppercase font-mono">{cookieInfo ? '連線正常' : '連線斷開'}</span>
          </div>
          <button onClick={autoFetchCookie} className="text-slate-300 hover:text-indigo-600 transition-all active:rotate-180 duration-500"><IconRefresh /></button>
        </div>
      </header>

      {/* Search bar */}
      <UnifiedSearchBar
        keyword={keyword} setKeyword={setKeyword}
        versionA={versionA} setVersionA={setVersionA}
        versionB={versionB} setVersionB={setVersionB}
        enableAB={enableAB} setEnableAB={setEnableAB}
        searchApi={searchApi} setSearchApi={setSearchApi}
        aiEnabled={aiEnabled} setAiEnabled={setAiEnabled}
        loading={loading} cookieInfo={cookieInfo}
        baselineKeywords={baselineKeywords}
        onSearch={handleSearch}
        onOpenSettings={() => setSettingsVisible(true)}
        hasResults={hasResults}
        doubtOnly={doubtOnly} setDoubtOnly={setDoubtOnly}
        onExportCSV={handleExportCSV}
      />

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden bg-[#F8FAFC]">
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-[4px] border-white/10 border-t-indigo-600 rounded-full animate-spin shadow-2xl" />
            <div className="text-indigo-900 font-black text-[11px] tracking-[6px] animate-pulse uppercase">
              {enableAB ? 'Comparing A vs B...' : 'Analyzing...'}
            </div>
          </div>
        )}

        {!loading && hasResults && (
          <div className="flex-1 flex flex-col overflow-hidden p-4 gap-3">
            {/* Metrics + Baseline alerts */}
            <div className="flex gap-3 shrink-0">
              <div className="flex-1">
                <CompactMetricBar data={versionAData} env={`Version A (v${versionAData.test_exp})`} envCode="A" color="#10B981" />
              </div>
              {versionBData && (
                <div className="flex-1">
                  <CompactMetricBar data={versionBData} env={`Version B (v${versionBData.test_exp})`} envCode="B" color="#6366F1" />
                </div>
              )}
            </div>

            <BaselineAlertBar alerts={versionAData.baseline_alerts} baseline={baselineData} />

            {/* AB Comparison summary */}
            {abComparison && <ABComparisonSummary comparison={abComparison} />}

            {/* Product lists */}
            <div className={`flex-1 flex ${versionBData ? 'gap-3' : ''} overflow-hidden`}>
              <AnnotatedResultList
                items={versionAData.results}
                title={versionBData ? 'Version A' : 'STAGE 巡檢清單'}
                total={versionAData.total || 0}
                color={versionBData ? '#10B981' : '#10B981'}
                onCalibrate={handleCalibrate}
                doubtOnly={doubtOnly}
                keyword={keyword}
                versionLabel={versionBData ? `v${versionAData.test_exp}` : null}
                otherVersionResults={versionBData?.results}
              />
              {versionBData && (
                <AnnotatedResultList
                  items={versionBData.results}
                  title="Version B"
                  total={versionBData.total || 0}
                  color="#6366F1"
                  onCalibrate={handleCalibrate}
                  doubtOnly={doubtOnly}
                  keyword={keyword}
                  versionLabel={`v${versionBData.test_exp}`}
                  otherVersionResults={versionAData?.results}
                />
              )}
            </div>
          </div>
        )}

        {!loading && !hasResults && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-slate-200 text-[48px] mb-4">🔍</div>
              <div className="text-slate-400 font-black text-[12px] tracking-widest uppercase">輸入關鍵字開始巡檢</div>
              <div className="text-slate-300 text-[10px] mt-2 font-bold">搜尋結果將自動標註 baseline 守門商品</div>
              {enableAB && <div className="text-indigo-400 text-[10px] mt-1 font-bold">A/B 模式已啟用 — 將同時比對兩個版本</div>}
            </div>
          </div>
        )}
      </main>

      {/* Batch panel (collapsible bottom) */}
      <BatchPanel
        showBatch={showBatch} setShowBatch={setShowBatch}
        auditKeywords={auditKeywords}
        batchStatus={batchStatus}
        batchResults={batchResults}
        batchHistory={batchHistory}
        viewingRunId={viewingRunId}
        onLoadArchive={loadArchive}
        onExitArchive={exitArchive}
        onStartBatch={handleStartBatch}
        onStopBatch={handleStopBatch}
        findResult={findResult}
      />

      {/* Modals */}
      <SettingsPanel
        visible={settingsVisible}
        onClose={() => setSettingsVisible(false)}
        versionA={versionA} setVersionA={setVersionA}
        versionB={versionB} setVersionB={setVersionB}
        enableAB={enableAB} setEnableAB={setEnableAB}
        searchApi={searchApi} setSearchApi={setSearchApi}
        aiEnabled={aiEnabled} setAiEnabled={setAiEnabled}
        cookieInfo={cookieInfo}
        onRefreshCookie={autoFetchCookie}
        onOpenKeywordEditor={() => { setKwInputText(auditKeywords.map(k => k.keyword).join(', ')); setKwEditorVisible(true) }}
        onOpenScheduleModal={() => { setEditingSchedule(null); setScheduleModalVisible(true) }}
        schedules={schedules}
      />
      <CalibrationModal
        product={edittingProduct}
        calibTier={calibTier}
        calibComment={calibComment}
        onTierChange={setCalibTier}
        onCommentChange={setCalibComment}
        onSubmit={submitCalibration}
        onClose={() => setEdittingProduct(null)}
      />
      <KeywordEditorModal
        visible={kwEditorVisible}
        kwInputText={kwInputText}
        onInputChange={setKwInputText}
        onSave={saveKeywords}
        onClose={() => setKwEditorVisible(false)}
      />
      <ScheduleModal
        visible={scheduleModalVisible}
        schedule={editingSchedule}
        onSave={handleSaveSchedule}
        onClose={() => { setScheduleModalVisible(false); setEditingSchedule(null) }}
      />
    </div>
  )
}
