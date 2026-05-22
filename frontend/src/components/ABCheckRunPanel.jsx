import { useMemo, useState } from 'react'
import { useAppContext } from '../context/AppContext'
import { IconPlay } from './icons/Icons'

const TYPE_LABEL = { precise: '精準詞', broad: '泛詞' }

const STATUS_STYLE = {
  pending:     'bg-slate-100 text-slate-500 border-slate-200',
  running:     'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse',
  ok:          'bg-emerald-50 text-emerald-700 border-emerald-200',
  error:       'bg-rose-100 text-rose-700 border-rose-200',
  starting:    'bg-slate-100 text-slate-500 border-slate-200',
  done:        'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed:      'bg-rose-100 text-rose-700 border-rose-200',
  cancelled:   'bg-amber-100 text-amber-800 border-amber-200',
  interrupted: 'bg-amber-100 text-amber-800 border-amber-200',
}

const SEVERITY_RANK = { P0: 4, P1: 3, P2: 2, INFO: 1 }
const SEVERITY_STYLE = {
  P0:   'bg-rose-100 text-rose-700 border-rose-200',
  P1:   'bg-amber-100 text-amber-800 border-amber-200',
  P2:   'bg-indigo-50 text-indigo-700 border-indigo-200',
  INFO: 'bg-slate-100 text-slate-600 border-slate-200',
}

function StatusChip({ status }) {
  if (!status) return <span className="text-slate-300 text-[10px]">—</span>
  return (
    <span className={`inline-block px-1.5 py-px rounded border text-[10px] font-semibold tabular-nums ${STATUS_STYLE[status] || STATUS_STYLE.pending}`}>
      {status}
    </span>
  )
}

function SeverityChip({ severity }) {
  if (!severity) return <span className="text-slate-300 text-[10px]">—</span>
  return (
    <span className={`inline-block px-1.5 py-px rounded border text-[10px] font-semibold tabular-nums ${SEVERITY_STYLE[severity] || SEVERITY_STYLE.INFO}`}>
      {severity}
    </span>
  )
}

function topSeverity(alerts) {
  if (!Array.isArray(alerts) || alerts.length === 0) return null
  return alerts.reduce((acc, a) => {
    const rank = SEVERITY_RANK[a.severity] || 0
    return rank > (SEVERITY_RANK[acc] || 0) ? a.severity : acc
  }, null)
}

