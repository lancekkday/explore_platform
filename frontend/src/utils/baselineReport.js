const SEVERITY_ORDER = { P0: 0, P1: 1, P2: 2, INFO: 3 }

export function severityRank(s) {
  return SEVERITY_ORDER[s] ?? 99
}

export function worstSeverity(severities) {
  let worst = null
  for (const s of severities) {
    if (worst == null || severityRank(s) < severityRank(worst)) worst = s
  }
  return worst
}

// stage_status 用的 label suffix。 alert.stage_status 由 backend 帶上來,
// 可能是 'removed' (商品下架,真的消失) / 'exists' (商品還在,只是排到 300 名外)
// / 'check_failed' (stage 查詢失敗) / null (在前 300 內,不需查 stage)
function stageLabel(stage) {
  if (stage === 'removed') return '商品下架'
  if (stage === 'exists') return '排名 >300'
  if (stage === 'check_failed') return '未確認'
  return '未出現'
}
function stageKind(prefix, stage) {
  // prefix: 'a' or 'b'
  if (stage === 'removed') return `${prefix}_removed`
  if (stage === 'exists') return `${prefix}_out_of_window`
  if (stage === 'check_failed') return `${prefix}_check_failed`
  return `${prefix}_missing` // 後備(理論上不會走到)
}

function preciseCellStatus(alert) {
  // alert.a_rank / alert.b_rank may be null
  // alert_type 'side' = A-only health; alert_type 'main' = AB compare
  if (alert.alert_type === 'side') {
    if (alert.a_rank == null) return { kind: stageKind('a', alert.stage_status), label: `A ${stageLabel(alert.stage_status)}` }
    return { kind: 'a_rank_drop', label: `A#${alert.a_rank} 偏低` }
  }
  // main: A 有出現,B 異常
  if (alert.b_rank == null) {
    return { kind: stageKind('b', alert.stage_status), label: `A#${alert.a_rank} → B ${stageLabel(alert.stage_status)}` }
  }
  return { kind: 'rank_drop', label: `A#${alert.a_rank} → B#${alert.b_rank}` }
}

export function aggregateAlerts(alerts) {
  const safeAlerts = Array.isArray(alerts) ? alerts : []
  const summary = { total: safeAlerts.length, P0: 0, P1: 0, P2: 0, INFO: 0 }
  for (const a of safeAlerts) {
    if (summary[a.severity] != null) summary[a.severity] += 1
  }

  // ── precise: group by query, slot into top1/top2 by baseline_rank ──────
  const preciseByQuery = new Map()
  for (const a of safeAlerts) {
    if (a.keyword_type !== 'precise') continue
    if (!preciseByQuery.has(a.query)) {
      preciseByQuery.set(a.query, {
        query: a.query, top1: null, top2: null,
        severities: [], reasons: [],
      })
    }
    const entry = preciseByQuery.get(a.query)
    const slot = a.baseline_rank === 2 ? 'top2' : 'top1'
    // Keep the most severe alert if two come in for the same slot (for cell label)
    const prev = entry[slot]
    if (!prev || severityRank(a.severity) < severityRank(prev.severity)) {
      const cell = preciseCellStatus(a)
      entry[slot] = {
        status: cell.kind,
        label: cell.label,
        a_rank: a.a_rank,
        b_rank: a.b_rank,
        severity: a.severity,
        reason: a.reason,
      }
    }
    entry.severities.push(a.severity)
    entry.reasons.push({
      severity: a.severity,
      baseline_rank: a.baseline_rank,
      a_rank: a.a_rank,
      b_rank: a.b_rank,
      reason: a.reason,
    })
  }
  const precise = Array.from(preciseByQuery.values()).map(e => ({
    ...e,
    reasons: e.reasons.sort((x, y) => {
      const r = severityRank(x.severity) - severityRank(y.severity)
      return r !== 0 ? r : (x.baseline_rank ?? 99) - (y.baseline_rank ?? 99)
    }),
    worstSeverity: worstSeverity(e.severities),
  }))

  // ── broad: group by query, count anomalies + missing + worst severity ──
  const broadByQuery = new Map()
  for (const a of safeAlerts) {
    if (a.keyword_type !== 'broad') continue
    if (!broadByQuery.has(a.query)) {
      broadByQuery.set(a.query, {
        query: a.query,
        anomalies: 0,
        removedCount: 0,        // B 確認下架
        outOfWindowCount: 0,    // B 排名 >300 名
        checkFailedCount: 0,    // stage 查詢失敗
        severities: [],
        reasons: [],
      })
    }
    const entry = broadByQuery.get(a.query)
    entry.anomalies += 1
    if (a.b_rank == null && a.a_rank != null) {
      if (a.stage_status === 'removed') entry.removedCount += 1
      else if (a.stage_status === 'exists') entry.outOfWindowCount += 1
      else entry.checkFailedCount += 1
    }
    entry.severities.push(a.severity)
    entry.reasons.push({
      severity: a.severity,
      baseline_rank: a.baseline_rank,
      reason: a.reason,
    })
  }
  const broad = Array.from(broadByQuery.values()).map(e => ({
    ...e,
    // Sort reasons by severity then baseline_rank for stable tooltip ordering
    reasons: e.reasons.sort((x, y) => {
      const r = severityRank(x.severity) - severityRank(y.severity)
      return r !== 0 ? r : (x.baseline_rank ?? 99) - (y.baseline_rank ?? 99)
    }),
    worstSeverity: worstSeverity(e.severities),
  }))

  // Sort by worst severity ascending (P0 first), then by query
  const bySeverity = (a, b) => {
    const ra = severityRank(a.worstSeverity)
    const rb = severityRank(b.worstSeverity)
    if (ra !== rb) return ra - rb
    return a.query.localeCompare(b.query)
  }
  precise.sort(bySeverity)
  broad.sort(bySeverity)

  return { summary, precise, broad }
}
