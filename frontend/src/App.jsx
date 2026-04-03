import { useState } from 'react'

// ─── Helpers ────────────────────────────────────────────────

const TIER_COLOR = {
  1: 'bg-green-100 text-green-700 border-green-200',
  2: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  3: 'bg-orange-100 text-orange-700 border-orange-200',
  null: 'bg-red-100 text-red-700 border-red-200',
}

function TierBadge({ p }) {
  const { tier, mismatch_reasons = [], cat_match, dest_match } = p
  const reasons = mismatch_reasons.join(' | ')
  if (tier === 1) return <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700 rounded-full border border-green-200 shrink-0">T1 精準</span>
  if (tier === 2) return <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-yellow-100 text-yellow-700 rounded-full border border-yellow-200 shrink-0">T2 廣泛</span>
  if (tier === 3) return (
    <span className="flex items-center gap-1">
      <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-orange-100 text-orange-700 rounded-full border border-orange-200 shrink-0">T3 地點</span>
      {cat_match === 'none' && <span className="px-1.5 py-0.5 text-[10px] bg-orange-50 text-orange-600 rounded border border-orange-200 shrink-0" title={reasons}>分類不符</span>}
    </span>
  )
  return (
    <span className="flex items-center gap-1 flex-wrap">
      <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-700 rounded-full border border-red-200 shrink-0">Mismatch</span>
      {!dest_match && <span className="px-1.5 py-0.5 text-[10px] bg-red-50 text-red-600 rounded border border-red-200 shrink-0" title={mismatch_reasons.find(r => r.startsWith('地點'))}>地點不符</span>}
      {cat_match === 'none' && <span className="px-1.5 py-0.5 text-[10px] bg-pink-50 text-pink-600 rounded border border-pink-200 shrink-0" title={mismatch_reasons.find(r => r.startsWith('分類'))}>分類不符</span>}
    </span>
  )
}

function RankDeltaBadge({ delta }) {
  if (delta == null) return null
  if (delta > 0) return <span className="text-[10px] text-green-600 font-bold shrink-0" title={`Stage 比 Prod 前進了 ${delta} 位`}>▲{delta}</span>
  if (delta < 0) return <span className="text-[10px] text-red-500 font-bold shrink-0" title={`Stage 比 Prod 退後了 ${Math.abs(delta)} 位`}>▼{Math.abs(delta)}</span>
  return <span className="text-[10px] text-gray-400 shrink-0">→0</span>
}

// ─── Metrics Panel ───────────────────────────────────────────

function NdcgGauge({ value, label }) {
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-16 h-16">
        <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e5e7eb" strokeWidth="3" />
          <circle cx="18" cy="18" r="15.9" fill="none" stroke={pct >= 70 ? '#22c55e' : pct >= 40 ? '#facc15' : '#f87171'}
            strokeWidth="3" strokeDasharray={`${pct} ${100 - pct}`} strokeLinecap="round" />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-700">{pct}%</span>
      </div>
      <span className="text-[10px] text-gray-500 font-medium">{label}</span>
    </div>
  )
}

