import { useCopyToClipboard } from '../utils/useCopyToClipboard'

function SegButton({ active, onClick, label, count }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 h-[21px] px-2.5 rounded-[4px] text-[11px] font-semibold transition-colors ${
        active
          ? 'bg-white border border-slate-300 text-slate-900 shadow-sm'
          : 'bg-transparent border border-transparent text-slate-500 hover:text-slate-700'
      }`}
    >
      <span>{label}</span>
      {count != null && (
        <span
          className={`text-[10px] px-1.5 rounded-full tabular-nums ${
            active ? 'bg-slate-200 text-slate-700' : 'bg-slate-100 text-slate-500'
          }`}
        >
          {count}
        </span>
      )}
    </button>
  )
}

export default function FilterBar({
  filterMode = 'all',
  setFilterMode,
  diffCount = 0,
  focusCount = 0,
  totalCount = 0,
  baseLabel = '以 A 為基準',
  requestId = null,
}) {
  const [copied, copy] = useCopyToClipboard()
  const toggle = (mode) => {
    setFilterMode?.(filterMode === mode ? 'all' : mode)
  }

  return (
    <div className="flex items-center gap-2 px-2 mb-[7px] text-[11px]">
      <span className="text-slate-500">顯示：</span>
      <div className="inline-flex items-center gap-0.5 bg-slate-100 border border-slate-200 rounded-md p-0.5">
        <SegButton
          active={filterMode === 'all'}
          onClick={() => setFilterMode?.('all')}
          label="全部"
          count={totalCount}
        />
        <SegButton
          active={filterMode === 'diff'}
          onClick={() => toggle('diff')}
          label="⇄ 差異"
          count={diffCount}
        />
        <SegButton
          active={filterMode === 'focus'}
          onClick={() => toggle('focus')}
          label="🔔 需關注"
          count={focusCount}
        />
      </div>
      {requestId && (
        <button
          onClick={() => copy(requestId)}
          title="點擊複製 request_id（可貼到 Kibana 查這次搜尋的後端 log）"
          className="ml-auto inline-flex items-center gap-1 text-[10px] font-mono text-slate-400 hover:text-slate-600 bg-slate-50 hover:bg-slate-100 px-2 py-0.5 rounded border border-slate-200 transition-colors"
        >
          <span className="text-slate-300">#</span>
          <span>{copied ? '已複製' : requestId}</span>
        </button>
      )}
      <span className={`${requestId ? '' : 'ml-auto'} inline-flex items-center gap-1 text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded`}>
        <span>📌</span>
        <span>{baseLabel}</span>
      </span>
    </div>
  )
}
