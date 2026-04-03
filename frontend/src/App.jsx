import { useState } from 'react'

function App() {
  const [keyword, setKeyword] = useState('北海道一日遊')
  const [cookie, setCookie] = useState('')
  const [loading, setLoading] = useState(false)
  
  const [stageResults, setStageResults] = useState(null)
  const [prodResults, setProdResults] = useState(null)
  const [error, setError] = useState('')
  const [queryStage, setQueryStage] = useState(true)
  const [queryProd, setQueryProd] = useState(true)
  const [onlyIssues, setOnlyIssues] = useState(false)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!cookie) {
      setError('請輸入 Cookie 以獲得授權')
      return
    }
    setError('')
    setLoading(true)
    setStageResults(null)
    setProdResults(null)

    try {
      const fetchPromises = []
      
      if (queryStage) {
        fetchPromises.push(
          fetch('http://localhost:8000/api/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, env: 'stage', cookie, count: 300 })
          })
          .then(async r => {
            if(!r.ok) {
                const txt = await r.text();
                throw new Error(txt || `HTTP ${r.status}`);
            }
            return r.json();
          })
          .then(res => {
            if(!res.success) throw new Error(res.detail || "API Response Error")
            setStageResults(res)
          })
          .catch(err => {
            throw new Error(`[Stage 環境請求失敗] ${err.message}`)
          })
        )
      }
      
      if (queryProd) {
        fetchPromises.push(
          fetch('http://localhost:8000/api/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyword, env: 'production', cookie, count: 300 })
          })
          .then(async r => {
            if(!r.ok) {
                const txt = await r.text();
                throw new Error(txt || `HTTP ${r.status}`);
            }
            return r.json();
          })
          .then(res => {
            if(!res.success) throw new Error(res.detail || "API Response Error")
            setProdResults(res)
          })
          .catch(err => {
            throw new Error(`[Production 環境請求失敗] ${err.message}`)
          })
        )
      }

      await Promise.all(fetchPromises)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const renderTierBadge = (p) => {
    const { tier, mismatch_reasons = [] } = p
    const reasons = mismatch_reasons.join(' | ')
    switch(tier) {
      case 1:
        return <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-green-100 text-green-700 rounded-full border border-green-200 shrink-0">T1 精準</span>
      case 2:
        return <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-yellow-100 text-yellow-700 rounded-full border border-yellow-200 shrink-0">T2 廣泛</span>
      case 3: {
        // cat_match===none but dest ok
        const hasCatIssue = p.cat_match === 'none'
        return (
          <span className="flex items-center gap-1">
            <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-orange-100 text-orange-700 rounded-full border border-orange-200 shrink-0">T3 地點</span>
            {hasCatIssue && (
              <span className="px-1.5 py-0.5 text-[10px] bg-orange-50 text-orange-600 rounded border border-orange-200 shrink-0" title={reasons}>分類不符</span>
            )}
          </span>
        )
      }
      default: {
        // tier === null — full mismatch, break down reasons
        const destFail = !p.dest_match
        const catFail  = p.cat_match === 'none'
        return (
          <span className="flex items-center gap-1 flex-wrap">
            <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-red-100 text-red-700 rounded-full border border-red-200 shrink-0">Mismatch</span>
            {destFail && (
              <span className="px-1.5 py-0.5 text-[10px] bg-red-50 text-red-600 rounded border border-red-200 shrink-0"
                title={mismatch_reasons.find(r => r.startsWith('地點'))}>地點不符</span>
            )}
            {catFail && (
              <span className="px-1.5 py-0.5 text-[10px] bg-pink-50 text-pink-600 rounded border border-pink-200 shrink-0"
                title={mismatch_reasons.find(r => r.startsWith('分類'))}>分類不符</span>
            )}
          </span>
        )
      }
    }
  }

  const ProductList = ({ data, envTitle }) => {
    const listToRender = data.results.filter(p => onlyIssues ? (p.tier === 3 || p.tier === null) : true);
    
    return (
    <div className="flex-1 flex flex-col gap-4 overflow-y-auto pr-2 max-h-[800px]">
      <h2 className="text-xl font-bold sticky top-0 bg-white/90 backdrop-blur pb-2 z-10 pt-2 border-b border-gray-100 flex justify-between items-center">
        <span>{envTitle}</span>
        <span className="text-sm font-normal text-gray-500">顯示 {listToRender.length} / 總計 {data.total} 件</span>
      </h2>
      {listToRender.map((p) => (
        <div key={p.id} className="bg-white px-3 py-2 rounded-lg border border-gray-100 hover:shadow-sm transition-shadow flex gap-3 items-start">
          <div className="w-10 h-10 bg-gray-100 rounded overflow-hidden shrink-0 mt-0.5">
            {p.img_url ? (
               <img src={p.img_url} alt={p.name} className="w-full h-full object-cover" />
            ) : (
               <div className="w-full h-full flex items-center justify-center text-gray-300 text-[9px] border border-dashed rounded">No Img</div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="bg-slate-700 text-white text-[10px] px-1.5 py-0.5 rounded-full shrink-0">#{p.rank}</span>
              {renderTierBadge(p)}
              <span className="text-gray-400 text-[10px]">📍 {p.destinations.join(', ') || '—'}</span>
              <span className="text-gray-400 text-[10px]">🏷️ {p.main_cat_key || '—'}</span>
            </div>
            <a href={p.url} target="_blank" rel="noreferrer" className="block mt-0.5 font-medium text-slate-800 hover:text-blue-600 line-clamp-1 text-xs leading-snug">
              {p.name}
            </a>
          </div>
        </div>
      ))}
    </div>
    )
  }

  return (
    <div className="min-h-screen p-8 bg-gradient-to-br from-[#f8fafc] to-[#e2e8f0] font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Header / Control Panel */}
        <div className="glass-panel p-6 shadow-xl">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-cyan-500">
                Search Intent Verification
              </h1>
              <p className="text-sm text-slate-500 mt-2">評估商品搜尋排序與搜索意圖的匹配程度</p>
            </div>
          </div>

          <form onSubmit={handleSearch} className="flex flex-col gap-4">
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-2">Search Keyword</label>
                <input 
                  type="text" 
                  value={keyword}
                  onChange={e => setKeyword(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm"
                  placeholder="e.g. 北海道一日遊"
                  required
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-2">Authentication Cookie</label>
                <input 
                  type="text" 
                  value={cookie}
                  onChange={e => setCookie(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm font-mono text-sm"
                  placeholder="Paste KKDAY_COOKIE here..."
                />
              </div>
              <button 
                type="submit" 
                disabled={loading || (!queryStage && !queryProd)}
                className="px-8 py-3 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-xl shadow-md transition-all active:scale-95 disabled:opacity-50 h-[50px] flex items-center justify-center shrink-0"
              >
                {loading ? (
                  <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                ) : 'Verify Intent'}
              </button>
            </div>
            
            <div className="flex items-center gap-6 mt-2 pb-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={queryStage} onChange={e => setQueryStage(e.target.checked)} className="w-4 h-4 text-blue-600 rounded" />
                <span className="text-sm font-medium text-slate-700">查詢 Stage</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={queryProd} onChange={e => setQueryProd(e.target.checked)} className="w-4 h-4 text-blue-600 rounded" />
                <span className="text-sm font-medium text-slate-700">查詢 Production</span>
              </label>
              <div className="w-px h-6 bg-gray-300 mx-2"></div>
              <label className="flex items-center gap-2 cursor-pointer bg-red-50 px-3 py-1.5 rounded-lg border border-red-100 filter drop-shadow-sm hover:brightness-95 transition-all">
                <input type="checkbox" checked={onlyIssues} onChange={e => setOnlyIssues(e.target.checked)} className="w-4 h-4 text-red-600 rounded" />
                <span className="text-sm font-semibold text-red-700">僅顯示有疑慮的商品 (Mismatch 或 Tier 3)</span>
              </label>
            </div>
          </form>

          {error && (
            <div className="mt-4 p-4 bg-red-50 text-red-700 rounded-lg border border-red-100 text-sm flex items-center gap-2">
              ⚠️ {error}
            </div>
          )}
        </div>

        {/* Results View */}
        {(stageResults || prodResults) && (
          <div className={`flex gap-6 h-[800px] ${(!stageResults || !prodResults) ? 'max-w-5xl mx-auto' : ''}`}>
            {/* Stage Side */}
            {stageResults && (
              <div className="glass-panel p-6 flex-1 flex flex-col shadow-lg border-t-4 border-t-cyan-400">
                 <ProductList data={stageResults} envTitle="Stage Environment" />
              </div>
            )}

            {/* Production Side */}
            {prodResults && (
              <div className="glass-panel p-6 flex-1 flex flex-col shadow-lg border-t-4 border-t-blue-500">
                 <ProductList data={prodResults} envTitle="Production Environment" />
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}

export default App
