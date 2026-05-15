// Parse "broad_rank_5" or "precise_top1" → readable label
function baselineLabel(tag) {
  if (!tag) return ''
  if (tag.startsWith('precise_top')) return `Top${tag.replace('precise_top', '')}`
  if (tag.startsWith('broad_rank_')) return `泛#${tag.replace('broad_rank_', '')}`
  return tag
}

function stageUrl(prod_mid) {
  return `https://www.stage.kkday.com/zh-tw/product/${prod_mid}`
}

function bucket(aAlerts, bAlerts, abComparison) {
  const aByMid = new Map()
  for (const x of aAlerts || []) aByMid.set(x.prod_mid, x)
  const bByMid = new Map()
  for (const x of bAlerts || []) bByMid.set(x.prod_mid, x)

  const buckets = {
    both_missing: [],
    b_missing: [],
    a_missing: [],
    ab_changed: [],
    a_dropped: [],
    b_dropped: [],
  }

  const assigned = new Set()  // prod_mid already placed
  const allMids = new Set([
    ...(aAlerts || []).map(x => x.prod_mid),
    ...(bAlerts || []).map(x => x.prod_mid),
    ...((abComparison?.rank_changes) || []).map(x => x.prod_mid),
  ])

  for (const mid of allMids) {
    const a = aByMid.get(mid)
    const b = bByMid.get(mid)
    const aStatus = a?.status
    const bStatus = b?.status
    const name = a?.prod_nm || b?.prod_nm
    const tag = a?.baseline_tag || b?.baseline_tag

    const entry = {
      prod_mid: mid,
      prod_nm: name,
      baseline_tag: tag,
      baseline_label: baselineLabel(tag),
    }

    // Priority: both missing > B missing > A missing > AB changed > A dropped > B dropped
    if (aStatus === 'missing' && bStatus === 'missing') {
      buckets.both_missing.push({ ...entry, hint: 'A,B' })
      assigned.add(mid)
      continue
    }
    if (bStatus === 'missing' && aStatus !== 'missing') {
      buckets.b_missing.push(entry)
      assigned.add(mid)
      continue
    }
    if (aStatus === 'missing' && bStatus !== 'missing') {
      buckets.a_missing.push(entry)
      assigned.add(mid)
      continue
    }
  }

  // AB compare changes for products not yet placed
  for (const rc of (abComparison?.rank_changes) || []) {
    if (assigned.has(rc.prod_mid)) continue
    if (rc.a_rank == null || rc.b_rank == null) continue
    const delta = rc.delta ?? (rc.b_rank - rc.a_rank)
    if (Math.abs(delta) <= 5) continue
    buckets.ab_changed.push({
      prod_mid: rc.prod_mid,
      prod_nm: rc.name,
      baseline_tag: rc.baseline_tag,
      baseline_label: baselineLabel(rc.baseline_tag),
      hint: delta > 0 ? 'B低' : 'A低',
      a_rank: rc.a_rank,
      b_rank: rc.b_rank,
    })
    assigned.add(rc.prod_mid)
  }

  // A dropped (not in any missing/changed)
  for (const a of aAlerts || []) {
    if (assigned.has(a.prod_mid)) continue
    if (a.status !== 'dropped') continue
    buckets.a_dropped.push({
      prod_mid: a.prod_mid,
      prod_nm: a.prod_nm,
      baseline_tag: a.baseline_tag,
      baseline_label: baselineLabel(a.baseline_tag),
      a_rank: a.current_rank,
      expected_rank: a.expected_rank,
    })
    assigned.add(a.prod_mid)
  }

  // B dropped (not in any other bucket)
  for (const b of bAlerts || []) {
    if (assigned.has(b.prod_mid)) continue
    if (b.status !== 'dropped') continue
    buckets.b_dropped.push({
      prod_mid: b.prod_mid,
      prod_nm: b.prod_nm,
      baseline_tag: b.baseline_tag,
      baseline_label: baselineLabel(b.baseline_tag),
      b_rank: b.current_rank,
      expected_rank: b.expected_rank,
    })
    assigned.add(b.prod_mid)
  }

  const total =
    buckets.both_missing.length +
    buckets.b_missing.length +
    buckets.a_missing.length +
    buckets.ab_changed.length +
    buckets.a_dropped.length +
    buckets.b_dropped.length

  return { buckets, total }
}

function Chip({ item, onChipClick }) {
  const title = [
    `${item.baseline_label || ''} ${item.prod_nm || `#${item.prod_mid}`}`,
    item.a_rank != null ? `A 排名 #${item.a_rank}` : null,
    item.b_rank != null ? `B 排名 #${item.b_rank}` : null,
    item.expected_rank ? `預期排名 #${item.expected_rank}` : null,
  ].filter(Boolean).join(' · ')

  return (
    <a
      href={stageUrl(item.prod_mid)}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => onChipClick?.(item)}
      className="inline-flex items-center gap-0.5 px-1.5 py-[1px] rounded-[3px] text-[10px] whitespace-nowrap max-w-[260px] transition-opacity hover:opacity-80 hover:underline"
      style={{ background: '#F5C4B3', color: '#993C1D' }}
      title={title}
    >
      {item.baseline_label && (
        <span className="text-[9px] opacity-70">{item.baseline_label}</span>
      )}
      <span className="truncate">{item.prod_nm || `#${item.prod_mid}`}</span>
      {item.hint && (
        <span className="text-[9px] opacity-60 ml-0.5">({item.hint})</span>
      )}
    </a>
  )
}

function CategoryRow({ label, items, onChipClick }) {
  if (!items.length) return null
  return (
    <div className="flex items-start gap-1.5 flex-wrap">
      <span className="text-[10px] font-semibold whitespace-nowrap leading-[18px]" style={{ color: '#854F0B' }}>
        {label}（{items.length}）：
      </span>
      <div className="inline-flex items-center gap-1 flex-wrap">
        {items.slice(0, 6).map(it => (
          <Chip key={it.prod_mid} item={it} onChipClick={onChipClick} />
        ))}
        {items.length > 6 && (
          <span className="text-[10px]" style={{ color: '#854F0B' }}>
            +{items.length - 6}
          </span>
        )}
      </div>
    </div>
  )
}

export default function BaselineAlertBar({ aAlerts, bAlerts, abComparison, baseline, onChipClick }) {
  if (!baseline?.has_data) return null

  const { buckets, total } = bucket(aAlerts, bAlerts, abComparison)
  if (total === 0) return null

  return (
    <div
      className="flex flex-col gap-1 mb-[7px] px-2.5 py-1.5 rounded-[6px] border text-[10px]"
      style={{
        background: 'rgba(250, 238, 218, 0.55)',
        borderColor: '#FAC775',
        color: '#854F0B',
      }}
    >
      <div className="flex items-center gap-2 leading-tight">
        <span className="text-[12px] leading-none">⚠</span>
        <span className="font-semibold">Baseline 異常 {total} 筆</span>
      </div>
      <CategoryRow label="A、B 雙消失" items={buckets.both_missing} onChipClick={onChipClick} />
      <CategoryRow label="B 消失" items={buckets.b_missing} onChipClick={onChipClick} />
      <CategoryRow label="A 消失" items={buckets.a_missing} onChipClick={onChipClick} />
      <CategoryRow label="A vs B 變動 > 5" items={buckets.ab_changed} onChipClick={onChipClick} />
      <CategoryRow label="A 排名偏離 baseline" items={buckets.a_dropped} onChipClick={onChipClick} />
      <CategoryRow label="B 排名偏離 baseline" items={buckets.b_dropped} onChipClick={onChipClick} />
    </div>
  )
}
