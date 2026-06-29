import { useEffect, useState } from 'react'
import { fetchBaselineSourceStatus } from '../api'

// Polls GET /api/baseline/source-status; shows top banner when BQ fetch failed
// or guardrail (row count drop) tripped. User-dismissible — re-appears on next
// failed status or new last_run timestamp.
export default function BaselineStatusBanner() {
  const [status, setStatus] = useState(null)
  const [dismissedTs, setDismissedTs] = useState(null)

  useEffect(() => {
    const load = () => fetchBaselineSourceStatus().then(r => r?.success && setStatus(r)).catch(() => {})
    load()
    const id = setInterval(load, 60_000)  // poll every 60s
    return () => clearInterval(id)
  }, [])

  const lr = status?.last_run
  if (!lr) return null

  const hasWarnings = Array.isArray(lr.warnings) && lr.warnings.length > 0
  const visible = (!lr.success || hasWarnings) && dismissedTs !== lr.ts
  if (!visible) return null

  const isError = !lr.success
  const color = isError
    ? 'bg-red-50 border-red-300 text-red-800'
    : 'bg-amber-50 border-amber-300 text-amber-900'
  const icon = isError ? '✗' : '⚠'
  const headline = isError ? 'BQ baseline 抽取失敗' : 'BQ baseline 異常警告'

  return (
    <div className={`shrink-0 border-b px-6 py-2 flex items-center gap-3 text-[11px] font-bold ${color}`}>
      <span className="text-[14px]">{icon}</span>
      <div className="flex-1 leading-tight">
        <span className="font-black mr-2">{headline}</span>
        <span className="font-mono text-[10px] opacity-80 mr-2">{lr.ts}</span>
        {isError && lr.error && <span className="opacity-90">{lr.error}</span>}
        {!isError && hasWarnings && <span className="opacity-90">{lr.warnings.join('；')}</span>}
        <span className="ml-2 opacity-70">
          (精準詞 {lr.precise_rows} / 泛詞 {lr.broad_rows}，下次 cron 仍會嘗試)
        </span>
      </div>
      <button
        onClick={() => setDismissedTs(lr.ts)}
        className="text-[14px] opacity-60 hover:opacity-100 shrink-0"
        title="關閉提示"
      >✕</button>
    </div>
  )
}
