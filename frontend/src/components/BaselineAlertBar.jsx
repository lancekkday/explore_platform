export default function BaselineAlertBar({ alerts, baseline }) {
  if (!alerts || alerts.length === 0) return null
  if (!baseline?.has_data) return null

  const missing = alerts.filter(a => a.status === 'missing')
  const dropped = alerts.filter(a => a.status === 'dropped')
  const present = alerts.filter(a => a.status === 'present')
  const hasIssues = missing.length > 0 || dropped.length > 0

  return (
    <div className={`px-6 py-2.5 rounded-2xl border flex items-start gap-3 ${
      hasIssues
        ? 'bg-amber-50 border-amber-200'
        : 'bg-emerald-50 border-emerald-200'
    }`}>
      <span className="text-[16px] shrink-0 mt-0.5">{hasIssues ? '⚠️' : '✅'}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-[11px] font-black uppercase tracking-wider ${hasIssues ? 'text-amber-800' : 'text-emerald-800'}`}>
            Baseline {baseline.keyword_type === 'both' ? '精準+泛詞' : baseline.keyword_type === 'precise' ? '精準詞' : '泛詞'}
          </span>
          <span className="text-[10px] font-bold text-slate-500">
            {present.length} 正常 · {missing.length} 缺失 · {dropped.length} 大幅下降
          </span>
        </div>
        {hasIssues && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {missing.map(a => (
              <span key={a.prod_mid} className="px-2 py-0.5 bg-red-100 text-red-700 rounded border border-red-200 text-[9px] font-bold" title={`ID: ${a.prod_mid}`}>
                {a.prod_nm || `#${a.prod_mid}`} — 未出現在結果中
              </span>
            ))}
            {dropped.map(a => (
              <span key={a.prod_mid} className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded border border-orange-200 text-[9px] font-bold" title={`ID: ${a.prod_mid}`}>
                {a.prod_nm || `#${a.prod_mid}`} — 排名 #{a.current_rank}（期望前 {a.expected_rank} 名）
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
