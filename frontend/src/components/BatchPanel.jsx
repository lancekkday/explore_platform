import { useState } from 'react'
import { IconPlay } from './icons/Icons'

const SEVERITY_STYLE = {
  P0: { cls: 'bg-rose-100 text-rose-700 border-rose-200', label: 'P0' },
  P1: { cls: 'bg-amber-100 text-amber-800 border-amber-200', label: 'P1' },
  P2: { cls: 'bg-indigo-50 text-indigo-700 border-indigo-200', label: 'P2' },
  INFO: { cls: 'bg-slate-100 text-slate-600 border-slate-200', label: 'INFO' },
}

function SevChip({ severity, onClick }) {
  if (!severity) return <span className="text-slate-300 text-[10px]">—</span>
  const style = SEVERITY_STYLE[severity] || SEVERITY_STYLE.INFO
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick?.() }}
      className={`inline-block px-1.5 py-px rounded border text-[10px] font-semibold tabular-nums hover:opacity-80 transition-opacity ${style.cls}`}
      title="點擊查看明細"
    >
      {style.label}
    </button>
  )
}

function PreciseCell({ entry }) {
  if (!entry) return <span className="text-emerald-600 text-[11px]">✓</span>
  return (
    <span className="text-[10.5px] text-slate-700" title={entry.reason}>
      {entry.label}
    </span>
  )
}

function LegendLine({ children }) {
  return (
    <div className="px-3 py-1 bg-slate-50/60 border-b border-slate-100 text-[10px] text-slate-500 leading-tight">
      {children}
    </div>
  )
}

