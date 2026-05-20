import { useEffect } from 'react'
import CreateCaseFromVideoButton from '../components/uploaded-video/CreateCaseFromVideoButton'
import UploadedVideoDropzone from '../components/uploaded-video/UploadedVideoDropzone'
import UploadedVideoEventsTable from '../components/uploaded-video/UploadedVideoEventsTable'
import UploadedVideoProcessingPanel from '../components/uploaded-video/UploadedVideoProcessingPanel'
import UploadedVideoReportPanel from '../components/uploaded-video/UploadedVideoReportPanel'
import UploadedVideoTimeline from '../components/uploaded-video/UploadedVideoTimeline'
import { useUploadedVideo } from '../hooks/useUploadedVideo'
import { useUploadedVideoProgress } from '../hooks/useUploadedVideoProgress'
import { useAuth } from '../hooks/useAuth'

export default function UploadedVideoAnalysisPage() {
  const auth = useAuth()
  const uploadedVideo = useUploadedVideo()
  const progress = useUploadedVideoProgress(uploadedVideo.currentSession?.session_id, {
    enabled: Boolean(uploadedVideo.currentSession?.session_id),
  })
  const currentSessionId = uploadedVideo.currentSession?.session_id
  const refreshSessionDetail = uploadedVideo.refreshSessionDetail
  const effectiveStatus = progress.status || uploadedVideo.currentStatus || {
    status: uploadedVideo.currentSession?.status,
    progress: uploadedVideo.currentSession?.progress,
  }

  useEffect(() => {
    if (!currentSessionId) return
    if (!progress.status) return
    refreshSessionDetail(currentSessionId)
  }, [currentSessionId, progress.status, refreshSessionDetail])

  return (
    <div className="page-grid uploaded-video-page">
      <UploadedVideoDropzone onUpload={file => uploadedVideo.upload(file)} busy={uploadedVideo.actionLoading} />
      <UploadedVideoProcessingPanel
        session={uploadedVideo.currentSession}
        status={effectiveStatus}
        connectionStatus={progress.connectionStatus}
        error={progress.error}
        stalled={progress.stalled}
        busy={uploadedVideo.actionLoading}
        onStart={uploadedVideo.startProcessing}
        onCancel={uploadedVideo.cancelProcessing}
      />
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Recent Sessions</p>
            <h2>Session Library</h2>
          </div>
          <div className="button-row">
            {auth.hasPermission('gis:read') ? (
              <button type="button" className="text-button" onClick={() => { window.location.hash = 'map-operations' }}>
                Show event location
              </button>
            ) : null}
            <span className="count-pill">{uploadedVideo.sessions.length}</span>
          </div>
        </div>
        {uploadedVideo.error ? <p className="error-text">{uploadedVideo.error}</p> : null}
        {uploadedVideo.loading ? (
          <p className="muted">Loading uploaded-video sessions...</p>
        ) : uploadedVideo.sessions.length === 0 && !uploadedVideo.error ? (
          <p className="muted">No uploaded-video sessions yet.</p>
        ) : (
          <div className="uploaded-video-session-list">
            {uploadedVideo.sessions.map(session => (
              <button
                key={session.session_id}
                type="button"
                className={`timeline-card session-card ${uploadedVideo.currentSession?.session_id === session.session_id ? 'active' : ''}`}
                onClick={() => uploadedVideo.selectSession(session.session_id)}
              >
                <div className="button-row">
                  <strong>{session.original_filename}</strong>
                  <span className={`count-pill ${session.status === 'completed' ? 'status-open' : ''}`}>{session.status}</span>
                </div>
                <p>{session.session_id}</p>
                <div className="button-row">
                  <span>{Number(session.duration_seconds || 0).toFixed(1)}s</span>
                  <span>{session.frame_count || 0} frames</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>
      <UploadedVideoTimeline
        items={uploadedVideo.timeline}
        sessionId={uploadedVideo.currentSession?.session_id}
        status={effectiveStatus?.status}
      />
      <UploadedVideoEventsTable
        events={uploadedVideo.events}
        sessionId={uploadedVideo.currentSession?.session_id}
        status={effectiveStatus?.status}
      />
      <UploadedVideoReportPanel report={uploadedVideo.report} />
      <CreateCaseFromVideoButton
        session={uploadedVideo.currentSession}
        disabled={uploadedVideo.actionLoading || !uploadedVideo.currentSession || !['completed'].includes(effectiveStatus?.status || uploadedVideo.currentSession?.status)}
        onCreate={uploadedVideo.createCase}
      />
    </div>
  )
}
