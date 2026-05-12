import { normalizeKw } from '../utils/safeString'
import { IconPlay, IconSquare, IconArchive } from './icons/Icons'

export default function BatchPanel({
  showBatch, setShowBatch,
  auditKeywords, batchStatus, batchResults, batchHistory,
  viewingRunId, onLoadArchive, onExitArchive,
  onStartBatch, onStopBatch,
  findResult,
}) {
  return (
    <div className="shrink-0 border-t border-slate-200">
      {/* Toggle header */}
      <button
        onClick={() => setShowBatch(!showBatch)}
        className="w-full px-8 py-2 bg-white hover:bg-slate-50 flex items-center justify-between transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-black text-slate-800 uppercase tracking-[3px]">
            批次巡檢
          </span>
          {batchStatus?.is_running && (
            <span className="text-[9px] font-black text-indigo-600 animate-pulse uppercase tracking-wider">
              Running {batchStatus.progress}%
            </span>
          )}
          <span className="text-[9px] font-bold text-slate-400">
            {auditKeywords.length} 個關鍵字 · {batchHistory.length} 筆歷史
          </span>
        </div>
        <span className={`text-slate-400 transition-transform ${showBatch ? 'rotate-180' : ''}`}>▼</span>
      </button>

      {showBatch && (
        <div className="bg-slate-50 border-t border-slate-100">
          {/* Controls */}
          <div className="px-8 py-2 flex items-center gap-3">
            <div className="flex-1 max-w-xs">
              <div className="flex justify-between items-end mb-1">
                <span className="text-[8px] font-black text-slate-400 font-mono uppercase">Progress</span>
                <span className="text-[11px] font-black text-indigo-700 font-mono italic">{batchStatus.progress}%</span>
              </div>
              <div className="w-full h-1 bg-slate-100 rounded-full overflow-hidden border border-slate-200 shadow-inner">
                <div className="h-full bg-indigo-600 transition-all duration-700" style={{ width: `${batchStatus.progress}%` }} />
              </div>
            </div>
            <div className="flex gap-2">
              {batchStatus.is_running ? (
                <button onClick={onStopBatch} disabled={!!viewingRunId} className={`px-6 py-1.5 rounded-xl text-[10px] font-black shadow flex items-center gap-1.5 ${viewingRunId ? 'bg-slate-200 text-slate-400' : 'bg-rose-500 text-white'}`}>
                  <IconSquare /> 終止
                </button>
              ) : (
                <button onClick={onStartBatch} disabled={auditKeywords.length === 0 || !!viewingRunId} className={`px-6 py-1.5 rounded-xl text-[10px] font-black shadow tracking-[2px] uppercase flex items-center gap-1.5 ${(auditKeywords.length === 0 || viewingRunId) ? 'bg-slate-200 text-slate-400' : 'bg-[#0F172A] text-white active:scale-95'}`}>
                  <IconPlay /> 啟動
                </button>
              )}
            </div>
          </div>

          {viewingRunId && (
            <div className="mx-4 mb-2 px-4 py-2 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between">
              <span className="text-[11px] font-black text-amber-800">閱覽存檔 #{String(viewingRunId).padStart(3, '0')}</span>
              <button onClick={onExitArchive} className="px-3 py-1 bg-amber-100 hover:bg-amber-200 border border-amber-300 text-amber-800 rounded-lg text-[9px] font-black transition-all">
                返回即時 ×
              </button>
            </div>
          )}

          {/* Keyword table */}
          <div className="px-4 pb-2">
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden max-h-48 overflow-y-auto custom-scroll">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10 font-mono text-[9px] text-slate-400 uppercase tracking-widest">
                    <th className="px-6 py-2">關鍵字</th>
                    <th className="px-4 py-2 text-center border-l border-slate-100">Status</th>
                    <th className="px-4 py-2 text-center border-l border-slate-100">NDCG@10</th>
                    <th className="px-4 py-2 text-center border-l border-slate-100">誤判率</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {(viewingRunId
                    ? Object.keys(batchResults).map(k => ({ keyword: k }))
                    : auditKeywords
                  ).map(kwObj => {
                    const kwStr = kwObj.keyword
                    const res = findResult(kwStr)
                    const isDone = !!res
                    const isActive = !viewingRunId && normalizeKw(kwStr) === normalizeKw(batchStatus.current_keyword)
                    const m = res?.stage?.metrics || res?.stage || {}
                    return (
                      <tr key={kwStr} className={`hover:bg-slate-50 transition-all ${isActive ? 'bg-indigo-50/50' : ''}`}>
                        <td className="px-6 py-2 font-black text-[12px] text-slate-900">{kwStr}</td>
                        <td className="px-4 py-2 text-center border-l border-slate-50">
                          {isDone ? <span className="text-[9px] font-black text-emerald-600 font-mono">Done</span>
                            : isActive ? <span className="text-[9px] font-black text-indigo-700 animate-pulse font-mono">Active</span>
                            : <span className="text-[9px] font-black text-slate-200 font-mono">Wait</span>}
                        </td>
                        <td className="px-4 py-2 border-l border-slate-50 text-center font-mono font-black text-emerald-600 text-[11px]">
                          {isDone ? `${Math.round((m.ndcg_at_10 || m.ndcg_10 || 0) * 100)}%` : '-'}
                        </td>
                        <td className="px-4 py-2 border-l border-slate-50 text-center font-black text-rose-500 text-[11px]">
                          {isDone ? `${Math.round((m.mismatch_rate || 0) * 100)}%` : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Archives */}
          {batchHistory.length > 0 && (
            <div className="px-4 pb-4">
              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden max-h-36 overflow-y-auto custom-scroll">
                <div className="px-6 py-2 bg-slate-50/80 border-b border-slate-200 flex items-center gap-2">
                  <IconArchive />
                  <span className="text-[10px] font-black text-slate-800 uppercase tracking-[2px] font-mono">巡檢紀錄</span>
                </div>
                <table className="w-full text-left">
                  <tbody className="divide-y divide-slate-50">
                    {batchHistory.map(h => {
                      const ndcg = Math.round((h.avg_ndcg || 0) * 100)
                      const ts = h.timestamp ? new Date(h.timestamp).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '-'
                      return (
                        <tr key={h.id} className="hover:bg-indigo-50/20 transition-all">
                          <td className="px-6 py-2 text-slate-400 font-mono text-[10px]">#{h.id.toString().padStart(3, '0')}</td>
                          <td className="px-4 py-2 text-slate-600 text-[11px] font-bold">{ts}</td>
                          <td className="px-4 py-2 text-center">
                            <span className={`px-2 py-0.5 font-black font-mono rounded border text-[10px] ${ndcg >= 80 ? 'bg-emerald-50 text-emerald-700 border-emerald-100' : ndcg >= 50 ? 'bg-amber-50 text-amber-700 border-amber-100' : 'bg-rose-50 text-rose-600 border-rose-100'}`}>
                              {ndcg}%
                            </span>
                          </td>
                          <td className="px-4 py-2 text-right">
                            <button
                              onClick={() => onLoadArchive(h.id)}
                              className="px-3 py-1 bg-white border border-slate-200 text-slate-800 rounded-lg text-[9px] font-black hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all"
                            >
                              載入
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
