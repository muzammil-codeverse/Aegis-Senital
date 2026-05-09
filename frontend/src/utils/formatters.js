export function formatNumber(value) {
  if (value === null || value === undefined || value === '') return 'N/A'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return numeric.toLocaleString()
}

export function formatPercent(value) {
  if (value === null || value === undefined || value === '') return 'N/A'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'N/A'
  const pct = numeric <= 1 ? numeric * 100 : numeric
  return `${pct.toFixed(0)}%`
}

export function asArray(value) {
  return Array.isArray(value) ? value : []
}

export function compactList(values, fallback = 'N/A') {
  const items = asArray(values).filter(value => value !== null && value !== undefined && value !== '')
  return items.length ? items.join(', ') : fallback
}

export function metricValue(metrics, key) {
  return Object.prototype.hasOwnProperty.call(metrics || {}, key) ? metrics[key] : null
}
