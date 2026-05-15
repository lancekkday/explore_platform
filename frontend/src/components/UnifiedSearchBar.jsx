import { useState, useRef, useEffect } from 'react'
import { IconSearch } from './icons/Icons'

export default function UnifiedSearchBar({
  keyword, setKeyword,
  loading, cookieInfo,
  baselineKeywords,
  onSearch,
  onOpenSettings,
  hasResults,
  onExportCSV,
}) {
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputRef = useRef(null)
  const suggestRef = useRef(null)

  const filtered = keyword.trim()
    ? baselineKeywords.filter(k => k.toLowerCase().includes(keyword.toLowerCase())).slice(0, 12)
    : []

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
    <div className="px-2 mb-[7px] flex items-center gap-1.5 shrink-0">
      {/* Keyword input with autocomplete */}
      <div className="relative flex-1 group">
        <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-600 pointer-events-none">
          <IconSearch />
        </span>
        <input
          ref={inputRef}
          type="text"
          value={keyword}
          onChange={e => { setKeyword(e.target.value); setShowSuggestions(true) }}
          onFocus={() => setShowSuggestions(true)}
          onKeyDown={handleKeyDown}
          className="w-full h-[25px] pl-8 pr-3 text-[12px] rounded-[5px] border border-slate-200 bg-white focus:border-indigo-500 outline-none transition-colors text-slate-900"
          placeholder="搜尋關鍵字..."
        />
        {showSuggestions && filtered.length > 0 && (
          <div ref={suggestRef} className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-50 max-h-64 overflow-y-auto">
            {filtered.map(kw => (
              <button
                key={kw}
                onClick={() => handleSelect(kw)}
                className="w-full text-left px-3 py-1.5 text-[11px] text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
              >
                {kw}
                <span className="ml-2 text-[9px] text-slate-400 font-mono uppercase">baseline</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 巡檢 button (dark) */}
      <button
        onClick={() => onSearch(keyword)}
        disabled={loading || !cookieInfo}
        className={`h-[25px] px-3 rounded-[5px] text-[11px] font-semibold tracking-wide transition-colors ${
          (loading || !cookieInfo)
            ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
            : 'bg-slate-900 text-white hover:bg-black active:scale-[0.98]'
        }`}
      >
        {loading ? '搜尋中…' : !cookieInfo ? '等待連線…' : '巡檢'}
      </button>

      {/* Export (only when results) */}
      {hasResults && (
        <button
          onClick={onExportCSV}
          className="h-[25px] px-2.5 rounded-[5px] border border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900 text-[11px] inline-flex items-center gap-1 transition-colors"
          title="匯出 CSV"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          下載
        </button>
      )}

      {/* Settings */}
      <button
        onClick={onOpenSettings}
        className="h-[25px] px-2.5 rounded-[5px] border border-slate-200 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900 text-[11px] inline-flex items-center gap-1 transition-colors"
        title="平台設定"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
        設定
      </button>
    </div>
  )
}
