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

function preciseCellStatus(alert) {
  // alert.a_rank / alert.b_rank may be null
  // alert_type 'side' = A-only health; alert_type 'main' = AB compare
  if (alert.alert_type === 'side') {
    if (alert.a_rank == null) return { kind: 'a_missing', label: 'A 未出現' }
    return { kind: 'a_dropped', label: `A#${alert.a_rank} 偏低` }
  }
  // main: A 有出現,B 異常
  if (alert.b_rank == null) return { kind: 'b_missing', label: `A#${alert.a_rank} → B 消失` }
  return { kind: 'dropped', label: `A#${alert.a_rank} → B#${alert.b_rank}` }
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
        missingCount: 0,
        severities: [],
        reasons: [],
      })
    }
    const entry = broadByQuery.get(a.query)
    entry.anomalies += 1
    if (a.b_rank == null && a.a_rank != null) entry.missingCount += 1
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
