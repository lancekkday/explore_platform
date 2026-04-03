import { useState, useEffect, useCallback } from 'react'

// ─── SVG Icons (Lucide-style, no emoji) ──────────────────────────────────────
const IconMapPin = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>
  </svg>
)
const IconTag = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2H2v10l9.29 9.29a1 1 0 0 0 1.41 0l7.3-7.3a1 1 0 0 0 0-1.41Z"/><path d="M7 7h.01"/>
  </svg>
)
const IconArrowUp = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="m18 15-6-6-6 6"/>
  </svg>
)
const IconArrowDown = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="m6 9 6 6 6-6"/>
  </svg>
)
const IconMinus = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M5 12h14"/></svg>
)
const IconX = ({ size = 12 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
)
const IconRefresh = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>
  </svg>
)
const IconSearch = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
  </svg>
)
const IconShield = ({ ok }) => ok ? (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>
  </svg>
) : (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v4m0 4h.01"/>
  </svg>
)

// ─── Tier Badge ───────────────────────────────────────────────────────────────
function TierBadge({ p }) {
  const { tier, mismatch_reasons = [], cat_match, dest_match } = p
  const base = 'inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-semibold rounded border leading-none whitespace-nowrap'
  if (tier === 1) return <span className={`${base} bg-emerald-50 text-emerald-700 border-emerald-200`}>T1</span>
  if (tier === 2) return <span className={`${base} bg-amber-50 text-amber-700 border-amber-200`}>T2</span>
  if (tier === 3) return (
    <span className="inline-flex items-center gap-1">
      <span className={`${base} bg-orange-50 text-orange-700 border-orange-200`}>T3</span>
      {cat_match === 'none' && <span className={`${base} bg-orange-50 text-orange-500 border-orange-200`}>分類偏</span>}
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      <span className={`${base} bg-red-50 text-red-700 border-red-200`}>Miss</span>
      {!dest_match && <span className={`${base} bg-red-50 text-red-500 border-red-200`} title={mismatch_reasons.find(r => r.startsWith('地點'))}>地點</span>}
      {cat_match === 'none' && <span className={`${base} bg-pink-50 text-pink-500 border-pink-200`} title={mismatch_reasons.find(r => r.startsWith('分類'))}>分類</span>}
    </span>
  )
}

// ─── Rank Delta ───────────────────────────────────────────────────────────────
function RankDelta({ delta }) {
  if (delta == null) return null
  if (delta > 0) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-emerald-600 shrink-0" title={`Stage 前進 ${delta} 位`}>
      <IconArrowUp />{delta}
    </span>
  )
  if (delta < 0) return (
    <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-red-500 shrink-0" title={`Stage 退後 ${Math.abs(delta)} 位`}>
      <IconArrowDown />{Math.abs(delta)}
    </span>
  )
  return <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400 shrink-0"><IconMinus /></span>
}

// ─── NDCG Gauge ───────────────────────────────────────────────────────────────
function NdcgGauge({ value, label }) {
  const pct = Math.round((value ?? 0) * 100)
  const stroke = pct >= 70 ? '#059669' : pct >= 40 ? '#D97706' : '#DC2626'
  const dash = `${pct} ${100 - pct}`
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-14 h-14">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#DBEAFE" strokeWidth="3" />
          <circle cx="18" cy="18" r="15.9" fill="none" stroke={stroke}
            strokeWidth="3" strokeDasharray={dash} strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.5s ease' }} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-[11px] font-bold text-slate-700">{pct}%</span>
      </div>
      <span className="text-[10px] text-slate-400 font-medium tracking-tight">{label}</span>
    </div>
  )
}