function ProgressBar({ done, total, status }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const barColor = status === 'failed' ? 'bg-rose-500'
                : status === 'cancelled' || status === 'interrupted' ? 'bg-amber-500'
                : status === 'done' ? 'bg-emerald-500'
                : 'bg-indigo-500'
  return (
    <div className="w-full h-1.5 bg-slate-200 rounded overflow-hidden">
      <div
        className={`h-full transition-all duration-300 ${barColor}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

export default function ABCheckRunPanel({ type }) {
  const { versionA, versionB, preciseRun, broadRun, startRun, resetRun } = useAppContext()
  const run = type === 'precise' ? preciseRun : broadRun
  const [limit, setLimit] = useState('')

  const rows = useMemo(() => {
    const arr = Array.from(run.rowsMap.values())
    arr.sort((a, b) => a.query_idx - b.query_idx)
    return arr
  }, [run.rowsMap])

  const isInflight = run.status === 'starting' || run.status === 'running'
  const isStarting = run.status === 'starting'

  async function handleStart() {
    await startRun(type, limit, null)
  }

  function handleReset() {
    resetRun(type)
  }

  return (
    <div className="flex flex-col h-full">
      {/* 啟動列 */}
      <div className="px-4 py-2 bg-white border-b border-slate-200 flex items-center gap-3 shrink-0">
        <span className="text-[11px] text-slate-500">{TYPE_LABEL[type]} · limit</span>
        <input
          type="number"
          min="1"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          placeholder="空白 = 全跑"
          disabled={isInflight}
          className="w-32 px-2 py-1 border border-slate-300 rounded text-[11px] tabular-nums disabled:bg-slate-100"
        />
        <div className="text-[11px] text-slate-600 inline-flex items-center gap-1.5">
          <span>A</span>
          <span className="inline-block px-1.5 py-0.5 rounded border border-slate-300 bg-white font-mono tabular-nums text-slate-800 text-[10px]">{versionA}</span>
          <span className="text-slate-400">vs</span>
          <span>B</span>
          <span className="inline-block px-1.5 py-0.5 rounded border border-slate-300 bg-white font-mono tabular-nums text-slate-800 text-[10px]">{versionB}</span>
        </div>
        <div className="flex-1" />
        {run.runId && (
          <button
            onClick={handleReset}
            disabled={isInflight}
            className="px-3 py-1 rounded text-[11px] text-slate-600 hover:bg-slate-100 transition-colors disabled:text-slate-300 disabled:cursor-not-allowed"
          >
            重設
          </button>
        )}
        <button
          onClick={handleStart}
          disabled={isInflight}
          className={`px-4 py-1.5 rounded-md text-[11px] font-semibold inline-flex items-center gap-1.5 transition-colors ${
            isInflight
              ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
              : 'bg-slate-900 text-white hover:bg-black'
          }`}
        >
          <IconPlay />
          {isStarting ? '啟動中…' : (run.runId ? '重新啟動' : '啟動')}
        </button>
      </div>

      {/* 內容 */}
      <div className="flex-1 overflow-y-auto bg-slate-50 px-4 py-3 custom-scroll">
        {run.error && (
          <div className="mb-3 px-3 py-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-700">
            {run.error}
          </div>
        )}

        {!run.runId && !run.error && (
          <div className="py-16 text-center text-[12px] text-slate-400">
            <div className="text-slate-300 text-[36px] mb-3">📊</div>
            <div>輸入 limit(可空)後按「啟動」開始 {TYPE_LABEL[type]} 巡檢</div>
            <div className="text-[10px] mt-2">啟動後表格立刻 render 所有 query 為 pending,每 2 秒拉一次增量更新</div>
          </div>
        )}

        {run.runId && (
          <>
            <div className="mb-2 flex items-center gap-3 text-[11px]">
              <span className="text-slate-500">run_id</span>
              <span className="font-mono tabular-nums text-slate-700 text-[10px]">{run.runId.slice(0, 12)}…</span>
              <span className="text-slate-300">|</span>
              <span className="text-slate-500">進度</span>
              <span className="tabular-nums text-slate-800 font-semibold">{run.doneCount}/{run.total}</span>
              {run.runningIdx != null && isInflight && (
                <>
                  <span className="text-slate-300">|</span>
                  <span className="text-slate-500">跑到</span>
                  <span className="font-mono text-indigo-700 text-[10px]">
                    #{run.runningIdx} {run.rowsMap.get(run.runningIdx)?.query}
                  </span>
                </>
              )}
              <div className="flex-1" />
              <StatusChip status={run.status} />
            </div>

            <div className="mb-3">
              <ProgressBar done={run.doneCount} total={run.total} status={run.status} />
            </div>

            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <div className="max-h-[calc(100vh-260px)] overflow-y-auto">
                {rows.length === 0 ? (
                  <div className="py-6 text-center text-slate-400 text-[11px]">尚無 row…</div>
                ) : (
                  <table className="w-full text-left text-[11px]">
                    <thead>
                      <tr className="bg-slate-50/60 sticky top-0 border-b border-slate-200 text-slate-500 text-[10px] uppercase tracking-wider">
                        <th className="px-3 py-1.5 font-medium w-[60px]">#</th>
                        <th className="px-3 py-1.5 font-medium">query</th>
                        <th className="px-3 py-1.5 font-medium w-[80px]">狀態</th>
                        <th className="px-3 py-1.5 font-medium w-[70px] text-right">alerts</th>
                        <th className="px-3 py-1.5 font-medium w-[60px] text-right">嚴重</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(r => {
                        const alertCount = Array.isArray(r.alerts) ? r.alerts.length : null
                        const sev = topSeverity(r.alerts)
                        return (
                          <tr key={r.query_idx} className="border-b border-slate-100 hover:bg-indigo-50/40 transition-colors">
                            <td className="px-3 py-1.5 tabular-nums text-slate-400">{r.query_idx}</td>
                            <td className="px-3 py-1.5 font-medium text-slate-800">{r.query}</td>
                            <td className="px-3 py-1.5"><StatusChip status={r.status} /></td>
                            <td className="px-3 py-1.5 text-right tabular-nums text-slate-700">
                              {r.status === 'ok' ? alertCount : <span className="text-slate-300">—</span>}
                            </td>
                            <td className="px-3 py-1.5 text-right">
                              <SeverityChip severity={sev} />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
