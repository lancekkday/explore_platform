import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'

const AUTO_DISMISS_MS = 8000

export default function BatchToast() {
  const { batchJustCompleted, setBatchJustCompleted, baselineReport } = useAppContext()
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!batchJustCompleted) return
    const id = setTimeout(() => setBatchJustCompleted(false), AUTO_DISMISS_MS)
    return () => clearTimeout(id)
  }, [batchJustCompleted, setBatchJustCompleted])

  // 已經在 /batch 就不顯示 (使用者已經看到結果)
  if (!batchJustCompleted || location.pathname === '/batch') return null

  const summary = baselineReport?.summary
  const totalAnomaly = summary?.total ?? 0
  const hasP0 = (summary?.P0 ?? 0) > 0
  const tone = hasP0 ? 'border-rose-300 bg-rose-50' : 'border-emerald-300 bg-emerald-50'
  const iconColor = hasP0 ? 'text-rose-600' : 'text-emerald-600'

  return (
    <div className="fixed top-12 right-4 z-[700] pointer-events-none">
      <div
        className={`pointer-events-auto rounded-lg border shadow-lg px-3 py-2 min-w-[260px] max-w-[340px] ${tone}`}
      >
        <div className="flex items-start gap-2">
          <span className={`text-[14px] leading-none mt-0.5 ${iconColor}`}>{hasP0 ? '⚠' : '✓'}</span>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-semibold text-slate-800">批次巡檢完成</div>
            <div className="text-[10px] text-slate-600 mt-0.5">
              {totalAnomaly === 0
                ? '所有 baseline 正常'
                : `${totalAnomaly} 個 query 異常${summary?.P0 ? ` · P0 ${summary.P0}` : ''}`}
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <button
                onClick={() => {
                  setBatchJustCompleted(false)
                  navigate('/batch')
                }}
                className="text-[10px] font-semibold text-indigo-600 hover:text-indigo-800"
              >
                查看報表 →
              </button>
              <button
                onClick={() => setBatchJustCompleted(false)}
                className="text-[10px] text-slate-400 hover:text-slate-600"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