// ─── Metrics Panel ────────────────────────────────────────────────────────────
function MetricsPanel({ metrics, envLabel, color }) {
  if (!metrics) return null
  const { ndcg_at_10, ndcg_at_50, recall_at_10, recall_at_50, tier_breakdown, mismatch_rate, category_distribution } = metrics
  const tb = tier_breakdown || {}

  return (
    <div className={`rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden`}>
      <div className={`px-3 py-2 border-b border-slate-100 flex items-center justify-between`} style={{ borderLeftWidth: 3, borderLeftColor: color, borderLeftStyle: 'solid' }}>
        <span className="text-xs font-bold text-slate-700 font-['Fira_Sans']">{envLabel}</span>
        <span className="text-[10px] text-slate-400">{tb.total ?? 0} 件</span>
      </div>

      <div className="p-3 space-y-3">
        {/* NDCG */}
        <div className="flex justify-center gap-4">
          <NdcgGauge value={ndcg_at_10} label="NDCG@10" />
          <NdcgGauge value={ndcg_at_50} label="NDCG@50" />
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-2 gap-1.5 text-[10px]">
          {[
            ['Recall@10', recall_at_10 != null ? `${Math.round(recall_at_10 * 100)}%` : '—', '#DBEAFE'],
            ['Recall@50', recall_at_50 != null ? `${Math.round(recall_at_50 * 100)}%` : '—', '#DBEAFE'],
            ['Mismatch', `${Math.round((mismatch_rate ?? 0) * 100)}%`, '#FEE2E2'],
            ['T1/T2/T3', `${tb.tier1 ?? 0}/${tb.tier2 ?? 0}/${tb.tier3 ?? 0}`, '#F0FDF4'],
          ].map(([k, v, bg]) => (
            <div key={k} className="rounded-lg px-2 py-1.5" style={{ background: bg }}>
              <div className="text-slate-400 mb-0.5">{k}</div>
              <div className="font-bold text-slate-700 font-['Fira_Code']">{v}</div>
            </div>
          ))}
        </div>

        {/* Category distribution */}
        {category_distribution?.length > 0 && (
          <div>
            <div className="text-[10px] text-slate-400 mb-1.5 font-medium">分類分佈</div>
            <div className="space-y-1">
              {category_distribution.slice(0, 6).map(({ cat_key, percentage }) => (
                <div key={cat_key} className="flex items-center gap-1.5">
                  <span className="text-[9px] text-slate-500 w-24 truncate shrink-0 font-['Fira_Code']">{cat_key}</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${percentage}%`, background: '#3B82F6' }} />
                  </div>
                  <span className="text-[9px] text-slate-400 w-7 text-right shrink-0 font-['Fira_Code']">{percentage}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Product Card ─────────────────────────────────────────────────────────────
function ProductCard({ p, showDelta }) {
  return (
    <div className="flex gap-2.5 items-start px-2.5 py-2 rounded-lg border border-transparent hover:border-slate-200 hover:bg-slate-50/80 transition-all duration-150 group cursor-default">
      <div className="w-9 h-9 bg-slate-100 rounded-md overflow-hidden shrink-0 mt-0.5 border border-slate-200">
        {p.img_url
          ? <img src={p.img_url} alt="" className="w-full h-full object-cover" loading="lazy" />
          : <div className="w-full h-full flex items-center justify-center text-slate-300"><IconSearch /></div>}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 flex-wrap mb-0.5">
          <span className="text-[10px] font-bold text-white bg-slate-700 px-1.5 py-0.5 rounded-full font-['Fira_Code'] shrink-0">#{p.rank}</span>
          {showDelta && <RankDelta delta={p.rank_delta} />}
          <TierBadge p={p} />
        </div>
        <a href={p.url} target="_blank" rel="noreferrer"
          className="block text-[11px] font-medium text-slate-800 hover:text-blue-600 line-clamp-1 leading-snug transition-colors duration-150 cursor-pointer">
          {p.name}
        </a>
        <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-400">
          <span className="flex items-center gap-0.5"><IconMapPin />{p.destinations.join(', ') || '—'}</span>
          <span className="flex items-center gap-0.5"><IconTag />{p.main_cat_key || '—'}</span>
        </div>
      </div>
    </div>
  )
}

// ─── Product List ─────────────────────────────────────────────────────────────
function ProductList({ data, envTitle, color, onlyIssues, showDelta }) {
  const list = (data.results || []).filter(p => onlyIssues ? (p.tier === 3 || p.tier === null) : true)
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center justify-between pb-2 mb-1 border-b border-slate-100 shrink-0">
        <span className="text-sm font-bold text-slate-800 font-['Fira_Sans']" style={{ color }}>{envTitle}</span>
        <span className="text-[10px] text-slate-400 font-['Fira_Code']">{list.length} / {data.total}</span>
      </div>
      <div className="overflow-y-auto flex-1 -mx-1 px-1 space-y-0.5">
        {list.map(p => <ProductCard key={p.id} p={p} showDelta={showDelta} />)}
        {list.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-slate-400">
            <IconSearch />
            <p className="mt-2 text-xs">無符合篩選條件的商品</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Cookie Status Indicator ──────────────────────────────────────────────────
function CookieStatus({ info, loading, onRefetch, onManual }) {
  const [showManual, setShowManual] = useState(false)
  const [manualVal, setManualVal] = useState('')

  const hasKey = info?.key_fields_found?.length > 0
  const statusColor = !info ? '#94A3B8' : hasKey ? '#059669' : '#D97706'

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="flex items-center gap-1 font-medium" style={{ color: statusColor }}>
        <IconShield ok={hasKey} />
        {!info ? '未取得 Cookie' : `${info.env} · ${info.total_fields} 欄`}
      </span>
      <button onClick={onRefetch} disabled={loading}
        className="flex items-center gap-0.5 px-2 py-0.5 text-[10px] text-slate-500 hover:text-blue-600 border border-slate-200 hover:border-blue-300 rounded-md transition-all duration-150 cursor-pointer disabled:opacity-40">
        <span className={loading ? 'animate-spin' : ''}><IconRefresh /></span>
        {loading ? '取得中…' : '自動取得'}
      </button>
      <button onClick={() => setShowManual(v => !v)}
        className="text-[10px] text-slate-400 hover:text-slate-600 transition-colors duration-150 cursor-pointer underline underline-offset-2">
        手動輸入
      </button>
      {showManual && (
        <div className="flex items-center gap-1">
          <input type="text" value={manualVal} onChange={e => setManualVal(e.target.value)}
            placeholder="貼上 cookie 字串…"
            className="w-64 px-2 py-0.5 text-[10px] font-['Fira_Code'] border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-400" />
          <button onClick={() => { onManual(manualVal); setShowManual(false) }}
            className="px-2 py-0.5 text-[10px] bg-slate-800 text-white rounded-md hover:bg-slate-700 transition-colors duration-150 cursor-pointer">
            套用
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Spinner ──────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <div className="flex flex-col items-center justify-center h-48 gap-3 text-slate-400">
      <svg className="animate-spin h-8 w-8 text-blue-500" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
      <span className="text-sm">分析中，請稍候…</span>
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [keyword, setKeyword] = useState('北海道一日遊')
  const [cookie, setCookie]   = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [cookieLoading, setCookieLoading] = useState(false)

  const [loading, setLoading] = useState(false)
  const [stageData, setStageData] = useState(null)
  const [prodData, setProdData]   = useState(null)
  const [error, setError]         = useState('')

  const [mode, setMode]           = useState('compare')
  const [onlyIssues, setOnlyIssues] = useState(false)

  // Auto-fetch cookie on mount
  const fetchCookieFor = useCallback(async (env) => {
    const res = await fetch(`http://localhost:8000/api/guest-cookie?env=${env}`)
      .catch(() => { throw new Error('Backend 未啟動 (port 8000)') })
    if (!res.ok) { const b = await res.json().catch(() => ({})); throw new Error(b.detail || `HTTP ${res.status}`) }
    return res.json()
  }, [])

  const autoFetchCookie = useCallback(async (currentMode) => {
    setCookieLoading(true)
    setError('')
    try {
      if (currentMode === 'compare') {
        const [s, p] = await Promise.all([fetchCookieFor('stage'), fetchCookieFor('production')])
        const map = new Map()
        const parse = str => str.split(';').forEach(x => {
          const i = x.indexOf('='); if (i < 0) return
          map.set(x.slice(0, i).trim(), x.slice(i + 1).trim())
        })
        parse(p.cookie); parse(s.cookie)
        const merged = [...map.entries()].map(([k, v]) => `${k}=${v}`).join('; ')
        const keys = [...new Set([...(s.key_fields_found || []), ...(p.key_fields_found || [])])]
        setCookie(merged)
        setCookieInfo({ env: 'stage + production', key_fields_found: keys, total_fields: map.size })
      } else {
        const d = await fetchCookieFor(currentMode)
        setCookie(d.cookie)
        setCookieInfo({ env: d.env, key_fields_found: d.key_fields_found, total_fields: d.total_fields })
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setCookieLoading(false)
    }
  }, [fetchCookieFor])

  useEffect(() => { autoFetchCookie(mode) }, [])   // auto on mount

  const handleModeChange = (newMode) => {
    setMode(newMode)
    setStageData(null); setProdData(null); setError('')
    autoFetchCookie(newMode)
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!cookie) { setError('Cookie 尚未取得，請先點「自動取得」'); return }
    setError(''); setLoading(true); setStageData(null); setProdData(null)

    const call = async (url, body) => {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
        .catch(() => { throw new Error('無法連線到 Backend (port 8000)，請執行 ./start.sh') })
      if (!r.ok) { const b = await r.json().catch(() => ({})); throw new Error(`[${body.env ?? 'compare'} 失敗] HTTP ${r.status}: ${b.detail || ''}`) }
      const d = await r.json(); if (!d.success) throw new Error(d.detail || '未知錯誤')
      return d
    }

    try {
      if (mode === 'compare') {
        const d = await call('http://localhost:8000/api/compare', { keyword, cookie, count: 300 })
        setStageData({ total: d.stage.total, results: d.stage.results, metrics: d.stage.metrics })
        setProdData({ total: d.production.total, results: d.production.results, metrics: d.production.metrics })
      } else {
        const d = await call('http://localhost:8000/api/verify', { keyword, env: mode, cookie, count: 300 })
        if (mode === 'stage') { setStageData(d); setProdData(null) }
        else { setProdData(d); setStageData(null) }
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const hasResults = stageData || prodData
  const showDelta  = mode === 'compare' && !!(stageData && prodData)

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Fira Sans', system-ui, sans-serif; }
      `}</style>

      <div className="min-h-screen bg-[#F8FAFC]">
        {/* ── Sticky Header ── */}
        <header className="sticky top-0 z-20 bg-white border-b border-[#DBEAFE] shadow-sm">
          <div className="max-w-screen-2xl mx-auto px-5 py-3">
            {/* Title Row */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <h1 className="text-base font-bold text-[#1E3A8A] tracking-tight">
                  Search Intent Verification
                </h1>
                <span className="text-[11px] text-slate-400 hidden md:block">搜索意圖驗收平台</span>
              </div>
              <CookieStatus
                info={cookieInfo}
                loading={cookieLoading}
                onRefetch={() => autoFetchCookie(mode)}
                onManual={(v) => { setCookie(v); setCookieInfo({ env: 'manual', key_fields_found: ['manual'], total_fields: 1 }) }}
              />
            </div>

            {/* Search Form */}
            <form onSubmit={handleSearch} className="flex items-center gap-2 flex-wrap">
              {/* Keyword */}
              <div className="relative flex-1 min-w-[200px]">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"><IconSearch /></span>
                <input type="text" value={keyword} onChange={e => setKeyword(e.target.value)} required
                  className="w-full pl-8 pr-3 py-2 text-sm rounded-lg border border-[#DBEAFE] bg-[#F8FAFC] focus:outline-none focus:ring-2 focus:ring-[#1E40AF]/30 focus:border-[#1E40AF] transition-all duration-150 font-['Fira_Sans']"
                  placeholder="搜尋關鍵字，e.g. 北海道一日遊" />
              </div>

              {/* Mode */}
              <select value={mode} onChange={e => handleModeChange(e.target.value)}
                className="px-3 py-2 text-sm rounded-lg border border-[#DBEAFE] bg-[#F8FAFC] text-slate-700 focus:outline-none focus:ring-2 focus:ring-[#1E40AF]/30 cursor-pointer transition-all duration-150 font-['Fira_Sans']">
                <option value="stage">Stage 僅看</option>
                <option value="production">Production 僅看</option>
                <option value="compare">Stage vs Prod（含 Rank Delta）</option>
              </select>

              {/* Filters */}
              <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer hover:text-slate-900 transition-colors duration-150 select-none">
                <input type="checkbox" checked={onlyIssues} onChange={e => setOnlyIssues(e.target.checked)}
                  className="w-3.5 h-3.5 rounded accent-red-500 cursor-pointer" />
                僅顯示有疑慮
              </label>

              {/* Submit */}
              <button type="submit" disabled={loading || cookieLoading}
                className="flex items-center gap-2 px-5 py-2 text-sm font-semibold text-white rounded-lg transition-all duration-150 active:scale-95 disabled:opacity-40 cursor-pointer"
                style={{ background: loading ? '#3B82F6' : '#1E40AF' }}>
                {loading
                  ? <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>分析中…</>
                  : <><IconSearch />Verify Intent</>}
              </button>
            </form>

            {/* Error / Status */}
            {error && (
              <div className="mt-2 flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 rounded-lg border border-red-100 text-xs">
                <span className="flex-1">{error}</span>
                <button onClick={() => setError('')} className="text-red-300 hover:text-red-500 transition-colors cursor-pointer"><IconX /></button>
              </div>
            )}
          </div>
        </header>

        {/* ── Main ── */}
        {loading && !hasResults && (
          <div className="max-w-screen-2xl mx-auto px-5 py-12"><Spinner /></div>
        )}

        {hasResults && (
          <div className="max-w-screen-2xl mx-auto px-5 py-4 flex gap-4">
            {/* Metrics Sidebar */}
            <div className="w-52 shrink-0 space-y-3 sticky top-[108px] self-start">
              {stageData && <MetricsPanel metrics={stageData.metrics} envLabel="Stage" color="#06B6D4" />}
              {prodData  && <MetricsPanel metrics={prodData.metrics}  envLabel="Production" color="#1E40AF" />}
            </div>

            {/* Results */}
            <div className="flex flex-1 gap-3 min-h-0">
              {stageData && (
                <div className="flex-1 bg-white rounded-xl border-t-[3px] border-cyan-400 border border-slate-200 shadow-sm p-4 flex flex-col" style={{ height: 'calc(100vh - 120px)' }}>
                  <ProductList data={stageData} envTitle="Stage" color="#06B6D4" onlyIssues={onlyIssues} showDelta={showDelta} />
                </div>
              )}
              {prodData && (
                <div className="flex-1 bg-white rounded-xl border-t-[3px] border-[#1E40AF] border border-slate-200 shadow-sm p-4 flex flex-col" style={{ height: 'calc(100vh - 120px)' }}>
                  <ProductList data={prodData} envTitle="Production" color="#1E40AF" onlyIssues={onlyIssues} showDelta={false} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
