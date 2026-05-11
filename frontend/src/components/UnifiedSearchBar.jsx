import { useState, useRef, useEffect } from 'react'
import { IconSearch, IconBot } from './icons/Icons'

export default function UnifiedSearchBar({
  keyword, setKeyword,
  versionA, setVersionA,
  versionB, setVersionB,
  enableAB, setEnableAB,
  searchApi, setSearchApi,
  aiEnabled, setAiEnabled,
  loading, cookieInfo,
  baselineKeywords,
  onSearch,
  onOpenSettings,
}) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef(null)
  const suggestRef = useRef(null)

  // Filter baseline keywords for autocomplete
  const filtered = keyword.trim()
    ? baselineKeywords.filter(k => k.toLowerCase().includes(keyword.toLowerCase())).slice(0, 12)
    : []

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e) => {
      if (suggestRef.current && !suggestRef.current.contains(e.target) &&
          inputRef.current && !inputRef.current.contains(e.target)) {
        setShowSuggestions(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (kw) => {
    setKeyword(kw)
    setShowSuggestions(false)
    onSearch(kw)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      setShowSuggestions(false)
      onSearch(keyword)
    }
  }

  return (
    <div className="px-8 py-2.5 bg-white border-b border-slate-200 flex items-center gap-3 shrink-0 z-20 shadow-sm">
      {/* Keyword input with autocomplete */}
      <div className="relative flex-1 max-w-md group">
        <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-600">
          <IconSearch />
        </span>
        <input
          ref={inputRef}
          type="text"
          value={keyword}
          onChange={e => { setKeyword(e.target.value); setShowSuggestions(true) }}
          onFocus={() => setShowSuggestions(true)}
          onKeyDown={handleKeyDown}
          className="w-full pl-10 pr-4 py-2 text-[13px] rounded-xl border-2 border-slate-100 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none transition-all font-black text-slate-900"
          placeholder="搜尋關鍵字..."
        />
        {showSuggestions && filtered.length > 0 && (
          <div ref={suggestRef} className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-xl shadow-xl z-50 max-h-64 overflow-y-auto">
            {filtered.map(kw => (
              <button
                key={kw}
                onClick={() => handleSelect(kw)}
                className="w-full text-left px-4 py-2 text-[12px] font-bold text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors first:rounded-t-xl last:rounded-b-xl"
              >
                {kw}
                <span className="ml-2 text-[9px] text-slate-400 font-mono uppercase">baseline</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Version A/B selectors - only shown for v3 API */}
      {searchApi === 'v3' && (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <label className="text-[9px] font-black text-slate-400 uppercase tracking-wider">A</label>
            <input
              type="number"
              value={versionA}
              onChange={e => setVersionA(parseInt(e.target.value) || 0)}
              className="w-12 px-1.5 py-1.5 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
            />
          </div>

          {enableAB && (
            <>
              <span className="text-[9px] font-black text-indigo-500 uppercase tracking-wider">vs</span>
              <div className="flex items-center gap-1.5">
                <label className="text-[9px] font-black text-slate-400 uppercase tracking-wider">B</label>
                <input
                  type="number"
                  value={versionB ?? 3}
                  onChange={e => setVersionB(parseInt(e.target.value) || 0)}
                  className="w-12 px-1.5 py-1.5 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Toggles */}
      <div className="flex gap-1.5 text-[10px] font-black">
        <button
          onClick={() => setSearchApi(searchApi === 'ajax' ? 'v3' : 'ajax')}
          className={`px-3 py-1.5 rounded-lg border-2 transition-all ${
            searchApi === 'v3'
              ? 'bg-indigo-600 text-white border-indigo-700'
              : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
          }`}
        >
          {searchApi === 'v3' ? 'v3' : 'AJAX'}
        </button>
        <button
          onClick={() => setAiEnabled(!aiEnabled)}
          className={`flex items-center gap-1 px-3 py-1.5 rounded-lg border-2 transition-all ${
            aiEnabled
              ? 'bg-[#0F172A] text-white border-slate-900'
              : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
          }`}
        >
          <IconBot /> AI
        </button>
      </div>

      {/* Search button */}
      <button
        onClick={() => onSearch(keyword)}
        disabled={loading || !cookieInfo}
        className={`px-8 py-2 rounded-xl font-black text-[11px] tracking-[3px] uppercase transition-all shadow-lg ${
          (loading || !cookieInfo)
            ? 'bg-slate-200 text-slate-400 cursor-not-allowed border-2 border-slate-300'
            : 'bg-[#0F172A] text-white hover:bg-black active:scale-95 border-2 border-[#0F172A]'
        }`}
      >
        {loading ? 'SEARCHING...' : !cookieInfo ? '等待連線...' : '巡檢'}
      </button>

      {/* Settings gear */}
      <button
        onClick={onOpenSettings}
        className="text-slate-400 hover:text-slate-700 transition-colors"
        title="平台設定"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      </button>
    </div>
  )
}
