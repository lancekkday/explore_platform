import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import RunStatusBar from './RunStatusBar'

const TYPE_LABEL = { precise: '精準詞', broad: '泛詞' }

// Spec §5.5 status cell — inline dot + label
const STATUS_PRESET = {
  pending:     { dot: '#C0BFB9', text: '#5f5e5a', label: '等待' },
  running:     { dot: '#378ADD', text: '#0C447C', label: '執行中', pulse: true },
  ok:          { dot: '#1D9E75', text: '#0F6E56', label: '完成' },
  error:       { dot: '#E24B4A', text: '#791F1F', label: '失敗' },
  // Derived: row is pending AND parent run was cancelled — surface "waiting to resume"
  pending_resume: { dot: '#EF9F27', text: '#854F0B', label: '待續跑' },
}

function StatusDot({ status, isResumePending }) {
  const key = (status === 'pending' && isResumePending) ? 'pending_resume' : status
  const preset = STATUS_PRESET[key] || STATUS_PRESET.pending
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: preset.text }}>
      <span
        className={`inline-block w-1.5 h-1.5 rounded-full ${preset.pulse ? 'animate-pulse' : ''}`}
        style={{ background: preset.dot }}
      />
      {preset.label}
    </span>
  )
}

// Spec §5.5 嚴重度 — keep 4 levels (P0/P1/P2/INFO) per user; apply spec dimensions
const SEVERITY_STYLE = {
  P0:   { bg: '#FCEBEB', fg: '#791F1F' },
  P1:   { bg: '#FAEEDA', fg: '#854F0B' },
  P2:   { bg: '#EEEDFE', fg: '#3C3489' },
  INFO: { bg: '#F2F1ED', fg: '#5f5e5a' },
}
const SEVERITY_RANK = { P0: 4, P1: 3, P2: 2, INFO: 1 }

function SeverityPill({ severity }) {
  if (!severity) return <span className="text-text-tertiary text-[11px]">—</span>
  const s = SEVERITY_STYLE[severity] || SEVERITY_STYLE.INFO
  return (
    <span
      className="inline-block text-[10px] font-medium rounded-[8px] tabular-nums"
      style={{ background: s.bg, color: s.fg, padding: '2px 7px' }}
    >
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

// Hover popup over the severity chip — quick alert summary
// (replaces the legacy click-to-modal that lived in pre-step-4 BatchPage)
// Uses position:fixed + measured anchor so the popup escapes the table's
// overflow:hidden/overflow:auto ancestors.
function SeverityHoverCell({ alerts, query }) {
  const anchorRef = useRef(null)
  const hideTimerRef = useRef(null)
  const [pos, setPos] = useState(null)  // {top, right} viewport coords
  const sev = topSeverity(alerts)

  if (!sev) return <span className="text-text-tertiary text-[11px]">—</span>

  const list = Array.isArray(alerts) ? alerts : []
  const sortedAlerts = [...list].sort(
    (a, b) => (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0)
  )

  function cancelHide() {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current)
      hideTimerRef.current = null
    }
  }
  function scheduleHide() {
    // Short delay gives the cursor time to bridge the 6px gap into the popup.
    cancelHide()
    hideTimerRef.current = setTimeout(() => setPos(null), 150)
  }

  function handleEnter() {
    cancelHide()
    const r = anchorRef.current?.getBoundingClientRect()
    if (!r) return
    const POP_W = 480
    const POP_MAX_H = 320
    const margin = 8
    // Default: align right edge to chip's right edge, drop below
    let right = Math.max(margin, window.innerWidth - r.right)
    let top = r.bottom + 6
    // Flip up if not enough room below
    if (top + POP_MAX_H + margin > window.innerHeight) {
      top = Math.max(margin, r.top - POP_MAX_H - 6)
    }
    // Make sure popup doesn't disappear to the left
    if (window.innerWidth - right - POP_W < margin) {
      right = Math.max(margin, window.innerWidth - POP_W - margin)
    }
    setPos({ top, right })
  }

  return (
    <span
      ref={anchorRef}
      className="relative inline-block"
      onMouseEnter={handleEnter}
      onMouseLeave={scheduleHide}
    >
      <SeverityPill severity={sev} />
      {pos && (
        <div
          // Popup keeps itself alive while hovered — cursor can move from
          // chip into popup to scroll long alert lists without dismissing.
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
          className="bg-white rounded-lg p-3 text-left z-[200]"
          style={{
            position: 'fixed',
            top: `${pos.top}px`,
            right: `${pos.right}px`,
            width: '480px',
            maxHeight: '320px',
            overflowY: 'auto',
            border: '0.5px solid rgba(0,0,0,0.18)',
          }}
        >
          <div className="text-[12px] font-medium text-text-primary mb-2 pb-2" style={{ borderBottom: '0.5px solid rgba(0,0,0,0.08)' }}>
            <span className="text-text-primary mr-1.5">{query}</span>
            <span className="text-text-tertiary">·</span>
            <span className="text-text-secondary text-[11px] ml-1.5">{list.length} 筆 alert</span>
          </div>
          {sortedAlerts.map((a, i) => (
            <div key={i} className="py-1.5" style={{ borderTop: i === 0 ? 'none' : '0.5px solid rgba(0,0,0,0.06)' }}>
              <div className="flex items-center gap-2 mb-0.5 text-[11px]">
                <SeverityPill severity={a.severity} />
                <span className="text-text-tertiary">baseline #{a.baseline_rank}</span>
                <span className="text-text-tertiary">·</span>
                <span className="text-text-tertiary">A 排名 <span className="tabular-nums text-text-primary">{a.a_rank ?? '—'}</span></span>
                <span className="text-text-tertiary">·</span>
                <span className="text-text-tertiary">B 排名 <span className="tabular-nums text-text-primary">{a.b_rank ?? '—'}</span></span>
              </div>
              <div className="text-[11px] text-text-secondary leading-relaxed">{a.reason}</div>
            </div>
          ))}
        </div>
      )}
    </span>
  )
}

