import { useCallback, useEffect, useState } from 'react'
import { getAuditLogs, getRecentAuditLogs } from '../api/auditApi'
import { normalizeError } from '../api/client'

export function useAuditLogs({ recent = true, limit = 100 } = {}) {
  const [logs, setLogs] = useState([])
  const [filters, setFilters] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async (nextFilters = filters) => {
    setLoading(true)
    try {
      const response = recent && Object.keys(nextFilters).length === 0
        ? await getRecentAuditLogs(limit)
        : await getAuditLogs({ limit, ...nextFilters })
      setLogs(response.items || [])
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [filters, limit, recent])

  const updateFilters = useCallback((next) => {
    setFilters(next)
    refresh(next)
  }, [refresh])

  useEffect(() => {
    refresh()
  }, [refresh])

  return {
    logs,
    filters,
    loading,
    error,
    refresh,
    setFilters: updateFilters,
  }
}
