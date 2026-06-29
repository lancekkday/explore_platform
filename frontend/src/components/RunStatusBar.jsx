import { useCopyToClipboard } from '../utils/useCopyToClipboard'

// Inline tabler-style SVG icons (avoid @tabler/icons-react dep)
function IconPause({ className = '' }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="6" y="5" width="4" height="14" rx="1" />
      <rect x="14" y="5" width="4" height="14" rx="1" />
    </svg>
  )
}
function IconCheck({ className = '' }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12l5 5L20 7" />
    </svg>
  )
}
function IconCopy({ className = '' }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="8" y="8" width="12" height="12" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  )
}
function IconPlay({ className = '' }) {
  return (
    <svg className={className} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M7 4v16l13 -8z" />
    </svg>
  )
}
function IconAlert({ className = '' }) {
  return (
    <svg className={className} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71 -3L13.71 3.86a2 2 0 0 0 -3.42 0z" />
    </svg>
  )
}

function CopyButton({ runId }) {
  const [copied, copy] = useCopyToClipboard()

  function handleCopy(e) {
    e.stopPropagation()
    copy(runId)
  }

  return (
    <button
      onClick={handleCopy}
      className="relative inline-flex items-center justify-center w-5 h-5 rounded hover:bg-black/5 transition-colors opacity-60 hover:opacity-100"
      title="複製 run_id"
    >
      <IconCopy />
      {copied && (
        <span className="absolute left-full ml-2 px-1.5 py-0.5 rounded bg-black text-white text-[10px] whitespace-nowrap">
          已複製
        </span>
      )}
    </button>
  )
}

function ProgressLine({ done, total, fillColor, trackColor }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="inline-flex items-center gap-2">
      <div className="w-[120px] h-1 rounded-full overflow-hidden" style={{ background: trackColor }}>
        <div className="h-full transition-all duration-300" style={{ width: `${pct}%`, background: fillColor }} />
      </div>
      <span className="text-[12px] font-medium tabular-nums" style={{ color: fillColor === '#1D9E75' ? '#0F6E56' : '#854F0B' }}>
        {done} / {total}
      </span>
    </div>
  )
}

function SummaryInline({ summary }) {
  if (!summary) return null
  const cells = []
  if (summary.P0) cells.push({ k: 'P0', cls: 'text-text-red-dk' })
  if (summary.P1) cells.push({ k: 'P1', cls: 'text-text-amber-dk' })
  if (summary.P2) cells.push({ k: 'P2', cls: 'text-text-purple-dk' })
  if (summary.INFO) cells.push({ k: 'INFO', cls: 'text-text-tertiary' })
  if (cells.length === 0) {
    return <span className="text-[11px] text-text-green-dk">無 alert</span>
  }
  return (
    <span className="inline-flex items-center gap-2 text-[11px] tabular-nums">
      {cells.map(c => (
        <span key={c.k} className={c.cls}>
          {c.k} {summary[c.k]}
        </span>
      ))}
    </span>
  )
}

// Spec §5.3 — only renders for cancelled/interrupted/done/failed; null
// otherwise (running 不出現, per user Q1).
const FAILED_PALETTE = {
  bg:         '#FCEBEB',
  borderBot:  '#F2BABA',
  iconBg:     '#E24B4A',
  textMain:   '#791F1F',
  textSub:    'rgba(121, 31, 31, 0.75)',
  progressFill:  '#E24B4A',
  progressTrack: 'rgba(121, 31, 31, 0.15)',
}
const AMBER_PALETTE = {
  bg:         '#FAEEDA',
  borderBot:  '#F0D49B',
  iconBg:     '#EF9F27',
  textMain:   '#854F0B',
  textSub:    'rgba(133, 79, 11, 0.75)',
  progressFill:  '#EF9F27',
  progressTrack: 'rgba(133, 79, 11, 0.15)',
}
const GREEN_PALETTE = {
  bg:         '#EAF7F1',
  borderBot:  '#B7E2D2',
  iconBg:     '#1D9E75',
  textMain:   '#0F6E56',
  textSub:    'rgba(15, 110, 86, 0.75)',
  progressFill:  '#1D9E75',
  progressTrack: 'rgba(15, 110, 86, 0.15)',
}

export default function RunStatusBar({ run, onResume }) {
  if (!run?.runId) return null
  const status = run.status

  const isInterrupted = status === 'cancelled' || status === 'interrupted'
  const isDone = status === 'done'
  const isFailed = status === 'failed'
  if (!isInterrupted && !isDone && !isFailed) return null

  const remaining = Math.max(0, run.total - run.doneCount)
  const showResumeCTA = isInterrupted && remaining > 0

  const palette = isFailed ? FAILED_PALETTE : isInterrupted ? AMBER_PALETTE : GREEN_PALETTE
  const Icon = isFailed ? IconAlert : isInterrupted ? IconPause : IconCheck
  const headLabel = isFailed
    ? '失敗'
    : isInterrupted
      ? (status === 'cancelled' ? '已中斷' : '已中斷(處理程序重啟)')
      : '完成'

  return (
    <div
      className="px-[18px] py-[14px] flex items-center gap-5 flex-wrap"
      style={{ background: palette.bg, borderBottom: `0.5px solid ${palette.borderBot}` }}
    >
      <span
        className="inline-flex items-center justify-center w-[22px] h-[22px] rounded-full text-white shrink-0"
        style={{ background: palette.iconBg }}
      >
        <Icon />
      </span>

      <div className="flex flex-col gap-[2px] flex-1 min-w-[200px]">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] font-medium" style={{ color: palette.textMain }}>{headLabel}</span>
          <span style={{ color: palette.textMain, opacity: 0.6 }}>·</span>
          <span className="font-mono text-[11px]" style={{ color: palette.textMain }}>
            {run.runId.slice(0, 12)}…
          </span>
          <span style={{ color: palette.textMain }}>
            <CopyButton runId={run.runId} />
          </span>
        </div>
        <div className="text-[11px]" style={{ color: palette.textSub }}>
          {isInterrupted && `剩下 ${remaining} 個 query 未跑,可從中斷處繼續`}
          {isDone && <SummaryInline summary={run.summary} />}
          {isFailed && (run.errorMsg || run.error || '伺服器異常,請檢查 backend log')}
        </div>
        {/* PR #28: 顯示這個 run 的 locale。Interrupted 時特別標「續跑沿用」提醒
            使用者:即使他現在 dropdown 切到別的 locale,續跑仍會用這組值。 */}
        {(run.lang || run.locale || run.channel) && (
          <div className="text-[10px] font-mono" style={{ color: palette.textSub, opacity: 0.85 }}>
            locale:<span style={{ color: palette.textMain }}>{run.lang}</span>
            {' · '}<span style={{ color: palette.textMain }}>{run.locale}</span>
            {' · '}<span style={{ color: palette.textMain }}>{run.channel}</span>
            {isInterrupted && <span className="ml-2 opacity-75">(續跑沿用)</span>}
          </div>
        )}
      </div>

      <ProgressLine
        done={run.doneCount}
        total={run.total}
        fillColor={palette.progressFill}
        trackColor={palette.progressTrack}
      />

      {showResumeCTA && (
        <button
          onClick={onResume}
          className="inline-flex items-center gap-1.5 px-[14px] py-[6px] rounded-md text-[12px] font-medium text-white shrink-0 hover:brightness-105 transition-[filter]"
          style={{ background: palette.iconBg }}
        >
          <IconPlay />
          續跑剩下 {remaining} 個
        </button>
      )}
    </div>
  )
}
