import { useMemo, useState } from 'react'
import { safeString } from '../utils/safeString'
import { prodMatchKey } from '../utils/prodMid'
import TierBadge from './ui/TierBadge'
import { IconTag } from './icons/Icons'
import { explainProduct } from '../api'

function NdcgBadges({ data }) {
  const m = data?.metrics || {}
  const n10 = Math.round((m.ndcg_at_10 ?? m.ndcg_10 ?? 0) * 100)
  const n50 = Math.round((m.ndcg_at_50 ?? m.ndcg_50 ?? 0) * 100)
  const n150 = Math.round((m.ndcg_at_150 ?? m.ndcg_150 ?? m.ndcg_at_300 ?? 0) * 100)
  const pill = 'text-[10px] px-1.5 py-px rounded-full bg-white/70 text-slate-700 tabular-nums'
  return (
    <div className="inline-flex gap-1">
      <span className={pill}>@10 {n10}</span>
      <span className={pill}>@50 {n50}</span>
      <span className={pill}>@150 {n150}</span>
    </div>
  )
}

function PanelHeader({ column, data, version, onVersionChange, onSubmit }) {
  const isA = column === 'A'
  const letter = (
    <span className="text-[13px] font-semibold text-slate-800">{column}</span>
  )
  const testExpLabel = (
    <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">test_exp</span>
  )
  const versionInput = (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      value={version}
      onChange={(e) => onVersionChange?.(e.target.value.replace(/\D/g, ''))}
      onKeyDown={(e) => { if (e.key === 'Enter') onSubmit?.() }}
      maxLength={4}
      className="w-[36px] h-[18px] text-[11px] font-medium text-slate-700 text-center border border-slate-300 rounded-[3px] bg-white outline-none focus:border-indigo-500"
    />
  )

  return (
    <>
      {/* Row 1: test_exp + version input (A: label left, input right; B: input left, label right) */}
      <div className="bg-slate-50 border-b border-slate-200 px-2.5 py-1 flex items-center gap-1.5">
        {isA ? (
          <>
            {testExpLabel}
            <span className="ml-auto">{versionInput}</span>
          </>
        ) : (
          <>
            {versionInput}
            <span className="ml-auto">{testExpLabel}</span>
          </>
        )}
      </div>
      {/* Row 2: letter + NDCG badges */}
      <div className="bg-slate-50 border-b border-slate-200 px-2.5 py-1 flex items-center">
        {isA ? (
          <>{letter}<span className="ml-auto"><NdcgBadges data={data} /></span></>
        ) : (
          <><NdcgBadges data={data} /><span className="ml-auto">{letter}</span></>
        )}
      </div>
    </>
  )
}

function BaselineBadge({ info }) {
  if (!info) return null
  const colors = info.kind === 'precise'
    ? 'bg-amber-100 text-amber-800 border-amber-300'
    : 'bg-indigo-50 text-indigo-700 border-indigo-300'
  return (
    <span className={`text-[9px] font-semibold tracking-wide px-1 py-px rounded border whitespace-nowrap ${colors}`}>
      {info.label}
    </span>
  )
}

function CrossRankTag({ column, otherRank, currentRank }) {
  const otherLabel = column === 'A' ? 'B' : 'A'
  if (otherRank == null) {
    return (
      <span className="text-[10px] text-rose-600 font-semibold whitespace-nowrap">
        {otherLabel} 未出現
      </span>
    )
  }
  let arrow = null
  let cls = 'text-slate-500'
  if (currentRank != null) {
    if (otherRank > currentRank) {
      // Other column rank is larger → this product moved DOWN in other column
      arrow = '▼'
      cls = 'text-rose-600 font-semibold'
    } else if (otherRank < currentRank) {
      // Other column rank is smaller → this product moved UP in other column
      arrow = '▲'
      cls = 'text-emerald-700 font-semibold'
    }
  }
  return (
    <span className={`text-[10px] tabular-nums whitespace-nowrap inline-flex items-center gap-0.5 ${cls}`}>
      <span>{otherLabel}#{otherRank}</span>
      {arrow && <span className="text-[11px] leading-none">{arrow}</span>}
    </span>
  )
}

