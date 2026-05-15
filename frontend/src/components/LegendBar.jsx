const FILTER_LABEL = {
  all: '全部',
  diff: '差異模式',
  focus: '需關注模式',
}

export default function LegendBar({ filterMode = 'all' }) {
  return (
    <div className="flex items-center gap-3 px-2 py-1.5 text-[10px] text-slate-500">
      <span className="text-emerald-700">▲ 上升</span>
      <span className="text-rose-700">▼ 下降</span>
      <span className="ml-auto">篩選中：{FILTER_LABEL[filterMode] || '全部'}</span>
    </div>
  )
}
