import { useCallback, useEffect, useState } from 'react'
import { getOperationalView } from '../../api/scenarioApi'
import { normalizeError } from '../../api/client'
import CameraHandoffTimeline from './CameraHandoffTimeline'
import DroneRoutePanel from './DroneRoutePanel'
import FusedTrackSummary from './FusedTrackSummary'
import SuspectPathMap from './SuspectPathMap'
import LoadingState from '../common/LoadingState'
import ErrorState from '../common/ErrorState'

const POLL_MS = 4000

const SEVERITY_COLOR = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  medium: '#faad14',
  low: '#52c41a',
  info: '#6b7280',
}

const STATE_COLOR = {
  running: '#52c41a',
  paused: '#faad14',
  completed: '#1890ff',
  cancelled: '#ff4d4f',
  idle: '#6b7280',
}

function SectionHeader({ title, badge = null }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
      <span style={{ fontSize: '0.65rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</span>
      {badge != null && (
        <span style={{ fontSize: '0.58rem', color: '#4b5563', background: 'rgba(255,255,255,0.05)', padding: '1px 5px', borderRadius: 8 }}>
          {badge}
        </span>
      )}
    </div>
  )
}

export default function OperationalTrackingPanel({ activeRun = null }) {
  const [view, setView] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('path')

  const runId = activeRun?.run_id || null
  const isActive = activeRun && (activeRun.state === 'running' || activeRun.state === 'paused' || activeRun.state === 'completed')

  const refresh = useCallback(async (isInitial = false) => {
    if (!runId || !isActive) {
      setView(null)
      return
    }
    if (isInitial) setLoading(true)
    try {
      const data = await getOperationalView(runId)
      setView(data)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      if (isInitial) setLoading(false)
    }
  }, [runId, isActive])

  useEffect(() => {
    const initial = window.setTimeout(() => refresh(true), 0)
    const timer = window.setInterval(() => refresh(false), POLL_MS)
    return () => {
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [refresh])

  // Zero state
  if (!activeRun || !isActive) {
    return (
      <section className="panel" style={{ marginBottom: 8 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Operational Tracking</p>
            <h2>Fused Path View</h2>
          </div>
        </div>
        <div style={{ textAlign: 'center', color: '#4b5563', fontSize: '0.72rem', padding: '16px 0' }}>
          No active scenario run.<br />Start a scenario to see suspect path, camera handoffs, and drone route.
        </div>
      </section>
    )
  }

  const suspectPath = view?.suspect_path || []
  const handoffs = view?.camera_handoffs || []
  const droneRoute = view?.drone_route || null
  const fusedTrack = view?.fused_track || null
  const currentEvent = view?.current_event || null
  const stateColor = STATE_COLOR[view?.state || activeRun.state] || '#6b7280'

  return (
    <section className="panel" style={{ marginBottom: 8 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Operational Tracking</p>
          <h2>Fused Path View</h2>
        </div>
        <span style={{ fontSize: '0.65rem', color: stateColor, fontWeight: 600 }}>
          {(view?.state || activeRun.state || 'loading').toUpperCase()}
        </span>
      </div>

      {loading && !view && <LoadingState label="Loading tracking data" />}
      {error && <ErrorState message={error} />}

      {/* Current event banner */}
      {currentEvent && (
        <div style={{
          padding: '5px 8px', borderRadius: 4, marginBottom: 8,
          background: `rgba(${currentEvent.observation?.severity === 'critical' ? '255,77,79' : '24,144,255'},0.08)`,
          border: `1px solid rgba(${currentEvent.observation?.severity === 'critical' ? '255,77,79' : '24,144,255'},0.2)`,
        }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '0.65rem', fontWeight: 700,
              color: SEVERITY_COLOR[currentEvent.observation?.severity] || '#9ca3af',
            }}>
              {(currentEvent.event_type || '').replace(/_/g, ' ').toUpperCase()}
            </span>
            <span style={{ fontSize: '0.6rem', color: '#6b7280' }}>T+{currentEvent.t_offset_seconds}s</span>
            {currentEvent.observation?.camera_id && (
              <span style={{ fontSize: '0.6rem', color: '#52c41a' }}>{currentEvent.observation.camera_id}</span>
            )}
            {currentEvent.observation?.drone_id && (
              <span style={{ fontSize: '0.6rem', color: '#1890ff' }}>{currentEvent.observation.drone_id}</span>
            )}
          </div>
          <div style={{ fontSize: '0.62rem', color: '#6b7280', marginTop: 2 }}>
            {currentEvent.observation?.description || ''}
          </div>
        </div>
      )}

      {/* Drone dispatch badge */}
      {(view?.drone_dispatched || activeRun.drone_dispatched) && (
        <div style={{
          display: 'flex', gap: 6, alignItems: 'center',
          padding: '3px 8px', borderRadius: 4, marginBottom: 6,
          background: 'rgba(24,144,255,0.08)', border: '1px solid rgba(24,144,255,0.2)',
          fontSize: '0.65rem',
        }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#1890ff' }} />
          <strong style={{ color: '#1890ff' }}>{view?.dispatched_drone_id || activeRun.dispatched_drone_id}</strong>
          <span style={{ color: '#6b7280' }}>dispatched and tracking SUSPECT-001</span>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 8, borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        {[
          { id: 'path', label: 'Suspect Path' },
          { id: 'handoff', label: `Handoffs (${handoffs.length})` },
          { id: 'drone', label: 'Drone Route' },
          { id: 'fused', label: 'Fused Track' },
        ].map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '4px 10px', fontSize: '0.65rem', border: 'none', cursor: 'pointer',
              borderBottom: activeTab === tab.id ? '2px solid #1890ff' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === tab.id ? '#1890ff' : '#6b7280',
              fontWeight: activeTab === tab.id ? 600 : 400,
              marginBottom: -1,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'path' && (
          <div>
            <SectionHeader
              title="Suspect Movement Path"
              badge={`${suspectPath.length} waypoints`}
            />
            <SuspectPathMap
              waypoints={suspectPath}
              droneWaypoints={droneRoute?.waypoints || []}
              runId={runId}
            />
          </div>
        )}

        {activeTab === 'handoff' && (
          <div>
            <SectionHeader
              title="Camera Handoff Sequence"
              badge={`${handoffs.length} handoffs`}
            />
            <CameraHandoffTimeline handoffs={handoffs} />
          </div>
        )}

        {activeTab === 'drone' && (
          <div>
            <SectionHeader
              title="DRONE-ALPHA Route"
              badge={droneRoute ? droneRoute.status : 'standby'}
            />
            <DroneRoutePanel
              droneRoute={droneRoute}
              droneDispatched={view?.drone_dispatched || activeRun.drone_dispatched}
              dispatchedDroneId={view?.dispatched_drone_id || activeRun.dispatched_drone_id}
            />
          </div>
        )}

        {activeTab === 'fused' && (
          <div>
            <SectionHeader title="Fused Track" badge={fusedTrack ? fusedTrack.status : 'building'} />
            <FusedTrackSummary fusedTrack={fusedTrack} />
          </div>
        )}
      </div>

      {/* Involved cameras/drones footer */}
      {view && (view.involved_cameras?.length > 0 || view.involved_drones?.length > 0) && (
        <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '0.6rem', color: '#4b5563' }}>
          {view.involved_cameras?.length > 0 && (
            <span>CCTV: {view.involved_cameras.slice(0, 6).join(' · ')}{view.involved_cameras.length > 6 ? '…' : ''}</span>
          )}
          {view.involved_cameras?.length > 0 && view.involved_drones?.length > 0 && <span> &nbsp;|&nbsp; </span>}
          {view.involved_drones?.length > 0 && (
            <span style={{ color: '#1890ff' }}>Drones: {view.involved_drones.join(' · ')}</span>
          )}
        </div>
      )}
    </section>
  )
}