function ResultRow({
  column,
  item,
  otherRank,
  baselineInfo,
  highlight,
  rowRef,
  onCalibrate,
  onExplain,
  explanation,
  keyword,
  showCrossRank,
}) {
  return (
    <div
      ref={rowRef}
      className={`group relative flex flex-col justify-center px-2.5 py-1 min-h-[42px] border-b border-slate-100 transition-colors ${
        highlight ? 'bg-amber-100' : 'hover:bg-slate-50'
      }`}
    >
      <div className="flex items-center gap-1.5">
        {/* rank */}
        <span className="text-[10px] text-slate-400 w-[20px] text-right tabular-nums">#{item.rank}</span>
        {/* baseline label before title */}
        <BaselineBadge info={baselineInfo} />
        {/* title — render as link only when we have a URL, else plain span */}
        {(() => {
          const href = item.url || (item.prod_mid ? `https://www.stage.kkday.com/zh-tw/product/${item.prod_mid}` : null)
          const name = safeString(item.name)
          if (href) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 min-w-0 text-[11px] leading-[1.4] text-slate-800 truncate hover:text-indigo-600 hover:underline"
                title={name}
              >
                {name}
              </a>
            )
          }
          return (
            <span
              className="flex-1 min-w-0 text-[11px] leading-[1.4] text-slate-800 truncate"
              title={name}
            >
              {name}
            </span>
          )
        })()}
        {/* Tier */}
        <TierBadge it={item} />
        {/* Cross-rank tag (only in diff/baseline mode) */}
        {showCrossRank && (
          <CrossRankTag column={column} otherRank={otherRank} currentRank={item.rank} />
        )}
      </div>
      {/* metadata (left) + mismatch reasons (right) in one row */}
      <div className="ml-[28px] mt-0.5 flex items-center gap-2 text-[9px] text-slate-500 leading-none">
        <span className="inline-flex items-center gap-0.5">
          <IconTag />
          <span className="uppercase tracking-wider">{safeString(item.main_cat_key) || 'UNIDENTIFIED'}</span>
        </span>
        <span className="uppercase tracking-wider">
          {(() => {
            const dests = Array.isArray(item.destinations) ? item.destinations : []
            if (dests.length === 0) return 'GLOBAL'
            const first = dests[0]
            return typeof first === 'object' ? safeString(first.name) : safeString(first)
          })()}
        </span>
        {item.show_order_count != null && item.show_order_count !== '' && (
          <span className="text-slate-400 tabular-nums">✦ {item.show_order_count}</span>
        )}
        {item.mismatch_reasons?.length > 0 && (
          <span
            className="ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 text-[9px] bg-rose-50 border border-rose-100 rounded italic text-rose-600/90 max-w-[420px]"
            title={item.mismatch_reasons.join(' | ')}
          >
            <span className="w-1 h-1 bg-rose-400 rounded-full shrink-0" />
            <span className="truncate">{item.mismatch_reasons.join(' | ')}</span>
          </span>
        )}
        {/* Hover actions — sits inline in meta row so baselines align with mismatch chip;
            always takes space (invisible until hover) to avoid layout jump. */}
        <div className={`${item.mismatch_reasons?.length > 0 ? '' : 'ml-auto'} flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none group-hover:pointer-events-auto`}>
          <button
            onClick={() => onExplain?.(item)}
            className={`inline-flex items-center px-1.5 py-0.5 text-[9px] font-medium rounded border leading-none transition-colors ${
              explanation
                ? 'bg-indigo-600 text-white border-indigo-700'
                : 'bg-white text-indigo-600 border-indigo-200 hover:bg-indigo-50'
            }`}
            title={`AI 解釋（關鍵字：${keyword}）`}
          >
            {explanation === 'loading' ? '…' : 'AI'}
          </button>
          <button
            onClick={() => onCalibrate?.(item)}
            className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-medium rounded border leading-none bg-white text-slate-700 border-slate-200 hover:bg-slate-100"
          >
            校正
          </button>
        </div>
      </div>
      {/* AI explanation (when active) */}
      {explanation && explanation !== 'loading' && explanation !== 'error' && (
        <div className="ml-[28px] mt-1 pl-2 border-l-2 border-indigo-300 text-[10.5px] leading-[1.5] text-slate-600">
          {explanation}
        </div>
      )}
      {explanation === 'error' && (
        <div className="ml-[28px] mt-1 pl-2 border-l-2 border-rose-300 text-[10px] text-rose-500">
          AI 解釋失敗，請稍後再試。
        </div>
      )}
    </div>
  )
}

// "Missing" row shown when a baseline product exists in the other column but not in this one (diff mode only)
// status: 'removed' | 'out_of_window' | 'check_failed' | undefined (legacy / not yet checked)
function MissingRow({ column, baselineInfo, item, status }) {
  const thisLabel = column === 'A' ? 'A' : 'B'
  const config = (() => {
    if (status === 'removed') {
      return { bg: 'bg-rose-100/50', tagBg: 'text-rose-700 bg-rose-200/70 px-1.5 rounded', tag: '商品下架', dashColor: 'text-rose-400' }
    }
    if (status === 'out_of_window') {
      return { bg: 'bg-orange-50/40', tagBg: 'text-orange-700 bg-orange-100 px-1.5 rounded', tag: '排名 >300', dashColor: 'text-orange-300' }
    }
    if (status === 'check_failed') {
      return { bg: 'bg-slate-50/60', tagBg: 'text-slate-600 bg-slate-200 px-1.5 rounded', tag: 'Stage 未確認', dashColor: 'text-slate-400' }
    }
    return { bg: 'bg-rose-50/30', tagBg: 'text-rose-600 font-medium', tag: '未出現', dashColor: 'text-rose-300' }
  })()
  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1.5 border-b border-slate-100 ${config.bg}`}>
      <span className={`text-[10px] w-[20px] text-right tabular-nums ${config.dashColor}`}>—</span>
      <span className="w-[5px] shrink-0" />
      <BaselineBadge info={baselineInfo} />
      <span className="flex-1 min-w-0 text-[11px] leading-[1.4] italic text-slate-400 truncate" title={item?.prod_nm}>
        {safeString(item?.prod_nm || `#${item?.prod_mid}`)}
      </span>
      <span className={`text-[10px] whitespace-nowrap ${config.tagBg}`}>{thisLabel} {config.tag}</span>
    </div>
  )
}

