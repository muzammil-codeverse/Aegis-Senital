import CaseSummaryPanel from './CaseSummaryPanel'
import CaseAssignmentPanel from './CaseAssignmentPanel'
import CaseEvidencePanel from './CaseEvidencePanel'
import EvidenceExplanationPanel from './EvidenceExplanationPanel'
import NaturalLanguageQueryPanel from './NaturalLanguageQueryPanel'
import CaseNotesPanel from './CaseNotesPanel'
import CasePriorityBadge from './CasePriorityBadge'
import ReportDraftPanel from './ReportDraftPanel'
import CaseStatusBadge from './CaseStatusBadge'
import CaseTimeline from './CaseTimeline'
import LlmSafetyBadge from './LlmSafetyBadge'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatDateTime } from '../../utils/time'

export default function CaseDetailDrawer({
  caseItem,
  open,
  loading,
  error,
  timeline = [],
  evidence = [],
  notes = [],
  busy,
  llmBusy,
  llmStatus,
  summaryOutput,
  timelineSummary,
  evidenceSummary,
  queryAnswer,
  generatedReport,
  canGenerateLlm,
  canGenerateReport,
  onClose,
  onAssign,
  onAddEvidence,
  onAddNote,
  onResolve,
  onReopen,
  onDismiss,
  onArchive,
  onExport,
  onGenerateCaseSummary,
  onGenerateIncidentSummary,
  onGenerateTimelineSummary,
  onGenerateEvidenceSummary,
  onGenerateDraftReport,
  onGenerateHandoffReport,
  onAskCaseQuestion,
  onOpenGeneratedReport,
}) {
  if (!open) return null
  return (
    <aside className="detail-drawer" aria-label="Case details">
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Case Detail</p>
          <h2>{caseItem?.title || 'Loading case'}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close case detail">
          x
        </button>
      </div>
      {loading && <LoadingState label="Loading case detail" />}
      {error && <ErrorState message={error} />}
      {caseItem && (
        <>
          <div className="drawer-summary">
            <CaseStatusBadge status={caseItem.status} />
            <CasePriorityBadge priority={caseItem.priority} />
            <span className="state-chip">{caseItem.requires_review ? 'requires review' : 'reviewed'}</span>
            <span className="state-chip">{caseItem.review_status || 'pending'}</span>
          </div>
          <p className="drawer-description">{caseItem.description || 'Possible incident requires operator review.'}</p>
          <LlmSafetyBadge status={llmStatus} />
          <div className="drawer-grid">
            <span>Case ID</span><strong>{caseItem.case_id}</strong>
            <span>Severity</span><strong>{caseItem.severity}</strong>
            <span>Cameras</span><strong>{(caseItem.camera_ids || []).join(', ') || 'N/A'}</strong>
            <span>Source Events</span><strong>{(caseItem.source_event_ids || []).join(', ') || 'N/A'}</strong>
            <span>Tracks</span><strong>{(caseItem.track_ids || []).join(', ') || 'N/A'}</strong>
            <span>Assigned To</span><strong>{caseItem.assigned_to || 'Unassigned'}</strong>
            <span>Created</span><strong>{formatDateTime(caseItem.created_at)}</strong>
            <span>Updated</span><strong>{formatDateTime(caseItem.updated_at)}</strong>
          </div>
          <div className="button-row">
            <button type="button" className="text-button" disabled={busy} onClick={() => onResolve?.('Resolved from drawer')}>Resolve</button>
            <button type="button" className="text-button" disabled={busy} onClick={() => onReopen?.('Reopened from drawer')}>Reopen</button>
            <button type="button" className="text-button danger" disabled={busy} onClick={() => onDismiss?.('Dismissed from drawer')}>Dismiss</button>
            <button type="button" className="text-button" disabled={busy} onClick={() => onArchive?.('Archived from drawer')}>Archive</button>
            <button type="button" className="text-button" disabled={busy} onClick={() => onExport?.('markdown')}>Export</button>
          </div>
          <CaseSummaryPanel
            summaryOutput={summaryOutput}
            timelineSummary={timelineSummary}
            busy={llmBusy}
            canGenerate={canGenerateLlm}
            onGenerateCaseSummary={onGenerateCaseSummary}
            onGenerateIncidentSummary={onGenerateIncidentSummary}
            onGenerateTimelineSummary={onGenerateTimelineSummary}
          />
          <EvidenceExplanationPanel
            output={evidenceSummary}
            busy={llmBusy}
            canGenerate={canGenerateLlm}
            onGenerate={onGenerateEvidenceSummary}
          />
          <ReportDraftPanel
            output={generatedReport}
            busy={llmBusy}
            canGenerate={canGenerateLlm}
            canReport={canGenerateReport}
            onGenerateDraft={onGenerateDraftReport}
            onGenerateHandoff={onGenerateHandoffReport}
            onOpenReport={onOpenGeneratedReport}
          />
          <NaturalLanguageQueryPanel
            output={queryAnswer}
            busy={llmBusy}
            canGenerate={canGenerateLlm}
            onAsk={onAskCaseQuestion}
          />
          <section className="drawer-section">
            <h3>Timeline</h3>
            <CaseTimeline items={timeline} />
          </section>
          <CaseEvidencePanel items={evidence} onAddEvidence={onAddEvidence} busy={busy} />
          <CaseNotesPanel items={notes} onAddNote={onAddNote} busy={busy} />
          <CaseAssignmentPanel caseItem={caseItem} onAssign={onAssign} busy={busy} />
        </>
      )}
    </aside>
  )
}
