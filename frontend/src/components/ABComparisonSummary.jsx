const SEVERITY_COLORS = {
  P0: 'bg-red-100 text-red-800 border-red-200',
  P1: 'bg-orange-100 text-orange-800 border-orange-200',
  P2: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  INFO: 'bg-slate-100 text-slate-600 border-slate-200',
  OK: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}

const SEVERITY_ROW = {
  P0: 'bg-red-50/60',
  P1: 'bg-orange-50/40',
}

export default function ABComparisonSummary({ comparison }) {
  if (!comparison) return null
  const { rank_changes, summary } = comparison
  if (!rank_changes || rank_changes.length === 0) {
    return (
      <div className="px-6 py-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-center">
        <span className="text-[12px] font-black text-emerald-700 tracking-wider">
          所有 baseline 商品在 A/B 版本間排名無顯著變化
        </span>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden">
      <div className="px-6 py-2.5 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
        <span className="text-[11px] font-black text-slate-800 uppercase tracking-[3px] font-mono">
          A/B 排名異動
        </span>
        <div className="flex items-center gap-2 text-[9px] font-black">
          {summary.P0 > 0 && <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded border border-red-200">P0: {summary.P0}</span>}
          {summary.P1 > 0 && <span className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded border border-orange-200">P1: {summary.P1}</span>}
          {summary.P2 > 0 && <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded border border-yellow-200">P2: {summary.P2}</span>}
          <span className="text-slate-400">共 {summary.total_changes} 項異動</span>
        </div>
      </div>
      <div className="max-h-48 overflow-y-auto custom-scroll">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10 font-mono text-[9px] text-slate-400 uppercase tracking-widest">
              <th className="px-4 py-2 text-center">嚴重度</th>
              <th className="px-4 py-2 border-l border-slate-100">Baseline</th>
              <th className="px-4 py-2 border-l border-slate-100">商品</th>
              <th className="px-4 py-2 text-center border-l border-slate-100">A 排名</th>
              <th className="px-4 py-2 text-center border-l border-slate-100">B 排名</th>
              <th className="px-4 py-2 text-center border-l border-slate-100">變化</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {rank_changes.map((rc, i) => (
              <tr key={i} className={`hover:bg-slate-50 transition-all ${SEVERITY_ROW[rc.severity] || ''}`}>
                <td className="px-4 py-2 text-center">
                  <span className={`px-2 py-0.5 rounded border text-[9px] font-black ${SEVERITY_COLORS[rc.severity] || SEVERITY_COLORS.OK}`}>
                    {rc.severity}
                  </span>
                </td>
                <td className="px-4 py-2 border-l border-slate-50 text-[9px] font-bold text-slate-500">
                  {rc.baseline_tag}
                </td>
                <td className="px-4 py-2 border-l border-slate-50 text-[11px] font-bold text-slate-800 max-w-[200px] truncate">
                  {rc.name}
                </td>
                <td className="px-4 py-2 text-center border-l border-slate-50 font-mono text-[11px] text-slate-600">
                  {rc.a_rank != null ? `#${rc.a_rank}` : '—'}
                </td>
                <td className="px-4 py-2 text-center border-l border-slate-50 font-mono text-[11px] text-slate-600">
                  {rc.b_rank != null ? `#${rc.b_rank}` : (
                    rc.stage_status === 'removed' ? <span className="text-red-600 font-bold">下架</span> :
                    rc.stage_status === 'exists'  ? <span className="text-orange-600 font-bold">&gt;300</span> :
                    rc.stage_status === 'check_failed' ? <span className="text-slate-500 font-bold">未確認</span> :
                    <span className="text-red-500 font-bold">消失</span>
                  )}
                </td>
                <td className="px-4 py-2 text-center border-l border-slate-50 font-mono text-[11px] font-bold">
                  {rc.delta != null ? (
                    <span className={rc.delta > 0 ? 'text-rose-600' : rc.delta < 0 ? 'text-emerald-600' : 'text-slate-400'}>
                      {rc.delta > 0 ? `+${rc.delta}` : rc.delta}
                    </span>
                  ) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
