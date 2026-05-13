import { useState } from 'react'
import { safeString } from '../utils/safeString'
import TierBadge from './ui/TierBadge'
import { IconTag } from './icons/Icons'
import { explainProduct } from '../api'

const BASELINE_COLORS = {
  precise_top1: 'bg-amber-100 text-amber-800 border-amber-300',
  precise_top2: 'bg-amber-50 text-amber-700 border-amber-200',
  broad: 'bg-blue-50 text-blue-700 border-blue-200',
}

function BaselineBadge({ tag, profit, ctr, profitRank }) {
  if (!tag) return null
  const isPrecise = tag.startsWith('precise_')
  const colorClass = isPrecise
    ? BASELINE_COLORS[tag] || BASELINE_COLORS.precise_top1
    : BASELINE_COLORS.broad

  const label = isPrecise
    ? tag === 'precise_top1' ? 'Top1' : 'Top2'
    : `#${profitRank ?? '?'}`

  const tooltipText = isPrecise
    ? [
        `⭐ 精準詞守門商品 ${label}`,
        '此商品為該關鍵字的高成交核心商品，排名下降需特別關注',
        profit != null ? `利潤: ${profit}` : null,
        ctr != null ? `點擊率: ${ctr}%` : null,
      ].filter(Boolean).join('\n')
    : [
        `📊 泛詞守門商品 (利潤排名 #${profitRank})`,
        '此商品為該關鍵字下利潤排名前10的商品，需確保出現在搜尋結果中',
        profit != null ? `利潤: ${profit}` : null,
        ctr != null ? `點擊率: ${ctr}%` : null,
      ].filter(Boolean).join('\n')

  return (
    <span
      title={tooltipText}
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border text-[8px] font-black tracking-wide cursor-help shrink-0 ${colorClass}`}
    >
      {isPrecise ? '⭐' : '📊'} {label}
    </span>
  )
}

function RankDeltaBadge({ aRank, bRank }) {
  if (aRank == null || bRank == null) return null
  const delta = aRank - bRank  // positive = improved in B
  if (delta === 0) return null
  return (
    <span className={`text-[8.5px] font-black px-1.5 py-0.5 rounded ${
      delta > 0
        ? 'bg-emerald-50 text-emerald-700'
        : 'bg-rose-50 text-rose-700'
    }`}>
      {delta > 0 ? `▲${delta}` : `▼${Math.abs(delta)}`}
    </span>
  )
}

export default function AnnotatedResultList({
  items, title, total, color,
  onCalibrate, doubtOnly, keyword,
  versionLabel,
  otherVersionResults,  // for computing rank delta (optional)
  baselineDropMultiplier = 3,
  baselineOnly = false,
}) {
  const rawItems = Array.isArray(items) ? items : []

  const [explanations, setExplanations] = useState({})

  // Build other version rank lookup for delta display
  const otherRankMap = {}
  if (otherVersionResults) {
    for (const r of otherVersionResults) {
      const mid = r.prod_mid || r.id
      if (mid) otherRankMap[mid] = r.rank
    }
  }

  const filtered = baselineOnly
    ? rawItems.filter(it => it && it.baseline_tag)
    : rawItems

  const displayed = doubtOnly
    ? filtered.filter(it => {
        if (!it) return false
        // T3 or MISS
        if (it.tier === 0 || it.tier === 3) return true
        // Calibrated
        if (it.is_calibrated) return true
        // Baseline product that dropped significantly
        if (it.baseline_tag && it.baseline_profit_rank && it.rank > it.baseline_profit_rank * baselineDropMultiplier) return true
        // Significant rank change vs other version
        const mid = it.prod_mid || it.id
        if (mid && otherRankMap[mid] != null) {
          const delta = Math.abs(it.rank - otherRankMap[mid])
          if (delta >= 5) return true
        }
        return false
      })
    : filtered

  const handleExplain = async (it) => {
    const pid = it.id
    if (explanations[pid] && explanations[pid] !== 'error') {
      setExplanations(prev => { const n = { ...prev }; delete n[pid]; return n })
      return
    }
    setExplanations(prev => ({ ...prev, [pid]: 'loading' }))
    try {
      const res = await explainProduct(keyword, it)
      setExplanations(prev => ({ ...prev, [pid]: res.explanation || 'error' }))
    } catch {
      setExplanations(prev => ({ ...prev, [pid]: 'error' }))
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden text-slate-900">
      <div className="flex items-center justify-between py-2.5 px-5 border-b border-slate-100 bg-white/80 backdrop-blur-sm sticky top-0 z-10 shrink-0">
        <h3 className="font-black text-[11px] text-slate-800 tracking-[3px] uppercase flex items-center gap-2.5">
          <div className="w-1.5 h-3.5 rounded-full shadow-lg" style={{ backgroundColor: color }} />
          {title}
          {versionLabel && (
            <span className="ml-1 px-2 py-0.5 bg-slate-100 rounded text-[9px] font-mono">{versionLabel}</span>
          )}
        </h3>
        <span className="text-[10.5px] font-black text-indigo-700 bg-indigo-50 px-3 py-0.5 rounded-full border border-indigo-100 tabular-nums">
          {displayed.length} / {total}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto custom-scroll px-2 py-1 bg-white">
        {displayed.length === 0 ? (
          <div className="py-20 text-center flex flex-col items-center justify-center opacity-30 select-none">
            <div className="text-5xl mb-4">🔍</div>
            <div className="text-[10px] font-black text-slate-400 uppercase tracking-[10px]">NO DATA</div>
          </div>
        ) : (
          <div className="flex flex-col gap-0.5">
            {displayed.map((it) => {
              if (!it) return null
              const pid = it.id
              const explanation = explanations[pid]
              const isActive = !!explanation
              const hasBaseline = !!it.baseline_tag
              const otherRank = otherRankMap[it.prod_mid || it.id]

              return (
                <div
                  key={it.prod_mid || it.id}
                  className={`py-1.5 px-4 border-b border-slate-50 hover:bg-slate-50/80 transition-all group rounded-xl relative border-l-2 ${
                    it.tier === 0
                      ? 'border-l-rose-500 bg-rose-50/10'
                      : hasBaseline
                        ? 'border-l-amber-400 bg-amber-50/10'
                        : 'border-l-transparent hover:border-l-indigo-300'
                  }`}
                >
                  <div className="flex items-center gap-4">
                    <div className="w-9 shrink-0 flex flex-col items-center">
                      <span className="text-[11.5px] font-black text-slate-900 leading-none font-mono">#{it.rank}</span>
                      {otherRank != null && (
                        <RankDeltaBadge aRank={otherRank} bRank={it.rank} />
                      )}
                      {it.rank_delta != null && !otherRank && (
                        <span className={`text-[8.5px] font-black mt-1 px-1.5 py-0.5 rounded ${
                          it.rank_delta > 0 ? 'bg-emerald-50 text-emerald-700'
                          : it.rank_delta < 0 ? 'bg-rose-50 text-rose-700'
                          : 'text-slate-300'
                        }`}>
                          {it.rank_delta > 0 ? `▲${it.rank_delta}` : it.rank_delta < 0 ? `▼${Math.abs(it.rank_delta)}` : '•'}
                        </span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <BaselineBadge
                          tag={it.baseline_tag}
                          profit={it.baseline_profit}
                          ctr={it.baseline_ctr}
                          profitRank={it.baseline_profit_rank}
                        />
                        <a
                          href={it.url || (it.prod_mid ? `https://www.stage.kkday.com/zh-tw/product/${it.prod_mid}` : undefined)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`text-[13px] font-bold text-slate-800 truncate leading-tight tracking-tight transition-colors ${
                            (it.url || it.prod_mid) ? 'group-hover:text-indigo-600 hover:underline cursor-pointer' : ''
                          }`}
                          title={safeString(it.name)}
                        >
                          {safeString(it.name)}
                        </a>
                      </div>
                      {it.mismatch_reasons?.length > 0 && (
                        <div className="mt-1 flex items-center gap-1.5 px-2 py-0.5 bg-rose-50/50 border border-rose-100/50 rounded text-[9px] font-black text-rose-500/80 italic leading-none w-fit">
                          <div className="w-1 h-1 bg-rose-400 rounded-full animate-pulse" />
                          {it.mismatch_reasons.join(' | ')}
                        </div>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 opacity-70">
                        <span className="flex items-center gap-1 text-[9px] font-black text-slate-500">
                          <IconTag />
                          <span className="uppercase tracking-[1px] leading-none">
                            {safeString(it.main_cat_key) || 'UNIDENTIFIED'}
                          </span>
                        </span>
                        <span className="flex items-center gap-1 text-[9px] font-black text-slate-500 uppercase tracking-[1px] leading-none">
                          {(() => {
                            const dests = Array.isArray(it.destinations) ? it.destinations : []
                            if (dests.length === 0) return 'GLOBAL'
                            const first = dests[0]
                            return typeof first === 'object' ? safeString(first.name) : safeString(first)
                          })()}
                        </span>
                        {it.show_order_count && (
                          <span className="text-[9px] font-black text-slate-400 tabular-nums">
                            ✦ {it.show_order_count}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2.5 shrink-0">
                      <TierBadge it={it} />
                      <button
                        onClick={() => handleExplain(it)}
                        className={`h-7.5 px-3 rounded-lg border text-[10px] font-black transition-all shadow-sm outline-none ${
                          isActive
                            ? 'bg-indigo-600 border-indigo-700 text-white'
                            : 'border-slate-200 bg-white text-indigo-500 hover:border-indigo-400 hover:bg-indigo-50'
                        }`}
                      >
                        {explanation === 'loading' ? '…' : 'AI'}
                      </button>
                      <button
                        onClick={() => onCalibrate(it)}
                        className="h-7.5 px-4 rounded-lg border border-slate-200 bg-white text-slate-800 font-black text-[11px] shadow-sm hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all outline-none"
                      >
                        校正
                      </button>
                    </div>
                  </div>

                  {explanation && explanation !== 'loading' && (
                    <div className={`mt-2 mb-1 ml-13 pl-4 border-l-2 text-[11px] leading-relaxed font-bold ${
                      explanation === 'error' ? 'border-rose-300 text-rose-500' : 'border-indigo-300 text-slate-600'
                    }`}>
                      {explanation === 'error' ? 'AI 解釋失敗，請稍後再試。' : explanation}
                    </div>
                  )}
                  {explanation === 'loading' && (
                    <div className="mt-2 mb-1 ml-13 pl-4 border-l-2 border-indigo-200 flex items-center gap-2 text-[10px] text-indigo-400 font-black">
                      <div className="w-3 h-3 border-2 border-indigo-200 border-t-indigo-500 rounded-full animate-spin" />
                      AI 分析中...
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
