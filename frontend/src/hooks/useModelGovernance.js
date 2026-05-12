import { useCallback, useEffect, useState } from 'react'
import {
  fetchDrift,
  fetchGovernanceActive,
  fetchGovernanceLimitations,
  fetchGovernanceRegistry,
  fetchPromotionPolicy,
  postGovernanceValidate,
} from '../api/modelGovernanceApi.js'

export function useModelGovernance(pollMs = 60000) {
  const [registry, setRegistry] = useState([])
  const [active, setActive] = useState([])
  const [limitations, setLimitations] = useState([])
  const [policy, setPolicy] = useState({})
  const [validation, setValidation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setError(null)
      const [reg, act, lim, pol] = await Promise.all([
        fetchGovernanceRegistry(),
        fetchGovernanceActive(),
        fetchGovernanceLimitations(),
        fetchPromotionPolicy(),
      ])
      setRegistry(reg.entries || [])
      setActive(act.models || [])
      setLimitations(lim.limitations || [])
      setPolicy(pol.promotion_policy || {})
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const runValidate = useCallback(async () => {
    const data = await postGovernanceValidate({})
    setValidation(data)
    return data
  }, [])

  useEffect(() => {
    refresh()
    const t = window.setInterval(refresh, pollMs)
    return () => clearInterval(t)
  }, [refresh, pollMs])

  const loadDrift = useCallback(async (modelId) => {
    return fetchDrift(modelId)
  }, [])

  return {
    registry,
    active,
    limitations,
    policy,
    validation,
    loading,
    error,
    refresh,
    runValidate,
    loadDrift,
  }
}
