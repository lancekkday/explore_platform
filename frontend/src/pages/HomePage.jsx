import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AnnotatedResultList from '../components/AnnotatedResultList'
import BaselineAlertBar from '../components/BaselineAlertBar'
import MidWarningBar from '../components/MidWarningBar'
import UnifiedSearchBar from '../components/UnifiedSearchBar'
import FilterBar from '../components/FilterBar'
import Drawer from '../components/Drawer'
import LegendBar from '../components/LegendBar'
import CalibrationModal from '../components/CalibrationModal'
import { fetchUnifiedSearch, saveFeedback } from '../api'
import { prodMatchKey } from '../utils/prodMid'
import { useAppContext } from '../context/AppContext'

export default function HomePage() {
  const ctx = useAppContext()
  const {
    versionA, setVersionA, versionB, setVersionB, enableAB,
    cookie, searchApi, aiEnabled,
    baselineKeywords,
    baselineDropMultiplier, setBaselineDropMultiplier,
    setSettingsVisible,
    // i18n / channel (lang+locale picked on this page; channel from settings)
    lang, setLang, locale, setLocale, channel,
    // Cross-route persistent search state (so coming back from /batch
    // restores the last keyword + results instead of resetting to 'esim').
    homeKeyword, setHomeKeyword,
    homeFilterMode, setHomeFilterMode,
    homeResults, setHomeResults,
  } = ctx

  const keyword = homeKeyword
  const setKeyword = setHomeKeyword
  const filterMode = homeFilterMode
  const setFilterMode = setHomeFilterMode
  const versionAData = homeResults.versionA
  const versionBData = homeResults.versionB
  const baselineData = homeResults.baseline
  const abComparison = homeResults.abComparison
  const requestId = homeResults.requestId

  // ── Local state (transient — UI-only, no cross-route survival) ───────────
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerType, setDrawerType] = useState(null)
  const [highlightId, setHighlightId] = useState(null)
  const rowRefs = useRef({})

  // Calibration modal state
  const [edittingProduct, setEdittingProduct] = useState(null)
  const [calibTier, setCalibTier] = useState(1)
  const [calibComment, setCalibComment] = useState('')
  const [calibSynonyms, setCalibSynonyms] = useState('')

  // ── URL params: cross-page navigation (BatchPage -> /?keyword=X&filter=diff) ─
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const kw = searchParams.get('keyword')
    if (kw) {
      setKeyword(kw)
      setFilterMode(searchParams.get('filter') || 'all')
      // Clear previous keyword's results immediately — otherwise the loading
      // gap (1-3s) shows the *old* products labelled with the *new* keyword.
      setHomeResults({ versionA: null, versionB: null, baseline: null, abComparison: null, requestId: null })
      handleSearch(kw)
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSearch(kw = keyword) {
    if (!kw?.trim()) return
    setLoading(true)
    setError('')
    try {
      const vb = enableAB ? versionB : null
      const res = await fetchUnifiedSearch(kw, cookie, 300, aiEnabled, searchApi, versionA, vb, lang, locale, channel)
      if (res?.success) {
        setHomeResults({
          versionA: res.version_a,
          versionB: res.version_b || null,
          baseline: res.baseline,
          abComparison: res.ab_comparison || null,
          requestId: res.request_id || null,
        })
        if (res.baseline_drop_multiplier != null) setBaselineDropMultiplier(res.baseline_drop_multiplier)
      } else {
        setError(res?.detail || '返回數據異常')
      }
    } catch {
      setError('伺服器連線異常')
    }
    setLoading(false)
  }

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
      // Cross-version rank-delta match keys on a valid prod_mid only (same backend
      // 0-sentinel contract as the result columns) — never fall back to `id`.
      const matchKey = prodMatchKey(it)
      if (matchKey != null) {
        const aMatch = aItems.find(r => prodMatchKey(r) === matchKey)
        const bMatch = bItems.find(r => prodMatchKey(r) === matchKey)
        if (aMatch && bMatch && Math.abs(aMatch.rank - bMatch.rank) >= 5) focus.add(mid)
      }
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

  return (
    <>
      <div className="pt-2">
        <UnifiedSearchBar
          keyword={keyword} setKeyword={setKeyword}
          loading={loading} cookieInfo={ctx.cookieInfo}
          baselineKeywords={baselineKeywords}
          onSearch={handleSearch}
          onOpenSettings={() => setSettingsVisible(true)}
          hasResults={hasResults}
          onExportCSV={handleExportCSV}
          lang={lang} setLang={setLang}
          locale={locale} setLocale={setLocale}
        />
      </div>

      {hasResults && (
        <div className="px-2">
          <MidWarningBar
            aWarnings={versionAData?.mid_warnings}
            bWarnings={versionBData?.mid_warnings}
          />
          <BaselineAlertBar
            aAlerts={versionAData?.baseline_alerts}
            bAlerts={versionBData?.baseline_alerts}
            abComparison={abComparison}
            baseline={baselineData}
            onChipClick={handleChipJump}
          />
        </div>
      )}

      {hasResults && (
        <FilterBar
          filterMode={filterMode}
          setFilterMode={setFilterMode}
          totalCount={totalCount}
          diffCount={diffCount}
          focusCount={focusCount}
          requestId={requestId}
        />
      )}

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
                baselineAlerts={versionAData?.baseline_alerts}
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
                  baselineAlerts={versionBData?.baseline_alerts}
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
              {error && <div className="mt-3 text-rose-500 text-[10px]">{error}</div>}
            </div>
          </div>
        )}
      </main>

      {hasResults && <LegendBar filterMode={filterMode} />}

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
    </>
  )
}