function ConfirmRestartModal({ runId, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-[400] flex items-center justify-center bg-black/30" onClick={onCancel}>
      <div className="bg-white rounded-lg w-[420px] max-w-[90vw] overflow-hidden border border-border-hair" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b border-border-hair text-[13px] font-medium text-text-primary">
          重新啟動新一輪?
        </div>
        <div className="px-4 py-3 text-[12px] text-text-secondary leading-relaxed">
          將開始新一輪巡檢,目前 run(
          <span className="font-mono text-text-primary">{runId.slice(0, 12)}…</span>
          )的進度將保留為歷史紀錄。確定繼續?
        </div>
        <div className="px-4 py-3 border-t border-border-hair flex items-center justify-end gap-2">
          <button onClick={onCancel} className="px-3 py-1.5 rounded text-[11px] text-text-secondary hover:bg-slate-100 transition-colors">
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 rounded text-[11px] font-medium text-white bg-text-primary hover:opacity-90 transition-opacity"
          >
            確定開始
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ABCheckRunPanel({ type }) {
  const {
    versionA, setVersionA, versionB, setVersionB,
    preciseRun, broadRun, startRun, cancelRun,
  } = useAppContext()
  const navigate = useNavigate()
  const run = type === 'precise' ? preciseRun : broadRun
  const [limit, setLimit] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)

  function jumpToKeyword(kw) {
    if (!kw) return
    // Polling timers live in AppContext (not unmounted by route change), so
    // the run keeps progressing even after we leave /batch.
    navigate(`/?keyword=${encodeURIComponent(kw)}&filter=diff`)
  }

  const rows = useMemo(() => {
    const arr = Array.from(run.rowsMap.values())
    arr.sort((a, b) => a.query_idx - b.query_idx)
    return arr
  }, [run.rowsMap])

  const isInflight = run.status === 'starting' || run.status === 'running'
  const isStarting = run.status === 'starting'
  const hasRun = !!run.runId
  // Spec Q3: 上一輪 cancelled → row pending = 待續跑(淡黃底)
  const showResumePending = run.status === 'cancelled' || run.status === 'interrupted'

  async function handleStartFresh() {
    await startRun(type, limit, null)
  }

  function handleRestartClick() {
    if (hasRun) setConfirmOpen(true)
    else handleStartFresh()
  }

  async function handleConfirmRestart() {
    setConfirmOpen(false)
    await handleStartFresh()
  }

  async function handleCancel() {
    await cancelRun(type)
  }

  async function handleResume() {
    await startRun(type, run.limitN ?? '', run.runId)
  }

  return (
    <div className="flex flex-col h-full">
      {/* §5.3 — Status Bar (cancelled/interrupted/done only; running 不出現) */}
      <RunStatusBar run={run} onResume={handleResume} />

      {/* §5.4 — Configuration Row */}
      <div className="px-[18px] py-[14px] flex items-center gap-5 flex-wrap border-b border-border-hair bg-white">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] uppercase tracking-[0.05em] font-medium text-text-tertiary">Limit</label>
          <input
            type="number"
            min="1"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            placeholder="全跑"
            disabled={isInflight}
            className="w-16 h-[30px] px-2 text-[13px] tabular-nums text-center border border-border-hair rounded text-text-primary placeholder:text-text-tertiary placeholder:text-[11px] disabled:bg-slate-50"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-[10px] uppercase tracking-[0.05em] font-medium text-text-tertiary">演算法比對</label>
          <div className="flex items-center gap-1.5">
            <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-chip-blue text-text-blue-dk">A</span>
            <input
              type="number"
              value={versionA}
              onChange={(e) => setVersionA(parseInt(e.target.value, 10) || 0)}
              disabled={isInflight}
              className="w-[52px] h-[30px] px-2 text-[13px] tabular-nums text-center border border-border-hair rounded text-text-primary disabled:bg-slate-50"
            />
            <span className="text-[11px] text-text-tertiary mx-0.5">vs</span>
            <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-chip-purple text-text-purple-dk">B</span>
            <input
              type="number"
              value={versionB}
              onChange={(e) => setVersionB(parseInt(e.target.value, 10) || 0)}
              disabled={isInflight}
              className="w-[52px] h-[30px] px-2 text-[13px] tabular-nums text-center border border-border-hair rounded text-text-primary disabled:bg-slate-50"
            />
          </div>
        </div>

        <div className="flex-1" />

        {isInflight ? (
          <button
            onClick={handleCancel}
            className="px-[14px] py-[6px] rounded-md text-[12px] font-medium text-status-red border border-status-red/40 bg-white hover:bg-chip-red transition-colors"
          >
            取消
          </button>
        ) : (
          <button
            onClick={handleRestartClick}
            className="px-[14px] py-[6px] rounded-md text-[12px] font-medium text-text-primary border border-border-hair bg-white hover:bg-page-bg transition-colors"
          >
            {isStarting ? '啟動中…' : (hasRun ? '重新啟動新一輪' : '啟動')}
          </button>
        )}
      </div>

      {/* Inline progress line (only while running — no full status bar per Q1) */}
      {isInflight && hasRun && (
        <div className="px-[18px] py-2 border-b border-border-hair bg-white flex items-center gap-3 text-[11px]">
          <span className="text-text-tertiary">進度</span>
          <span className="tabular-nums font-medium text-text-primary">{run.doneCount}/{run.total}</span>
          {run.runningIdx != null && (
            <>
              <span className="text-text-tertiary">·</span>
              <span className="text-text-tertiary">跑到</span>
              <span className="font-mono text-text-blue-dk">
                #{run.runningIdx} {run.rowsMap.get(run.runningIdx)?.query}
              </span>
            </>
          )}
          <div className="flex-1 mx-3 h-1 rounded-full bg-slate-200 overflow-hidden max-w-[280px]">
            <div
              className="h-full bg-status-blue transition-all duration-300"
              style={{ width: `${run.total > 0 ? (run.doneCount / run.total) * 100 : 0}%` }}
            />
          </div>
          {/* PR #28:running 中也顯示這個 run 的 locale。Resume 時這裡會跟
              ctx 全域選的不同 — 因為 backend 沿用了 parent 的。 */}
          {(run.lang || run.locale || run.channel) && (
            <span className="font-mono text-[10px] text-text-tertiary ml-auto">
              {run.lang} · {run.locale} · {run.channel}
            </span>
          )}
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-y-auto bg-page-bg px-[18px] py-3 custom-scroll">
        {run.error && (
          <div className="mb-3 px-3 py-2 bg-chip-red border border-status-red/40 rounded text-[11px] text-text-red-dk">
            {run.error}
          </div>
        )}

        {!hasRun && !run.error && (
          <div className="py-16 text-center text-[12px] text-text-tertiary">
            <div className="text-text-tertiary opacity-50 text-[32px] mb-2">📊</div>
            <div>輸入 Limit(可空)後按「啟動」開始 {TYPE_LABEL[type]} 巡檢</div>
            <div className="text-[10px] mt-2 opacity-80">啟動後表格立刻 render 所有 query 為「等待」,每 2 秒拉一次增量更新</div>
          </div>
        )}

        {hasRun && (
          <div className="bg-white border border-border-hair rounded-lg overflow-hidden">
            <div className="max-h-[calc(100vh-260px)] overflow-y-auto">
              {rows.length === 0 ? (
                <div className="py-6 text-center text-text-tertiary text-[11px]">尚無 row…</div>
              ) : (
                <table className="w-full text-left" style={{ tableLayout: 'fixed', borderCollapse: 'collapse' }}>
                  <colgroup>
                    <col style={{ width: '50px' }} />
                    <col />
                    <col style={{ width: '110px' }} />
                    <col style={{ width: '90px' }} />
                    <col style={{ width: '90px' }} />
                  </colgroup>
                  <thead>
                    <tr className="bg-page-bg sticky top-0 text-text-tertiary text-[10px] uppercase tracking-[0.05em]" style={{ borderBottom: '0.5px solid rgba(0,0,0,0.08)' }}>
                      <th className="font-medium text-left" style={{ padding: '9px 18px' }}>#</th>
                      <th className="font-medium text-left" style={{ padding: '9px 12px' }}>Query</th>
                      <th className="font-medium text-left" style={{ padding: '9px 12px' }}>狀態</th>
                      <th className="font-medium text-right" style={{ padding: '9px 12px' }}>Alerts</th>
                      <th className="font-medium text-right" style={{ padding: '9px 18px' }}>嚴重度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(r => {
                      const isResumePending = showResumePending && r.status === 'pending'
                      const alertCount = Array.isArray(r.alerts) ? r.alerts.length : null
                      const rowBg = isResumePending ? 'bg-amber-row' : ''
                      const idxColor = isResumePending ? 'text-text-amber-dk' : 'text-text-tertiary'
                      const queryColor = isResumePending ? 'text-text-secondary' : 'text-text-primary'
                      return (
                        <tr key={r.query_idx} className={rowBg} style={{ borderTop: '0.5px solid rgba(0,0,0,0.08)' }}>
                          <td className={`font-mono text-[12px] ${idxColor}`} style={{ padding: '11px 18px' }}>{r.query_idx}</td>
                          <td className={`text-[13px] font-medium ${queryColor}`} style={{ padding: '11px 12px' }}>
                            <button
                              onClick={() => jumpToKeyword(r.query)}
                              className="hover:underline hover:text-text-blue-dk transition-colors text-left"
                              title={`點擊跳至「${r.query}」單詞巡檢`}
                            >
                              {r.query}
                            </button>
                          </td>
                          <td style={{ padding: '11px 12px' }}><StatusDot status={r.status} isResumePending={isResumePending} /></td>
                          <td
                            className={`text-right tabular-nums text-[13px] ${alertCount > 0 ? 'font-medium text-text-primary' : 'text-text-tertiary'}`}
                            style={{ padding: '11px 12px' }}
                          >
                            {r.status === 'ok' ? (alertCount === 0 ? '0' : alertCount) : '—'}
                          </td>
                          <td className="text-right" style={{ padding: '11px 18px' }}><SeverityHoverCell alerts={r.alerts} query={r.query} /></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}
      </div>

      {confirmOpen && hasRun && (
        <ConfirmRestartModal
          runId={run.runId}
          onConfirm={handleConfirmRestart}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </div>
  )
}
