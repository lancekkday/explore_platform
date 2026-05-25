import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchABCheckHistory, fetchABCheckHistoryDetail } from '../api'

const TYPE_LABEL = { precise: '精準詞', broad: '泛詞' }

const STATUS_STYLE = {
  pending:     'bg-slate-100 text-slate-500 border-slate-200',
  running:     'bg-indigo-50 text-indigo-700 border-indigo-200',
  ok:          'bg-emerald-50 text-emerald-700 border-emerald-200',
  error:       'bg-rose-100 text-rose-700 border-rose-200',
  done:        'bg-emerald-50 text-emerald-700 border-emerald-200',
  failed:      'bg-rose-100 text-rose-700 border-rose-200',
  cancelled:   'bg-amber-100 text-amber-800 border-amber-200',
  interrupted: 'bg-amber-100 text-amber-800 border-amber-200',
  starting:    'bg-slate-100 text-slate-500 border-slate-200',
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

function fmtTime(iso) {
  if (!iso) return '—'
  return iso.replace(/\.\d+/, '').replace('T', ' ').replace(/\+\d{2}:\d{2}$/, '')
}

function SummaryPills({ summary }) {
  if (!summary) return <span className="text-slate-300">—</span>
  const cells = []
  if (summary.P0) cells.push({ k: 'P0', cls: 'text-rose-700' })
  if (summary.P1) cells.push({ k: 'P1', cls: 'text-amber-700' })
  if (summary.P2) cells.push({ k: 'P2', cls: 'text-indigo-700' })
  if (summary.INFO) cells.push({ k: 'INFO', cls: 'text-slate-600' })
  if (cells.length === 0) return <span className="text-emerald-700">✓ 0</span>
  return (
    <span className="inline-flex gap-2 tabular-nums">
      {cells.map(c => (
        <span key={c.k} className={c.cls}>{c.k} {summary[c.k]}</span>
      ))}
    </span>
  )
}

function HistoryList({ rows, filterType, setFilterType, onPick, loading, error, onRefresh }) {
  return (
    <>
      <div className="mb-3 flex items-center gap-2 text-[11px]">
        <span className="text-slate-500">type</span>
        {[
          { v: null,      l: '全部' },
          { v: 'precise', l: '精準詞' },
          { v: 'broad',   l: '泛詞' },
        ].map(opt => (
          <button
            key={opt.l}
            onClick={() => setFilterType(opt.v)}
            className={`px-2 py-0.5 rounded border text-[10px] transition-colors ${
              filterType === opt.v
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'
            }`}
          >
            {opt.l}
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={onRefresh}
          disabled={loading}
          className="px-2 py-0.5 rounded border text-[10px] bg-white text-slate-600 border-slate-300 hover:bg-slate-100 disabled:opacity-50"
        >
          {loading ? '載入中…' : '重新整理'}
        </button>
      </div>

      {error && (
        <div className="mb-3 px-3 py-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-700">
          {error}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        {rows.length === 0 && !loading ? (
          <div className="py-12 text-center text-[11px] text-slate-400">
            <div className="text-slate-300 text-[28px] mb-2">📜</div>
            尚無紀錄
          </div>
        ) : (
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="bg-slate-50/60 border-b border-slate-200 text-slate-500 text-[10px] uppercase tracking-wider sticky top-0">
                <th className="px-3 py-1.5 font-medium w-[110px]">run_id</th>
                <th className="px-3 py-1.5 font-medium w-[55px]">type</th>
                <th className="px-3 py-1.5 font-medium w-[80px]">狀態</th>
                <th className="px-3 py-1.5 font-medium w-[140px]">started_at</th>
                <th className="px-3 py-1.5 font-medium w-[60px] text-right">進度</th>
                <th className="px-3 py-1.5 font-medium">summary</th>
                <th className="px-3 py-1.5 font-medium w-[120px]">baseline</th>
                <th className="px-3 py-1.5 font-medium w-[110px]" title="v3 search API:lang / locale / channel">locale</th>
                <th className="px-3 py-1.5 font-medium w-[80px]" title="parent_run_id (resume chain)">續跑自</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr
                  key={r.run_id}
                  onClick={() => onPick(r.run_id)}
                  className="border-b border-slate-100 hover:bg-indigo-50/40 cursor-pointer transition-colors"
                >
                  <td className="px-3 py-1.5 font-mono tabular-nums text-slate-700 text-[10px]">
                    {r.run_id.slice(0, 10)}…
                  </td>
                  <td className="px-3 py-1.5 text-slate-700">{TYPE_LABEL[r.type] || r.type}</td>
                  <td className="px-3 py-1.5"><StatusChip status={r.status} /></td>
                  <td className="px-3 py-1.5 tabular-nums text-slate-600 text-[10px]">{fmtTime(r.started_at)}</td>
                  <td className="px-3 py-1.5 tabular-nums text-right text-slate-700">
                    {r.done_count}/{r.total_queries}
                  </td>
                  <td className="px-3 py-1.5"><SummaryPills summary={r.summary} /></td>
                  <td className="px-3 py-1.5 font-mono text-slate-500 text-[10px]">
                    {r.baseline_version ? r.baseline_version.slice(0, 15) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-slate-500 text-[10px]" title={`lang=${r.lang} locale=${r.locale} channel=${r.channel}`}>
                    {r.lang || r.locale || r.channel
                      ? `${r.lang}·${r.locale}·${r.channel}`
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-slate-500 text-[10px]">
                    {r.parent_run_id ? <span title={r.parent_run_id}>{r.parent_run_id.slice(0, 8)}…</span> : <span className="text-slate-300">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}

function HistoryDetail({ runId, onBack }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchABCheckHistoryDetail(runId)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setError(e?.message || '載入失敗') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [runId])

  const rows = useMemo(() => {
    const arr = Array.isArray(data?.rows) ? [...data.rows] : []
    arr.sort((a, b) => a.query_idx - b.query_idx)
    return arr
  }, [data])

  if (loading) {
    return (
      <div className="py-16 text-center text-[12px] text-slate-400">
        載入中…
      </div>
    )
  }
  if (error) {
    return (
      <>
        <button onClick={onBack} className="mb-3 text-[11px] text-slate-600 hover:text-slate-900">← 回列表</button>
        <div className="px-3 py-2 bg-rose-50 border border-rose-200 rounded text-[11px] text-rose-700">
          {error}
        </div>
      </>
    )
  }
  if (!data?.run) return null
  const r = data.run

  return (
    <>
      <button onClick={onBack} className="mb-3 text-[11px] text-slate-600 hover:text-slate-900">
        ← 回列表
      </button>

      <div className="mb-3 bg-white border border-slate-200 rounded-lg px-4 py-2.5 text-[11px]">
        <div className="flex items-center gap-3 mb-1">
          <span className="font-mono tabular-nums text-slate-700 text-[10px]">{r.run_id}</span>
          <StatusChip status={r.status} />
          <span className="text-slate-500">{TYPE_LABEL[r.type] || r.type}</span>
          <span className="text-slate-300">|</span>
          <span className="text-slate-500">A=<span className="font-mono">{r.version_a}</span> · B=<span className="font-mono">{r.version_b}</span></span>
          <span className="text-slate-300">|</span>
          <span className="text-slate-500">limit=<span className="font-mono">{r.limit_n ?? '全跑'}</span></span>
          <span className="text-slate-300">|</span>
          <span className="text-slate-500">進度 <span className="tabular-nums text-slate-800 font-semibold">{r.done_count}/{r.total_queries}</span></span>
        </div>
        <div className="flex items-center gap-3 text-slate-500 text-[10px]">
          <span>started {fmtTime(r.started_at)}</span>
          <span>finished {fmtTime(r.finished_at)}</span>
          <span>baseline <span className="font-mono">{r.baseline_version || '—'}</span></span>
          {r.parent_run_id && <span>parent <span className="font-mono">{r.parent_run_id.slice(0, 12)}…</span></span>}
          <div className="flex-1" />
          <SummaryPills summary={r.summary} />
        </div>
        {r.error_msg && (
          <div className="mt-1 text-rose-600 text-[10px]">error: {r.error_msg}</div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="max-h-[calc(100vh-280px)] overflow-y-auto">
          {rows.length === 0 ? (
            <div className="py-6 text-center text-slate-400 text-[11px]">無 checkpoint 紀錄</div>
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
                {rows.map(row => {
                  const alertCount = Array.isArray(row.alerts) ? row.alerts.length : null
                  const sev = topSeverity(row.alerts)
                  return (
                    <tr key={row.query_idx} className="border-b border-slate-100">
                      <td className="px-3 py-1.5 tabular-nums text-slate-400">{row.query_idx}</td>
                      <td className="px-3 py-1.5 font-medium text-slate-800">{row.query}</td>
                      <td className="px-3 py-1.5"><StatusChip status={row.status} /></td>
                      <td className="px-3 py-1.5 text-right tabular-nums text-slate-700">
                        {row.status === 'ok' ? alertCount : <span className="text-slate-300">—</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right"><SeverityChip severity={sev} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}

export default function ABCheckHistoryTable() {
  const [rows, setRows] = useState([])
  const [filterType, setFilterType] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedRunId, setSelectedRunId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchABCheckHistory(filterType, 50)
      setRows(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e?.message || '載入失敗')
    }
    setLoading(false)
  }, [filterType])

  useEffect(() => { load() }, [load])

  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 px-4 py-3 custom-scroll">
      {selectedRunId ? (
        <HistoryDetail runId={selectedRunId} onBack={() => setSelectedRunId(null)} />
      ) : (
        <HistoryList
          rows={rows}
          filterType={filterType}
          setFilterType={setFilterType}
          onPick={setSelectedRunId}
          loading={loading}
          error={error}
          onRefresh={load}
        />
      )}
    </div>
  )
}