function MetricsPanel({ metrics, envLabel, accentClass }) {
  if (!metrics) return null
  const { ndcg_at_10, ndcg_at_50, recall_at_10, recall_at_50, tier_breakdown, mismatch_rate, category_distribution } = metrics
  const tb = tier_breakdown || {}
  const total = tb.total || 1

  return (
    <div className={`rounded-xl border-l-4 ${accentClass} bg-white/80 p-4 shadow-sm space-y-3`}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-bold text-slate-700">{envLabel} 指標</span>
        <span className="text-xs text-gray-400">共 {tb.total} 件</span>
      </div>

      {/* NDCG Gauges */}
      <div className="flex gap-4 justify-center py-1">
        <NdcgGauge value={ndcg_at_10 ?? 0} label="NDCG@10" />
        <NdcgGauge value={ndcg_at_50 ?? 0} label="NDCG@50" />
      </div>

      {/* Recall@K */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {[['Recall@10', recall_at_10], ['Recall@50', recall_at_50]].map(([lbl, v]) => (
          <div key={lbl} className="bg-slate-50 rounded-lg px-2 py-1.5">
            <div className="text-gray-400 text-[10px]">{lbl}</div>
            <div className="font-bold text-slate-700">{v != null ? `${Math.round(v * 100)}%` : '—'}</div>
          </div>
        ))}
        <div className="bg-red-50 rounded-lg px-2 py-1.5">
          <div className="text-gray-400 text-[10px]">Mismatch 率</div>
          <div className="font-bold text-red-600">{Math.round((mismatch_rate ?? 0) * 100)}%</div>
        </div>
        <div className="bg-slate-50 rounded-lg px-2 py-1.5">
          <div className="text-gray-400 text-[10px]">Tier 分佈</div>
          <div className="font-bold text-slate-700 text-[10px]">T1:{tb.tier1} T2:{tb.tier2} T3:{tb.tier3}</div>
        </div>
      </div>

      {/* Category Distribution */}
      {category_distribution?.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-400 mb-1.5 font-medium">分類分佈</div>
          <div className="space-y-1">
            {category_distribution.slice(0, 7).map(({ cat_key, percentage }) => (
              <div key={cat_key} className="flex items-center gap-2">
                <span className="text-[10px] text-gray-500 w-28 truncate shrink-0">{cat_key}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                  <div className="h-full rounded-full bg-blue-400 transition-all" style={{ width: `${percentage}%` }} />
                </div>
                <span className="text-[10px] text-gray-500 w-8 text-right shrink-0">{percentage}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Product Card ─────────────────────────────────────────────

function ProductCard({ p, showDelta }) {
  return (
    <div className="bg-white px-3 py-2 rounded-lg border border-gray-100 hover:shadow-sm transition-shadow flex gap-3 items-start">
      <div className="w-10 h-10 bg-gray-100 rounded overflow-hidden shrink-0 mt-0.5">
        {p.img_url
          ? <img src={p.img_url} alt={p.name} className="w-full h-full object-cover" />
          : <div className="w-full h-full flex items-center justify-center text-gray-300 text-[9px] border border-dashed rounded">No Img</div>}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="bg-slate-700 text-white text-[10px] px-1.5 py-0.5 rounded-full shrink-0">#{p.rank}</span>
          {showDelta && <RankDeltaBadge delta={p.rank_delta} />}
          <TierBadge p={p} />
          <span className="text-gray-400 text-[10px]">📍 {p.destinations.join(', ') || '—'}</span>
          <span className="text-gray-400 text-[10px]">🏷️ {p.main_cat_key || '—'}</span>
        </div>
        <a href={p.url} target="_blank" rel="noreferrer"
          className="block mt-0.5 font-medium text-slate-800 hover:text-blue-600 line-clamp-1 text-xs leading-snug">
          {p.name}
        </a>
      </div>
    </div>
  )
}

// ─── Product List ─────────────────────────────────────────────

function ProductList({ data, envTitle, accentClass, onlyIssues, showDelta }) {
  const listToRender = data.results.filter(p =>
    onlyIssues ? (p.tier === 3 || p.tier === null) : true
  )
  return (
    <div className="flex-1 flex flex-col gap-2 overflow-y-auto pr-1">
      <div className={`sticky top-0 bg-white/95 backdrop-blur pb-2 pt-1 z-10 border-b border-gray-100`}>
        <div className="flex justify-between items-center">
          <span className="text-base font-bold text-slate-800">{envTitle}</span>
          <span className="text-xs text-gray-400">顯示 {listToRender.length} / 總計 {data.total} 件</span>
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        {listToRender.map(p => <ProductCard key={p.id} p={p} showDelta={showDelta} />)}
      </div>
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────

export default function App() {
  const [keyword, setKeyword] = useState('北海道一日遊')
  const [cookie, setCookie] = useState('')
  const [loading, setLoading] = useState(false)
  const [stageData, setStageData] = useState(null)
  const [prodData, setProdData] = useState(null)
  const [error, setError] = useState('')
  const [queryStage, setQueryStage] = useState(true)
  const [queryProd, setQueryProd] = useState(true)
  const [onlyIssues, setOnlyIssues] = useState(false)
  const [useCompare, setUseCompare] = useState(false)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!cookie) { setError('請輸入 Cookie 以獲得授權'); return }
    setError(''); setLoading(true); setStageData(null); setProdData(null)

    try {
      if (queryStage && queryProd && useCompare) {
        // Use /api/compare for rank delta
        const res = await fetch('http://localhost:8000/api/compare', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ keyword, cookie, count: 300 })
        })
        if (!res.ok) throw new Error(`[Compare 請求失敗] HTTP ${res.status}`)
        const data = await res.json()
        if (!data.success) throw new Error(data.detail || 'Compare API Error')
        setStageData({ total: data.stage.total, results: data.stage.results, metrics: data.stage.metrics })
        setProdData({ total: data.production.total, results: data.production.results, metrics: data.production.metrics })
      } else {
        const fetches = []
        if (queryStage) fetches.push(
          fetch('http://localhost:8000/api/verify', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, env: 'stage', cookie, count: 300 })
          }).then(async r => {
            if (!r.ok) throw new Error(`[Stage 環境請求失敗] HTTP ${r.status}`)
            const d = await r.json()
            if (!d.success) throw new Error(d.detail || 'Stage Error')
            setStageData(d)
          })
        )
        if (queryProd) fetches.push(
          fetch('http://localhost:8000/api/verify', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, env: 'production', cookie, count: 300 })
          }).then(async r => {
            if (!r.ok) throw new Error(`[Production 環境請求失敗] HTTP ${r.status}`)
            const d = await r.json()
            if (!d.success) throw new Error(d.detail || 'Prod Error')
            setProdData(d)
          })
        )
        await Promise.all(fetches)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const hasResults = stageData || prodData
  const showDelta = !!(stageData && prodData && useCompare)

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 font-sans">
      {/* ── Header ── */}
      <div className="sticky top-0 z-20 bg-white/90 backdrop-blur shadow-sm border-b border-gray-100 px-6 py-4">
        <div className="max-w-screen-2xl mx-auto">
          <div className="flex items-center gap-3 mb-3">
            <h1 className="text-xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-500">
              Search Intent Verification
            </h1>
            <span className="text-xs text-gray-400 hidden sm:block">評估商品搜尋排序與搜索意圖的匹配程度</span>
          </div>

          <form onSubmit={handleSearch} className="flex flex-col gap-2">
            <div className="flex gap-3 items-end flex-wrap">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-[10px] font-semibold text-gray-500 uppercase mb-1">Search Keyword</label>
                <input type="text" value={keyword} onChange={e => setKeyword(e.target.value)} required
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder="e.g. 北海道一日遊" />
              </div>
              <div className="flex-[2] min-w-[280px]">
                <label className="block text-[10px] font-semibold text-gray-500 uppercase mb-1">Cookie</label>
                <input type="text" value={cookie} onChange={e => setCookie(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-400 font-mono"
                  placeholder="Paste KKDAY_COOKIE..." />
              </div>
              <button type="submit" disabled={loading || (!queryStage && !queryProd)}
                className="px-6 py-2 text-sm bg-slate-900 hover:bg-slate-700 text-white font-semibold rounded-lg shadow transition-all active:scale-95 disabled:opacity-40 h-[38px] flex items-center gap-2 shrink-0">
                {loading
                  ? <><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>分析中...</>
                  : 'Verify Intent'}
              </button>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-5 text-sm flex-wrap">
              {[['查詢 Stage', queryStage, setQueryStage], ['查詢 Production', queryProd, setQueryProd]].map(([label, val, setter]) => (
                <label key={label} className="flex items-center gap-1.5 cursor-pointer text-slate-600">
                  <input type="checkbox" checked={val} onChange={e => setter(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                  {label}
                </label>
              ))}
              <div className="w-px h-4 bg-gray-200" />
              <label className="flex items-center gap-1.5 cursor-pointer text-blue-600 font-medium">
                <input type="checkbox" checked={useCompare} onChange={e => setUseCompare(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                顯示 Rank Delta (需同時查兩環境)
              </label>
              <div className="w-px h-4 bg-gray-200" />
              <label className="flex items-center gap-1.5 cursor-pointer text-red-600 font-medium">
                <input type="checkbox" checked={onlyIssues} onChange={e => setOnlyIssues(e.target.checked)} className="w-3.5 h-3.5 rounded" />
                僅顯示有疑慮 (Mismatch / T3)
              </label>
            </div>
          </form>

          {error && (
            <div className="mt-2 px-4 py-2 bg-red-50 text-red-700 rounded-lg border border-red-100 text-sm">⚠️ {error}</div>
          )}
        </div>
      </div>

      {/* ── Main Content ── */}
      {hasResults && (
        <div className="max-w-screen-2xl mx-auto px-4 py-4 flex gap-4">

          {/* Metrics Sidebar */}
          <div className="w-56 shrink-0 space-y-4 sticky top-[120px] self-start">
            {stageData && <MetricsPanel metrics={stageData.metrics} envLabel="Stage" accentClass="border-cyan-400" />}
            {prodData && <MetricsPanel metrics={prodData.metrics} envLabel="Production" accentClass="border-blue-500" />}
          </div>

          {/* Results Columns */}
          <div className="flex flex-1 gap-4 min-h-0">
            {stageData && (
              <div className="flex-1 bg-white/70 backdrop-blur rounded-xl border-t-4 border-cyan-400 shadow p-4 h-[calc(100vh-140px)] flex flex-col">
                <ProductList data={stageData} envTitle="Stage Environment" accentClass="border-cyan-400"
                  onlyIssues={onlyIssues} showDelta={showDelta} />
              </div>
            )}
            {prodData && (
              <div className="flex-1 bg-white/70 backdrop-blur rounded-xl border-t-4 border-blue-500 shadow p-4 h-[calc(100vh-140px)] flex flex-col">
                <ProductList data={prodData} envTitle="Production Environment" accentClass="border-blue-500"
                  onlyIssues={onlyIssues} showDelta={false} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