export default function AnnotatedResultList({
  column = 'A',
  data,
  version,
  onVersionChange,
  onSubmit,
  filterMode = 'all',
  focusIds,
  baselineMap,                  // Map<prod_mid, { label, kind, original }>
  otherResults,
  baselineAlerts,               // [{ prod_mid, status, stage_status, ... }] — for THIS column
  onCalibrate,
  keyword,
  rowRefs,
  highlightId,
}) {
  const alertStatusByMid = useMemo(() => {
    const m = new Map()
    for (const a of baselineAlerts || []) {
      if (a?.prod_mid != null) m.set(a.prod_mid, a.status)
    }
    return m
  }, [baselineAlerts])

  const [explanations, setExplanations] = useState({})

  const items = data?.results || []
  const otherItems = otherResults || []
  // Cross-column matching keys ONLY on a valid prod_mid (backend contract); rows
  // with no reliable id (prodMatchKey → null, also flagged in mid_warnings) are
  // left out of the maps instead of silently re-keying on `id`.
  const otherByMid = new Map(otherItems.filter(r => prodMatchKey(r) != null).map(r => [prodMatchKey(r), r]))
  const myByMid = new Map(items.filter(r => prodMatchKey(r) != null).map(r => [prodMatchKey(r), r]))

  const annotated = items.map(it => {
    const matchKey = prodMatchKey(it)
    const otherSameProduct = matchKey != null ? otherByMid.get(matchKey) : null
    return {
      item: it,
      // Row identity for React key / refs: prefer prod_mid, fall back to id so
      // anomalous rows still render (matching, above, deliberately does not).
      mid: it.prod_mid || it.id,
      // For cross-rank display, we want the SAME PRODUCT's rank in the other column (not whatever sits at the same rank)
      crossRank: otherSameProduct?.rank ?? null,
      baselineInfo: matchKey != null ? (baselineMap?.get(matchKey) || null) : null,
    }
  })

  // Build rendering list
  let rendered = []
  if (filterMode === 'diff' && baselineMap) {
    // Baseline-mode diff: keep only items whose prod_mid is in baselineMap
    rendered = annotated.filter(r => baselineMap.has(r.mid)).map(r => ({ type: 'row', ...r }))
    // Append "missing" rows for baseline products absent from THIS column
    for (const [mid, info] of baselineMap.entries()) {
      if (!myByMid.has(mid)) {
        rendered.push({ type: 'missing', mid, baselineInfo: info, original: info.original })
      }
    }
  } else if (filterMode === 'focus') {
    rendered = annotated.filter(r => focusIds?.has(r.mid)).map(r => ({ type: 'row', ...r }))
  } else {
    rendered = annotated.map(r => ({ type: 'row', ...r }))
  }

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

  // 只要有另一版資料就顯示 cross-rank 箭頭 (▲ 上升 / ▼ 下降);
  // 原本只在 baseline diff filter 才顯示,被使用者反映砍掉了
  const showCrossRank = Array.isArray(otherResults) && otherResults.length > 0

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-white border border-slate-200 rounded-md overflow-hidden">
      <PanelHeader
        column={column}
        data={data}
        version={version}
        onVersionChange={onVersionChange}
        onSubmit={onSubmit}
      />
      <div className="flex-1 overflow-y-auto">
        {rendered.length === 0 ? (
          <div className="py-12 text-center text-slate-300 text-[11px]">
            {items.length === 0 ? '無資料' : '此篩選下無項目'}
          </div>
        ) : (
          rendered.map((r, idx) => {
            if (r.type === 'missing') {
              return (
                <MissingRow
                  key={`m-${r.mid}-${idx}`}
                  column={column}
                  baselineInfo={r.baselineInfo}
                  item={r.original}
                  status={alertStatusByMid.get(r.mid)}
                />
              )
            }
            const mid = r.mid
            const refFn = (el) => {
              if (rowRefs && mid != null) rowRefs.current[`${column}:${mid}`] = el
            }
            const explanation = explanations[r.item.id]
            return (
              <ResultRow
                key={`${r.item.rank}-${mid}`}
                column={column}
                item={r.item}
                otherRank={r.crossRank}
                baselineInfo={r.baselineInfo}
                highlight={highlightId === mid}
                rowRef={refFn}
                onCalibrate={onCalibrate}
                onExplain={handleExplain}
                explanation={explanation}
                keyword={keyword}
                showCrossRank={showCrossRank}
              />
            )
          })
        )}
      </div>
    </div>
  )
}
