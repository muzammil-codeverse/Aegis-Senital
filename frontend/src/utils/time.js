export function formatTimestamp(value) {
  if (!value) return 'N/A'
  const ms = Number(value) < 10_000_000_000 ? Number(value) * 1000 : Number(value)
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return 'N/A'
  return date.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function formatDateTime(value) {
  if (!value) return 'N/A'
  const ms = Number(value) < 10_000_000_000 ? Number(value) * 1000 : Number(value)
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return 'N/A'
  return date.toLocaleString([], { hour12: false })
}

export function ageSeconds(value) {
  if (!value) return null
  const seconds = Number(value) < 10_000_000_000 ? Number(value) : Number(value) / 1000
  if (!Number.isFinite(seconds)) return null
  return Math.max(0, Math.round(Date.now() / 1000 - seconds))
}

export function formatAge(value) {
  const age = typeof value === 'number' ? value : ageSeconds(value)
  if (age === null || !Number.isFinite(age)) return 'N/A'
  if (age < 60) return `${age}s`
  const minutes = Math.floor(age / 60)
  if (minutes < 60) return `${minutes}m ${age % 60}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}
