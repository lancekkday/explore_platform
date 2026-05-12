import { useState } from 'react'
import { runABCheck } from '../api'

const SEVERITY_COLORS = {
  P0: 'bg-red-100 text-red-800 border-red-200',
  P1: 'bg-orange-100 text-orange-800 border-orange-200',
  P2: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  INFO: 'bg-slate-100 text-slate-600 border-slate-200',
}

const SEVERITY_ROW = {
  P0: 'bg-red-50/60',
  P1: 'bg-orange-50/40',
  P2: '',
  INFO: '',
}

export default function ABCheckPanel() {
  const [versionA, setVersionA] = useState(3)
  const [versionB, setVersionB] = useState(3)
  const [checkType, setCheckType] = useState('all') // 'all' | 'precise' | 'broad'
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [severityFilter, setSeverityFilter] = useState('all')

  const handleRun = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await runABCheck(
        parseInt(versionA),
        parseInt(versionB),
        checkType === 'broad',   // skip_precise
        checkType === 'precise', // skip_broad
      )
      if (res.success) {
        setResult(res)
      } else {
        setError(res.detail || '巡檢失敗')
      }
    } catch {
      setError('伺服器連線異常')
    }
    setLoading(false)
  }

  const filtered = result?.alerts?.filter(a =>
    severityFilter === 'all' || a.severity === severityFilter
  ) || []

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 設定區 */}
      <div className="px-8 py-3 bg-white border-b border-slate-200 shadow-sm flex items-center gap-5 shrink-0 z-20">
        <h2 className="text-[14px] font-black text-slate-900 tracking-tight uppercase leading-none shrink-0">AB 版本巡檢</h2>

        <div className="flex items-center gap-2">
          <label className="text-[10px] font-black text-slate-500 uppercase tracking-wider">Version A</label>
          <input
            type="number"
            value={versionA}
            onChange={e => setVersionA(e.target.value)}
            className="w-16 px-2 py-1.5 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
          />
        </div>

        <span className="text-slate-300 font-black text-[14px]">vs</span>

        <div className="flex items-center gap-2">
          <label className="text-[10px] font-black text-slate-500 uppercase tracking-wider">Version B</label>
          <input
            type="number"
            value={versionB}
            onChange={e => setVersionB(e.target.value)}
            className="w-16 px-2 py-1.5 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
          />
        </div>

        <div className="flex gap-1 text-[10px] font-black">
          {[['all', '全部'], ['precise', '精準詞'], ['broad', '泛詞']].map(([v, label]) => (
            <button
              key={v}
              onClick={() => setCheckType(v)}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                checkType === v
                  ? 'bg-[#0F172A] text-white border-slate-900'
                  : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <button
          onClick={handleRun}
          disabled={loading}
          className={`px-8 py-2 rounded-xl font-black text-[11px] tracking-[3px] uppercase transition-all shadow-lg ${
            loading
              ? 'bg-slate-200 text-slate-400 cursor-not-allowed border-2 border-slate-300'
              : 'bg-[#0F172A] text-white hover:bg-black active:scale-95 border-2 border-[#0F172A]'
          }`}
        >
          {loading ? '巡檢中...' : '開始巡檢'}
        </button>

        {error && <span className="text-red-500 text-[11px] font-bold">{error}</span>}
      </div>

      {/* 結果區 */}
      <div className="flex-1 overflow-hidden flex flex-col p-4 gap-4">
        {loading && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-[4px] border-white/10 border-t-indigo-600 rounded-full animate-spin shadow-2xl" />
            <div className="text-indigo-900 font-black text-[11px] tracking-[6px] animate-pulse uppercase">Checking</div>
          </div>
        )}

        {!loading && result && (
          <>
            {/* 摘要 */}
            <div className="flex gap-3 shrink-0">
              {[
                { label: '總告警', value: result.summary.total, color: 'text-slate-900 bg-white border-slate-200' },
                { label: 'P0', value: result.summary.P0, color: result.summary.P0 > 0 ? 'text-red-800 bg-red-50 border-red-200' : 'text-slate-400 bg-white border-slate-200' },
                { label: 'P1', value: result.summary.P1, color: result.summary.P1 > 0 ? 'text-orange-800 bg-orange-50 border-orange-200' : 'text-slate-400 bg-white border-slate-200' },
                { label: 'P2', value: result.summary.P2, color: result.summary.P2 > 0 ? 'text-yellow-800 bg-yellow-50 border-yellow-200' : 'text-slate-400 bg-white border-slate-200' },
                { label: 'INFO', value: result.summary.INFO, color: 'text-slate-500 bg-white border-slate-200' },
              ].map(({ label, value, color }) => (
                <div key={label} className={`px-5 py-3 rounded-xl border-2 ${color} flex flex-col items-center min-w-[80px]`}>
                  <span className="text-[22px] font-black font-mono">{value}</span>
                  <span className="text-[9px] font-black uppercase tracking-widest mt-0.5">{label}</span>
                </div>
              ))}

              <div className="flex-1" />

              <div className="flex items-center gap-1 text-[10px] font-black">
                <span className="text-slate-400 mr-1">篩選:</span>
                {['all', 'P0', 'P1', 'P2', 'INFO'].map(s => (
                  <button
                    key={s}
                    onClick={() => setSeverityFilter(s)}
                    className={`px-2.5 py-1 rounded-md border transition-all ${
                      severityFilter === s
                        ? 'bg-[#0F172A] text-white border-slate-900'
                        : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
                    }`}
                  >
                    {s === 'all' ? '全部' : s}
                  </button>
                ))}
              </div>
            </div>

            {/* 告警列表 */}
            <div className="flex-1 bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden flex flex-col">
              <div className="overflow-y-auto flex-1 custom-scroll">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10 font-mono text-[9px] text-slate-400 uppercase tracking-widest">
                      <th className="px-4 py-3 text-center">嚴重度</th>
                      <th className="px-4 py-3 text-center border-l border-slate-100">類型</th>
                      <th className="px-4 py-3 border-l border-slate-100">詞類</th>
                      <th className="px-6 py-3 border-l border-slate-100">搜尋詞</th>
                      <th className="px-4 py-3 text-center border-l border-slate-100">prod_mid</th>
                      <th className="px-4 py-3 text-center border-l border-slate-100">Baseline</th>
                      <th className="px-4 py-3 text-center border-l border-slate-100">A 排名</th>
                      <th className="px-4 py-3 text-center border-l border-slate-100">B 排名</th>
                      <th className="px-6 py-3 border-l border-slate-100">原因</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {filtered.map((a, i) => (
                      <tr key={i} className={`hover:bg-slate-50 transition-all ${SEVERITY_ROW[a.severity] || ''}`}>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`px-2 py-0.5 rounded border text-[10px] font-black ${SEVERITY_COLORS[a.severity]}`}>{a.severity}</span>
                        </td>
                        <td className="px-4 py-2.5 text-center border-l border-slate-50 text-[10px] font-bold text-slate-500">
                          {a.alert_type === 'main' ? '主告警' : '旁路'}
                        </td>
                        <td className="px-4 py-2.5 border-l border-slate-50 text-[10px] font-bold text-slate-600">
                          {a.keyword_type === 'precise' ? '精準' : '泛詞'}
                        </td>
                        <td className="px-6 py-2.5 border-l border-slate-50 font-black text-[12px] text-slate-900">{a.query}</td>
                        <td className="px-4 py-2.5 text-center border-l border-slate-50 font-mono text-[11px] text-slate-600">{a.prod_mid}</td>
                        <td className="px-4 py-2.5 text-center border-l border-slate-50 font-mono text-[11px] text-slate-600">#{a.baseline_rank}</td>
                        <td className="px-4 py-2.5 text-center border-l border-slate-50 font-mono text-[11px] font-bold text-slate-700">
                          {a.a_rank != null ? `#${a.a_rank}` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-center border-l border-slate-50 font-mono text-[11px] font-bold text-slate-700">
                          {a.b_rank != null ? `#${a.b_rank}` : <span className="text-red-500">消失</span>}
                        </td>
                        <td className="px-6 py-2.5 border-l border-slate-50 text-[11px] text-slate-600">{a.reason}</td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr>
                        <td colSpan={9} className="py-16 text-center text-slate-300 font-black italic tracking-widest uppercase text-[12px]">
                          {result.summary.total === 0 ? '無告警 — 兩版結果一致' : '無符合篩選條件的告警'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {!loading && !result && (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-slate-200 text-[40px] mb-4">⚖️</div>
              <div className="text-slate-400 font-black text-[12px] tracking-widest uppercase">設定 A / B 版本後開始巡檢</div>
              <div className="text-slate-300 text-[10px] mt-2 font-bold">比對兩個搜尋演算法版本的排名變化</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