function PreciseTable({ rows, totalCount, onJump, onShowDetail }) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden mb-2">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full px-3 py-1.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between hover:bg-slate-100 transition-colors"
      >
        <span className="text-[11px] font-semibold text-slate-800">
          精準詞（{totalCount} 個 · {rows.length} 個有異常）
        </span>
        <span className={`text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`}>▼</span>
      </button>
      {!collapsed && (
        <>
          <LegendLine>
            <strong className="text-slate-600">Top1/Top2</strong>：該 baseline 守門商品在 A/B 的位置（<span className="text-emerald-600">✓</span> 正常 ·
            <span className="ml-1">A#N 偏低</span>：在 A 排得太後面 ·
            <span className="ml-1 text-rose-600">A→B 消失</span>：B 完全找不到） ·
            <strong className="ml-2 text-slate-600">嚴重</strong>：該 query 最高 severity（點擊看明細） · 點 row 跳主列表
          </LegendLine>
          <div className="max-h-64 overflow-y-auto">
            {rows.length === 0 ? (
              <div className="py-6 text-center text-emerald-600 text-[11px]">所有精準詞 baseline 均正常 🎉</div>
            ) : (
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="bg-slate-50/60 sticky top-0 border-b border-slate-200 text-slate-500 text-[10px] uppercase tracking-wider">
                    <th className="px-3 py-1.5 font-medium">query</th>
                    <th className="px-3 py-1.5 font-medium">Top1</th>
                    <th className="px-3 py-1.5 font-medium">Top2</th>
                    <th className="px-3 py-1.5 font-medium w-[60px] text-right">嚴重</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr
                      key={r.query}
                      onClick={() => onJump?.(r.query)}
                      className="border-b border-slate-100 hover:bg-indigo-50/40 cursor-pointer transition-colors"
                    >
                      <td className="px-3 py-1.5 font-medium text-slate-800">{r.query}</td>
                      <td className="px-3 py-1.5"><PreciseCell entry={r.top1} /></td>
                      <td className="px-3 py-1.5"><PreciseCell entry={r.top2} /></td>
                      <td className="px-3 py-1.5 text-right">
                        <SevChip
                          severity={r.worstSeverity}
                          onClick={() => onShowDetail?.({ kind: 'precise', row: r })}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function BroadTable({ rows, totalCount, onJump, onShowDetail }) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full px-3 py-1.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between hover:bg-slate-100 transition-colors"
      >
        <span className="text-[11px] font-semibold text-slate-800">
          泛詞（{totalCount} 個 · {rows.length} 個有異常）
        </span>
        <span className={`text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`}>▼</span>
      </button>
      {!collapsed && (
        <>
          <LegendLine>
            <strong className="text-slate-600">異常</strong>：該 query 產生的 alert 總筆數（一個 baseline 商品可能貢獻 1~2 筆） ·
            <strong className="ml-1 text-slate-600">消失</strong>：其中 B 版完全找不到該商品（a_rank 有、b_rank 為空）的筆數 ·
            <strong className="ml-1 text-slate-600">嚴重</strong>：最高 severity（點擊看明細） · 點 row 跳主列表
          </LegendLine>
          <div className="max-h-64 overflow-y-auto">
            {rows.length === 0 ? (
              <div className="py-6 text-center text-emerald-600 text-[11px]">所有泛詞 baseline 均正常 🎉</div>
            ) : (
              <table className="w-full text-left text-[11px]">
                <thead>
                  <tr className="bg-slate-50/60 sticky top-0 border-b border-slate-200 text-slate-500 text-[10px] uppercase tracking-wider">
                    <th className="px-3 py-1.5 font-medium">query</th>
                    <th className="px-3 py-1.5 font-medium w-[60px]">異常</th>
                    <th className="px-3 py-1.5 font-medium w-[60px]">消失</th>
                    <th className="px-3 py-1.5 font-medium w-[60px] text-right">嚴重</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr
                      key={r.query}
                      onClick={() => onJump?.(r.query)}
                      className="border-b border-slate-100 hover:bg-indigo-50/40 cursor-pointer transition-colors"
                    >
                      <td className="px-3 py-1.5 font-medium text-slate-800">{r.query}</td>
                      <td className="px-3 py-1.5 tabular-nums text-slate-700">{r.anomalies}</td>
                      <td className="px-3 py-1.5 tabular-nums text-rose-600">{r.missingCount || ''}</td>
                      <td className="px-3 py-1.5 text-right">
                        <SevChip
                          severity={r.worstSeverity}
                          onClick={() => onShowDetail?.({ kind: 'broad', row: r })}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function AlertDetailModal({ detail, onClose }) {
  if (!detail) return null
  const { kind, row } = detail
  const reasons = row?.reasons || []
  const slotLabel = (br) => {
    if (kind === 'precise') return `Top${br || '?'}`
    return `#${br || '?'}`
  }
  return (
    <div
      className="fixed inset-0 z-[400] flex items-center justify-center bg-black/30 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-2xl w-[640px] max-w-[90vw] max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-2.5 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[12px] font-semibold tracking-wider">{row.query}</span>
            <span className="text-[10px] text-slate-300">
              {kind === 'precise' ? '精準詞 baseline' : '泛詞 baseline'}
            </span>
          </div>
          <button onClick={onClose} className="text-white/60 hover:text-white text-[16px] leading-none">✕</button>
        </div>
        <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-[10px] text-slate-500">
          共 {reasons.length} 筆 alert · 依嚴重度排序
        </div>
        <div className="flex-1 overflow-y-auto">
          {reasons.length === 0 ? (
            <div className="py-10 text-center text-slate-400 text-[11px]">無 alert 明細</div>
          ) : (
            <table className="w-full text-[11px]">
              <thead className="bg-slate-50/60 sticky top-0 border-b border-slate-200 text-slate-500 text-[10px] uppercase tracking-wider">
                <tr>
                  <th className="px-3 py-1.5 font-medium text-left w-[60px]">baseline</th>
                  <th className="px-3 py-1.5 font-medium text-left w-[60px]">嚴重</th>
                  <th className="px-3 py-1.5 font-medium text-left w-[60px]">A 排名</th>
                  <th className="px-3 py-1.5 font-medium text-left w-[60px]">B 排名</th>
                  <th className="px-3 py-1.5 font-medium text-left">原因</th>
                </tr>
              </thead>
              <tbody>
                {reasons.map((r, i) => {
                  const noRanks = r.a_rank == null && r.b_rank == null
                  return (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="px-3 py-1.5 font-mono tabular-nums text-slate-700">{slotLabel(r.baseline_rank)}</td>
                      <td className="px-3 py-1.5"><SevChip severity={r.severity} /></td>
                      {noRanks ? (
                        <td colSpan={2} className="px-3 py-1.5 text-slate-400 italic text-[10px]">(side health · 詳見原因)</td>
                      ) : (
                        <>
                          <td className="px-3 py-1.5 tabular-nums text-slate-700">
                            {r.a_rank != null ? r.a_rank : <span className="text-slate-300">—</span>}
                          </td>
                          <td className="px-3 py-1.5 tabular-nums text-slate-700">
                            {r.b_rank != null ? r.b_rank : <span className="text-slate-300">—</span>}
                          </td>
                        </>
                      )}
                      <td className="px-3 py-1.5 text-slate-600">{r.reason}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

export default function BatchPanel({
  showBatch, setShowBatch,
  versionA, versionB,
  baselineReport,
  baselineRunning,
  baselineCounts,
  onRun,
  onJumpToKeyword,
  error,
}) {
  const totalPrecise = baselineCounts?.precise ?? 0
  const totalBroad = baselineCounts?.broad ?? 0
  const summary = baselineReport?.summary
  const [detail, setDetail] = useState(null)

  return (
    <div className="shrink-0 border-t border-slate-200">
      {/* Toggle header */}
      <button
        onClick={() => setShowBatch(!showBatch)}
        className="w-full px-6 py-2 bg-white hover:bg-slate-50 flex items-center justify-between transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-bold text-slate-800 uppercase tracking-[3px]">
            批次 baseline 巡檢
          </span>
          {baselineRunning && (
            <span className="text-[10px] text-indigo-600 animate-pulse">巡檢中…</span>
          )}
          {!baselineRunning && summary && (
            <span className="text-[10px] text-slate-500">
              異常 {summary.total} 筆 · P0 {summary.P0} · P1 {summary.P1} · P2 {summary.P2} · INFO {summary.INFO}
            </span>
          )}
          {!baselineRunning && !summary && (
            <span className="text-[10px] text-slate-400">
              {totalPrecise + totalBroad > 0 ? `共 ${totalPrecise} 精準詞 + ${totalBroad} 泛詞` : '尚未巡檢'}
            </span>
          )}
        </div>
        <span className={`text-slate-400 transition-transform ${showBatch ? 'rotate-180' : ''}`}>▼</span>
      </button>

      {showBatch && (
        <div className="bg-slate-50 border-t border-slate-100 px-4 py-3 max-h-[60vh] overflow-y-auto custom-scroll">
          {/* Control row */}
          <div className="flex items-center gap-3 mb-3">
            <div className="text-[11px] text-slate-600 inline-flex items-center gap-2">
              <span>A test_exp</span>
              <span className="inline-block px-2 py-0.5 rounded border border-slate-300 bg-white font-mono tabular-nums text-slate-800">{versionA}</span>
              <span className="text-slate-400">vs</span>
              <span>B test_exp</span>
              <span className="inline-block px-2 py-0.5 rounded border border-slate-300 bg-white font-mono tabular-nums text-slate-800">{versionB}</span>
            </div>
            <button
              onClick={onRun}
              disabled={baselineRunning}
              className={`ml-auto px-4 py-1.5 rounded-md text-[11px] font-semibold inline-flex items-center gap-1.5 transition-colors ${
                baselineRunning
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-slate-900 text-white hover:bg-black'
              }`}
            >
              <IconPlay />
              {baselineRunning ? '巡檢中…' : (summary ? '重新巡檢' : '啟動')}
            </button>
          </div>

          {error && (
            <div className="mb-3 px-3 py-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-700">
              {error}
            </div>
          )}

          {baselineRunning && !summary && (
            <div className="flex flex-col items-center gap-2 py-12">
              <div className="w-7 h-7 border-[3px] border-slate-200 border-t-indigo-600 rounded-full animate-spin" />
              <div className="text-[11px] text-slate-500">巡檢中… 預計 3~5 分鐘</div>
              <div className="text-[10px] text-slate-400">將執行 {totalPrecise + totalBroad} 個關鍵字 × A/B 兩版本</div>
            </div>
          )}

          {baselineReport && (
            <>
              <PreciseTable
                rows={baselineReport.precise}
                totalCount={totalPrecise}
                onJump={onJumpToKeyword}
                onShowDetail={setDetail}
              />
              <BroadTable
                rows={baselineReport.broad}
                totalCount={totalBroad}
                onJump={onJumpToKeyword}
                onShowDetail={setDetail}
              />
            </>
          )}

          {!baselineRunning && !baselineReport && !error && (
            <div className="py-10 text-center text-[11px] text-slate-400">
              點「啟動」開始巡檢全部 baseline 守門關鍵字
            </div>
          )}
        </div>
      )}

      <AlertDetailModal detail={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
