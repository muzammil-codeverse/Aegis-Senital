import { useCallback, useEffect, useMemo, useState } from 'react'
import { listCases } from '../../api/caseApi'
import { acceptCorrelation, listCorrelations, markCorrelationInconclusive, rejectCorrelation } from '../../api/droneFusionApi'
import { acceptIdentityCandidate, getIdentityCandidates, rejectIdentityCandidate } from '../../api/identityApi'
import { investigationApi } from '../../api/investigationApi'
import { fetchGovernanceLimitations, fetchPromotionPolicy } from '../../api/modelGovernanceApi'
import { useAuth } from '../../hooks/useAuth'

function pendingOnly(items, field = 'review_status') {
  return (items || []).filter(item => String(item?.[field] || 'pending').toLowerCase() === 'pending')
}

export default function ReviewQueuePanel({ limit = 12 }) {
  const auth = useAuth()
  const { authenticated, loading: authLoading, ready, hasPermission } = auth
  const authReady = Boolean(ready ?? !authLoading)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busyKey, setBusyKey] = useState(null)

  const refresh = useCallback(async () => {
    if (!authReady) {
      setLoading(true)
      setError(null)
      return
    }
    if (!authenticated) {
      setItems([])
      setLoading(false)
      setError('Sign in required')
      return
    }
    setLoading(true)
    setError(null)
    const next = []
    try {
      const tasks = []
      if (hasPermission('identity:read')) tasks.push(getIdentityCandidates({ limit: 8 }).then(result => ['identity', pendingOnly(result.items)]))
      if (hasPermission('drone_fusion:read')) tasks.push(listCorrelations({ limit: 8 }).then(result => ['fusion', pendingOnly(result.items)]))
      if (hasPermission('investigation:read')) tasks.push(investigationApi.listHypotheses({ limit: 8 }).then(result => ['investigation', pendingOnly(result.items)]))
      if (hasPermission('case:read')) tasks.push(listCases({ limit: 8 }).then(result => ['cases', (result.items || []).filter(item => item.requires_review)]))
      if (hasPermission('model:read')) {
        tasks.push(Promise.all([fetchGovernanceLimitations(), fetchPromotionPolicy()]).then(([limitations, policy]) => ['governance', { limitations, policy }]))
      }
      const settled = await Promise.allSettled(tasks)

      for (const result of settled) {
        if (result.status !== 'fulfilled') continue
        const [kind, payload] = result.value
        if (kind === 'identity') {
          payload.forEach(item => next.push({
            key: `identity:${item.identity_candidate_id}`,
            kind: 'identity_candidate',
            title: item.display_name || item.identity_candidate_id,
            description: 'Identity candidate requires operator review.',
            route: 'identities',
            actions: ['accept', 'reject'],
            raw: item,
          }))
        }
        if (kind === 'fusion') {
          payload.forEach(item => next.push({
            key: `fusion:${item.correlation_id}`,
            kind: 'fusion_correlation',
            title: item.correlation_id,
            description: item.review_status || 'Candidate cross-source observation pending review.',
            route: 'drone-fusion',
            caseId: item.case_id,
            actions: ['accept', 'reject', 'inconclusive'],
            raw: item,
          }))
        }
        if (kind === 'investigation') {
          payload.forEach(item => next.push({
            key: `investigation:${item.hypothesis_id}`,
            kind: 'investigation_hypothesis',
            title: item.title || item.hypothesis_id,
            description: item.summary || 'Evidence-backed hypothesis pending review.',
            route: 'investigation',
            caseId: item.case_id,
            actions: ['accept', 'reject', 'inconclusive'],
            raw: item,
          }))
        }
        if (kind === 'cases') {
          payload.forEach(item => next.push({
            key: `case:${item.case_id}`,
            kind: 'case_review',
            title: item.title || item.case_id,
            description: item.description || 'Case requires operator review.',
            route: 'cases',
            caseId: item.case_id,
            actions: [],
            raw: item,
          }))
        }
        if (kind === 'governance') {
          const limitations = payload.limitations?.limitations || []
          const blocking = limitations.filter(item => item?.severity === 'high' || item?.status === 'blocked')
          blocking.forEach((item, index) => next.push({
            key: `governance:${item.model_id || index}`,
            kind: 'model_governance_blocker',
            title: item.name || item.model_id || 'Model governance blocker',
            description: item.detail || item.reason || 'Model limitation requires operator review.',
            route: 'model-governance',
            actions: [],
            raw: item,
          }))
          if (payload.policy?.promotion_policy?.enable_file_writes === false) {
            next.push({
              key: 'governance:file-writes',
              kind: 'model_governance_blocker',
              title: 'Promotion writes disabled',
              description: 'Promotion remains disabled while file writes are locked.',
              route: 'model-governance',
              actions: [],
              raw: payload.policy,
            })
          }
        }
      }

      setItems(next.slice(0, limit))
    } catch (err) {
      setError(err?.message || 'Failed to load review queue')
    } finally {
      setLoading(false)
    }
  }, [authReady, authenticated, hasPermission, limit])

  useEffect(() => {
    const initialTimer = window.setTimeout(refresh, 0)
    if (!authReady || !authenticated) {
      return () => window.clearTimeout(initialTimer)
    }
    const timer = window.setInterval(refresh, 30000)
    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [authenticated, authReady, refresh])

  async function handleReview(item, action) {
    setBusyKey(`${item.key}:${action}`)
    try {
      if (item.kind === 'identity_candidate') {
        if (action === 'accept') await acceptIdentityCandidate(item.raw.identity_candidate_id, {})
        if (action === 'reject') await rejectIdentityCandidate(item.raw.identity_candidate_id, {})
      }
      if (item.kind === 'fusion_correlation') {
        if (action === 'accept') await acceptCorrelation(item.raw.correlation_id, null)
        if (action === 'reject') await rejectCorrelation(item.raw.correlation_id, null)
        if (action === 'inconclusive') await markCorrelationInconclusive(item.raw.correlation_id, null)
      }
      if (item.kind === 'investigation_hypothesis') {
        if (action === 'accept') await investigationApi.acceptHypothesis(item.raw.hypothesis_id)
        if (action === 'reject') await investigationApi.rejectHypothesis(item.raw.hypothesis_id)
        if (action === 'inconclusive') await investigationApi.markInconclusive(item.raw.hypothesis_id)
      }
      await refresh()
    } finally {
      setBusyKey(null)
    }
  }

  const emptyText = useMemo(() => {
    if (loading) return 'Loading review queue...'
    if (error) return error
    return 'No pending review items are currently exposed to this operator.'
  }, [error, loading])

  return (
    <section className="panel command-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Operator Workflow</p>
          <h2>Unified Review Queue</h2>
        </div>
      </div>
      {items.length === 0 ? <p className="muted">{emptyText}</p> : null}
      <div className="review-queue-list">
        {items.map(item => (
          <article key={item.key} className="review-queue-card">
            <div className="review-queue-card__header">
              <span className="state-chip">{item.kind.replaceAll('_', ' ')}</span>
              <strong>{item.title}</strong>
            </div>
            <p>{item.description}</p>
            <div className="button-row">
              <button type="button" className="text-button" onClick={() => { window.location.hash = item.route }}>
                Open detail
              </button>
              {item.caseId ? (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    window.sessionStorage.setItem('aegis.map.case_id', item.caseId)
                    window.location.hash = 'map-operations'
                  }}
                >
                  View on map
                </button>
              ) : null}
              {item.actions.includes('accept') ? (
                <button type="button" className="text-button" disabled={busyKey === `${item.key}:accept`} onClick={() => handleReview(item, 'accept')}>
                  Accept
                </button>
              ) : null}
              {item.actions.includes('reject') ? (
                <button type="button" className="text-button danger" disabled={busyKey === `${item.key}:reject`} onClick={() => handleReview(item, 'reject')}>
                  Reject
                </button>
              ) : null}
              {item.actions.includes('inconclusive') ? (
                <button type="button" className="text-button" disabled={busyKey === `${item.key}:inconclusive`} onClick={() => handleReview(item, 'inconclusive')}>
                  Inconclusive
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
