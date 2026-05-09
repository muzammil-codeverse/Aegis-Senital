export const severityRank = {
  critical: 0,
  high: 1,
  medium: 2,
  elevated: 2,
  low: 3,
  info: 4,
  normal: 5,
}

export function normalizeSeverity(value) {
  return String(value || 'info').toLowerCase()
}

export function severityClass(value) {
  return `severity-${normalizeSeverity(value)}`
}

export function compareSeverity(a, b) {
  return (severityRank[normalizeSeverity(a)] ?? 9) - (severityRank[normalizeSeverity(b)] ?? 9)
}
