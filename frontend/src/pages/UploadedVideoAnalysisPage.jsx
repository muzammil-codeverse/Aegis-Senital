import { useEffect } from 'react'
import CreateCaseFromVideoButton from '../components/uploaded-video/CreateCaseFromVideoButton'
import UploadedVideoDropzone from '../components/uploaded-video/UploadedVideoDropzone'
import UploadedVideoEventsTable from '../components/uploaded-video/UploadedVideoEventsTable'
import UploadedVideoProcessingPanel from '../components/uploaded-video/UploadedVideoProcessingPanel'
import UploadedVideoReportPanel from '../components/uploaded-video/UploadedVideoReportPanel'
import UploadedVideoTimeline from '../components/uploaded-video/UploadedVideoTimeline'
import { useUploadedVideo } from '../hooks/useUploadedVideo'
import { useUploadedVideoProgress } from '../hooks/useUploadedVideoProgress'

export default function UploadedVideoAnalysisPage() {
  const uploadedVideo = useUploadedVideo()
  const progress = useUploadedVideoProgress(uploadedVideo.currentSession?.session_id, {
    enabled: Boolean(uploadedVideo.currentSession?.session_id),
  })

  useEffect(() => {
    const sessionId = uploadedVideo.currentSession?.session_id
    if (!sessionId) return
    if (!progress.status) return
    uploadedVideo.refreshSessionDetail(sessionId)
  }, [progress.status?.status, uploadedVideo.currentSession?.session_id, uploadedVideo.refreshSessionDetail])

  return (
    <div className="page-grid uploaded-video-page">
      <UploadedVideoDropzone onUpload={file => uploadedVideo.upload(file)} busy={uploadedVideo.actionLoading} />
      <UploadedVideoProcessingPanel
        session={uploadedVideo.currentSession}
        status={progress.status}
        connectionStatus={progress.connectionStatus}
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
          <span className="count-pill">{uploadedVideo.sessions.length}</span>
        </div>
        {uploadedVideo.error ? <p className="error-text">{uploadedVideo.error}</p> : null}
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
      </section>
      <UploadedVideoTimeline items={uploadedVideo.timeline} sessionId={uploadedVideo.currentSession?.session_id} />
      <UploadedVideoEventsTable
        events={uploadedVideo.events}
        sessionId={uploadedVideo.currentSession?.session_id}
      />
      <UploadedVideoReportPanel report={uploadedVideo.report} />
      <CreateCaseFromVideoButton
        session={uploadedVideo.currentSession}
        disabled={uploadedVideo.actionLoading || !uploadedVideo.currentSession || !['completed'].includes(progress.status?.status || uploadedVideo.currentSession?.status)}
        onCreate={uploadedVideo.createCase}
      />
    </div>
  )
}
