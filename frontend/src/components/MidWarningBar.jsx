import { useState } from 'react'
import { safeString } from '../utils/safeString'

/**
 * Surfaces products whose prod_mid could not be resolved to a non-zero positive
 * integer (the backend's mid_warnings). A real product always carries such an id,
 * so any entry here means the search API changed shape / returned a malformed id —
 * which would otherwise silently key the row on 0 and read as a false "未出現".
 */
const MAX_ROWS = 20  // cap rendered rows: a wholesale API shape change can flag every product

function WarningGroup({ column, warnings }) {
  if (!warnings?.length) return null
  const shown = warnings.slice(0, MAX_ROWS)
  const hidden = warnings.length - shown.length
  return (
    <div className="text-[11px]">
      <span className="font-semibold text-rose-700">{column} 版 {warnings.length} 筆</span>
      <ul className="mt-1 space-y-0.5">
        {shown.map((w, i) => (
          <li key={`${column}-${i}`} className="text-rose-600/90 tabular-nums">
            #{w.rank}
            <span className="ml-1 text-slate-600">{safeString(w.name) || '(無名稱)'}</span>
            <span className="ml-2 text-slate-400">
              prod_mid={JSON.stringify(w.prod_mid)} · prod_oid={JSON.stringify(w.prod_oid)}
            </span>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <div className="mt-0.5 text-slate-400 italic">…還有 {hidden} 筆（詳見後端 log / API 回應）</div>
      )}
    </div>
  )
}

export default function MidWarningBar({ aWarnings, bWarnings }) {
  const [open, setOpen] = useState(false)
  const total = (aWarnings?.length || 0) + (bWarnings?.length || 0)
  if (total === 0) return null

  return (
    <div className="mb-1 rounded-md border border-rose-300 bg-rose-50 px-3 py-1.5">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        <span className="text-[13px] leading-none">⚠️</span>
        <span className="text-[12px] font-semibold text-rose-800">
          {total} 筆商品的 prod_mid 無法解析
        </span>
        <span className="text-[10px] text-rose-600/80">
          （搜尋 API 可能改了 id 格式，這些列的比對結果不可信）
        </span>
        <span className="ml-auto text-[10px] text-rose-500">{open ? '收合 ▲' : '展開 ▼'}</span>
      </button>
      {open && (
        <div className="mt-1.5 pt-1.5 border-t border-rose-200 flex flex-col gap-2">
          <WarningGroup column="A" warnings={aWarnings} />
          <WarningGroup column="B" warnings={bWarnings} />
        </div>
      )}
    </div>
  )
}
