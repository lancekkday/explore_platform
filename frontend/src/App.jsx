import { useState, useEffect, useRef, useMemo } from 'react'
import { IconRefresh } from './components/icons/Icons'
import AnnotatedResultList from './components/AnnotatedResultList'
import BaselineAlertBar from './components/BaselineAlertBar'
import UnifiedSearchBar from './components/UnifiedSearchBar'
import FilterBar from './components/FilterBar'
import Drawer from './components/Drawer'
import LegendBar from './components/LegendBar'
import BatchPanel from './components/BatchPanel'
import SettingsPanel from './components/SettingsPanel'
import CalibrationModal from './components/CalibrationModal'
import KeywordEditorModal from './components/KeywordEditorModal'
import ScheduleModal from './components/ScheduleModal'
import { aggregateAlerts } from './utils/baselineReport'
import {
  fetchGuestCookie, saveFeedback,
  fetchKeywords, updateKeywords,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
  fetchUnifiedSearch, fetchBaselineKeywords,
  runABCheck,
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

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ── Results state ─────────────────────────────────────────────────────────
  const [versionAData, setVersionAData] = useState(null)
  const [versionBData, setVersionBData] = useState(null)
  const [baselineData, setBaselineData] = useState(null)
  const [abComparison, setAbComparison] = useState(null)
  const [baselineKeywords, setBaselineKeywords] = useState([])
  const [baselineDropMultiplier, setBaselineDropMultiplier] = useState(3)

  // ── New layout state ──────────────────────────────────────────────────────
  const [filterMode, setFilterMode] = useState('all') // 'all' | 'diff' | 'focus'
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerType, setDrawerType] = useState(null)  // 'exact' | 'broad' | null
  const [highlightId, setHighlightId] = useState(null)
  const rowRefs = useRef({})

  // ── Calibration ───────────────────────────────────────────────────────────
  const [edittingProduct, setEdittingProduct] = useState(null)
  const [calibTier, setCalibTier] = useState(1)
  const [calibComment, setCalibComment] = useState('')
  const [calibSynonyms, setCalibSynonyms] = useState('')

  // ── Baseline batch check state ────────────────────────────────────────────
  const [showBatch, setShowBatch] = useState(false)
  const [baselineReport, setBaselineReport] = useState(null)
  const [baselineRunning, setBaselineRunning] = useState(false)
  const [baselineError, setBaselineError] = useState(null)
  const [baselineCounts, setBaselineCounts] = useState({ precise: 0, broad: 0 })
  const [auditKeywords, setAuditKeywords] = useState([])    // used by keyword editor modal

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
      const [kwRes, schedRes] = await Promise.all([fetchKeywords(), fetchSchedules()])
      if (kwRes?.keywords) setAuditKeywords(kwRes.keywords)
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
        if (res.baseline_drop_multiplier != null) setBaselineDropMultiplier(res.baseline_drop_multiplier)
      } else {
        setError(res?.detail || '返回數據異常')
      }
    } catch {
      setError('伺服器連線異常')
    }
    setLoading(false)
  }

  async function runBaselineCheck() {
    setBaselineRunning(true)
    setBaselineError(null)
    try {
      const res = await runABCheck(versionA, versionB, cookie, false, false)
      if (res?.success) {
        setBaselineReport(aggregateAlerts(res.alerts || []))
      } else {
        setBaselineError(res?.detail || '巡檢失敗')
      }
    } catch (e) {
      setBaselineError(e?.message || '伺服器連線異常')
    }
    setBaselineRunning(false)
  }

  function jumpToKeyword(kw) {
    if (!kw) return
    setKeyword(kw)
    setFilterMode('diff')
    setShowBatch(false)
    handleSearch(kw)
  }

  // ── Effects ───────────────────────────────────────────────────────────────

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

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleCalibrate = (p) => {
    if (!p) return
    setEdittingProduct(p)
    setCalibTier(p.user_tier || p.tier || 1)
    setCalibComment(p.user_comment || p.comment || '')
    setCalibSynonyms('')
  }

  const submitCalibration = async () => {
    if (!edittingProduct) return
    try {
      const synonyms = calibSynonyms.split(/[,，]/).map(s => s.trim()).filter(s => s)
      const res = await saveFeedback(keyword, edittingProduct.id, parseInt(calibTier), calibComment, synonyms.length ? synonyms : undefined)
      if (res.success) { setEdittingProduct(null); handleSearch() }
    } catch { /* silent */ }
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

  // ── Export ────────────────────────────────────────────────────────────────

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

  // ── Derived data ──────────────────────────────────────────────────────────

  const hasResults = !!versionAData

  // Baseline 守門商品 Map：合併精準 (Top1/Top2) + 泛詞 (#1~#10)
  const baselineMap = useMemo(() => {
    const m = new Map()
    const p = baselineData?.precise
    if (p?.top1_prod_mid) m.set(p.top1_prod_mid, {
      label: 'Top1', kind: 'precise',
      original: { prod_mid: p.top1_prod_mid, prod_nm: p.top1_prod_nm },
    })
    if (p?.top2_prod_mid) m.set(p.top2_prod_mid, {
      label: 'Top2', kind: 'precise',
      original: { prod_mid: p.top2_prod_mid, prod_nm: p.top2_prod_nm },
    })
    for (const b of baselineData?.broad_products || []) {
      m.set(b.prod_mid, {
        label: `泛#${b.profit_rank}`, kind: 'broad',
        original: { prod_mid: b.prod_mid, prod_nm: b.prod_nm, profit_rank: b.profit_rank },
      })
    }
    return m
  }, [baselineData])

  const { totalCount, focusCount, focusIds } = useMemo(() => {
    const aItems = versionAData?.results || []
    const bItems = versionBData?.results || []
    // Focus: T3/MISS, calibrated, baseline-drop, large rank delta (≥5)
    const focus = new Set()
    const both = [...aItems, ...bItems]
    for (const it of both) {
      const mid = it.prod_mid || it.id
      if (!mid) continue
      if (it.tier === 0 || it.tier === 3) { focus.add(mid); continue }
      if (it.is_calibrated) { focus.add(mid); continue }
      if (it.baseline_tag && it.baseline_profit_rank && it.rank > it.baseline_profit_rank * baselineDropMultiplier) {
        focus.add(mid); continue
      }
      const aMatch = aItems.find(r => (r.prod_mid || r.id) === mid)
      const bMatch = bItems.find(r => (r.prod_mid || r.id) === mid)
      if (aMatch && bMatch && Math.abs(aMatch.rank - bMatch.rank) >= 5) focus.add(mid)
    }
    return {
      totalCount: Math.max(aItems.length, bItems.length),
      focusCount: focus.size,
      focusIds: focus,
    }
  }, [versionAData, versionBData, baselineDropMultiplier])

  const diffCount = baselineMap.size

  const preciseItems = useMemo(() => {
    const p = baselineData?.precise
    if (!p) return []
    const out = []
    if (p.top1_prod_mid) out.push({ name: p.top1_prod_nm, prod_mid: p.top1_prod_mid })
    if (p.top2_prod_mid) out.push({ name: p.top2_prod_nm, prod_mid: p.top2_prod_mid })
    return out
  }, [baselineData])

  const broadItems = useMemo(() => baselineData?.broad_products || [], [baselineData])

  const handleChipJump = (alert) => {
    const id = alert.prod_mid
    setHighlightId(id)
    const candidate = rowRefs.current[`B:${id}`] || rowRefs.current[`A:${id}`]
    if (candidate?.scrollIntoView) {
      candidate.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setTimeout(() => setHighlightId(null), 1800)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#F8FAFC] text-slate-900 text-[13px]">
      {/* Brand strip */}
      <header className="bg-white border-b border-slate-200 px-4 py-1.5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 text-slate-950">
          <span className="text-[11px] font-bold tracking-[3px] uppercase leading-none">搜尋巡檢平台</span>
          <span className="text-[8px] font-bold text-indigo-600 uppercase tracking-[2px] font-mono">Search Audit</span>
        </div>
        <div className="flex items-center gap-2 text-[10px]">
          {error && <div className="px-2 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded">{error}</div>}
          <div className="flex items-center gap-1.5 px-2 py-0.5 bg-slate-50 border border-slate-200 rounded-full">
            <div className={`w-1.5 h-1.5 rounded-full ${cookieInfo ? 'bg-emerald-500' : 'bg-red-500'}`} />
            <span className="text-slate-500 uppercase tracking-wide font-mono">{cookieInfo ? '連線正常' : '連線斷開'}</span>
          </div>
          <button onClick={autoFetchCookie} className="text-slate-300 hover:text-indigo-600">
            <IconRefresh />
          </button>
        </div>
      </header>

      {/* Topbar (search + 巡檢 + 下載 + 設定) */}
      <div className="pt-2">
        <UnifiedSearchBar
          keyword={keyword} setKeyword={setKeyword}
          loading={loading} cookieInfo={cookieInfo}
          baselineKeywords={baselineKeywords}
          onSearch={handleSearch}
          onOpenSettings={() => setSettingsVisible(true)}
          hasResults={hasResults}
          onExportCSV={handleExportCSV}
        />
      </div>

      {/* Alert bar */}
      {hasResults && (
        <div className="px-2">
          <BaselineAlertBar
            aAlerts={versionAData?.baseline_alerts}
            bAlerts={versionBData?.baseline_alerts}
            abComparison={abComparison}
            baseline={baselineData}
            onChipClick={handleChipJump}
          />
        </div>
      )}

      {/* Filter bar */}
      {hasResults && (
        <FilterBar
          filterMode={filterMode}
          setFilterMode={setFilterMode}
          totalCount={totalCount}
          diffCount={diffCount}
          focusCount={focusCount}
        />
      )}

      {/* Main content */}
      <main className="flex-1 flex overflow-hidden">
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="w-7 h-7 border-[3px] border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
            <div className="text-slate-500 text-[11px] tracking-widest uppercase">
              {enableAB ? '比對 A / B 版本中…' : '分析中…'}
            </div>
          </div>
        )}

        {!loading && hasResults && (
          <>
            <div className="flex-1 flex gap-2 px-2 min-w-0">
              <AnnotatedResultList
                column="A"
                data={versionAData}
                version={String(versionA)}
                onVersionChange={(s) => {
                  if (s === '') { setVersionA(0); return }
                  const n = parseInt(s, 10)
                  if (Number.isFinite(n)) setVersionA(n)
                }}
                onSubmit={() => handleSearch()}
                filterMode={filterMode}
                focusIds={focusIds}
                baselineMap={baselineMap}
                otherResults={versionBData?.results}
                onCalibrate={handleCalibrate}
                keyword={keyword}
                rowRefs={rowRefs}
                highlightId={highlightId}
              />
              {versionBData && (
                <AnnotatedResultList
                  column="B"
                  data={versionBData}
                  version={String(versionB)}
                  onVersionChange={(s) => {
                    if (s === '') { setVersionB(0); return }
                    const n = parseInt(s, 10)
                    if (Number.isFinite(n)) setVersionB(n)
                  }}
                  onSubmit={() => handleSearch()}
                  filterMode={filterMode}
                  focusIds={focusIds}
                  baselineMap={baselineMap}
                  otherResults={versionAData?.results}
                  onCalibrate={handleCalibrate}
                  keyword={keyword}
                  rowRefs={rowRefs}
                  highlightId={highlightId}
                />
              )}
            </div>
            <Drawer
              drawerOpen={drawerOpen}
              drawerType={drawerType}
              setDrawerOpen={setDrawerOpen}
              setDrawerType={setDrawerType}
              preciseItems={preciseItems}
              broadItems={broadItems}
            />
          </>
        )}

        {!loading && !hasResults && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-slate-300 text-[36px] mb-3">🔍</div>
              <div className="text-slate-500 font-semibold text-[12px] tracking-widest uppercase">輸入關鍵字開始巡檢</div>
              <div className="text-slate-400 text-[10px] mt-2">搜尋結果將自動標註 baseline 守門商品</div>
            </div>
          </div>
        )}
      </main>

      {/* Legend bar */}
      {hasResults && <LegendBar filterMode={filterMode} />}

      {/* Batch baseline check panel (collapsible bottom) */}
      <BatchPanel
        showBatch={showBatch}
        setShowBatch={setShowBatch}
        versionA={versionA}
        versionB={versionB}
        baselineReport={baselineReport}
        baselineRunning={baselineRunning}
        baselineCounts={baselineCounts}
        onRun={runBaselineCheck}
        onJumpToKeyword={jumpToKeyword}
        error={baselineError}
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
        onToggleSchedule={handleToggleSchedule}
        onDeleteSchedule={handleDeleteSchedule}
      />
      <CalibrationModal
        product={edittingProduct}
        calibTier={calibTier}
        calibComment={calibComment}
        calibSynonyms={calibSynonyms}
        onTierChange={setCalibTier}
        onCommentChange={setCalibComment}
        onSynonymsChange={setCalibSynonyms}
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
