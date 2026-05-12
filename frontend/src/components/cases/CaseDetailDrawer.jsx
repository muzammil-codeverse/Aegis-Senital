import { useMemo, useState } from 'react'
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
import CaseSummaryPanel from './CaseSummaryPanel'
import CaseEnrichmentPanel from '../osint/CaseEnrichmentPanel'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { useAuth } from '../../hooks/useAuth'
import { formatDateTime } from '../../utils/time'

const TABS = [
  'overview',
  'timeline',
  'evidence',
  'chain of custody',
  'investigation',
  'drone/fusion',
  'osint',
  'llm reports',
  'export',
]

function indicatorLabel(caseItem, evidence, generatedReport, showEnrichment) {
  const indicators = []
  if (evidence.some(item => String(item.integrity_status || '').toLowerCase() === 'verified')) indicators.push('hash verified')
  if (evidence.some(item => String(item.integrity_status || '').toLowerCase() === 'missing_file')) indicators.push('missing file')
  if (caseItem?.requires_review) indicators.push('operator review required')
  if (generatedReport) indicators.push('AI-assisted draft')
  if (showEnrichment) indicators.push('manual OSINT only')
  if ((caseItem?.tags || []).some(tag => String(tag).toLowerCase().includes('fusion')) || caseItem?.metadata?.fusion_candidate) indicators.push('fusion candidate')
  if (caseItem?.metadata?.simulated_drone_source || (caseItem?.tags || []).some(tag => String(tag).toLowerCase().includes('drone'))) indicators.push('simulated drone source')
  return indicators
}

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
  showEnrichment = false,
  enrichmentState = null,
  canReadEnrichment = false,
  canWriteEnrichment = false,
  canSummarizeEnrichment = false,
  onClose,
  onAssign,
  onAddEvidence,
  onUploadEvidenceFile,
  onVerifyEvidenceFile,
  onDownloadEvidenceFile,
  onExportEvidenceManifest,
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
  const auth = useAuth()
  const [activeTab, setActiveTab] = useState('overview')

  const indicators = useMemo(
    () => indicatorLabel(caseItem, evidence, generatedReport, showEnrichment),
    [caseItem, evidence, generatedReport, showEnrichment],
  )

  if (!open) return null

  return (
    <aside className="detail-drawer" aria-label="Case details">
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Case Command Drawer</p>
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
            <span className="state-chip">{caseItem.review_status || 'pending'}</span>
            {caseItem.metadata?.legal_hold ? <span className="state-chip">legal hold</span> : null}
          </div>
          <div className="button-row">
            {indicators.map(item => <span key={item} className="state-chip">{item}</span>)}
          </div>
          <p className="drawer-description">{caseItem.description || 'Possible incident requires operator review.'}</p>
          <LlmSafetyBadge status={llmStatus} />

          <div className="button-row" style={{ marginBottom: 12, flexWrap: 'wrap' }}>
            {TABS.map(tab => (
              <button
                key={tab}
                type="button"
                className={`command-action-button ${activeTab === tab ? '' : 'subtle'}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeTab === 'overview' ? (
            <>
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
                {auth.hasPermission('gis:read') && caseItem?.case_id ? (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      window.sessionStorage.setItem('aegis.map.case_id', caseItem.case_id)
                      window.location.hash = 'map-operations'
                    }}
                  >
                    Show case location
                  </button>
                ) : null}
                <button type="button" className="text-button" disabled={busy} onClick={() => onResolve?.('Resolved from drawer')}>Resolve</button>
                <button type="button" className="text-button" disabled={busy} onClick={() => onReopen?.('Reopened from drawer')}>Reopen</button>
                <button type="button" className="text-button danger" disabled={busy} onClick={() => onDismiss?.('Dismissed from drawer')}>Dismiss</button>
                <button type="button" className="text-button" disabled={busy} onClick={() => onArchive?.('Archived from drawer')}>Archive</button>
              </div>
              <CaseAssignmentPanel caseItem={caseItem} onAssign={onAssign} busy={busy} />
            </>
          ) : null}

          {activeTab === 'timeline' ? (
            <section className="drawer-section">
              <h3>Timeline</h3>
              <CaseTimeline items={timeline} />
            </section>
          ) : null}

          {activeTab === 'evidence' ? (
            <CaseEvidencePanel
              items={evidence}
              onAddEvidence={onAddEvidence}
              onUploadEvidenceFile={onUploadEvidenceFile}
              onVerifyEvidence={onVerifyEvidenceFile}
              onDownloadEvidence={onDownloadEvidenceFile}
              onExportManifest={onExportEvidenceManifest}
              busy={busy}
              caseId={caseItem.case_id}
              defaultCameraId={caseItem.camera_ids?.[0] || evidence?.[0]?.camera_id || null}
              legalHoldEnabled={Boolean(caseItem.metadata?.legal_hold)}
            />
          ) : null}

          {activeTab === 'chain of custody' ? (
            <section className="drawer-section">
              <div className="panel-subheader">
                <h3>Chain of Custody</h3>
                <span>{evidence.length} evidence item(s)</span>
              </div>
              <div className="drawer-grid">
                <span>Verified items</span><strong>{evidence.filter(item => String(item.integrity_status || '').toLowerCase() === 'verified').length}</strong>
                <span>Missing files</span><strong>{evidence.filter(item => String(item.integrity_status || '').toLowerCase() === 'missing_file').length}</strong>
                <span>Legal hold</span><strong>{caseItem.metadata?.legal_hold ? 'enabled' : 'disabled'}</strong>
                <span>Manifest export</span><strong>available</strong>
              </div>
              <div className="button-row">
                <button type="button" className="text-button" disabled={busy} onClick={() => onExportEvidenceManifest?.()}>
                  Export chain-of-custody manifest
                </button>
              </div>
            </section>
          ) : null}

          {activeTab === 'investigation' ? (
            <>
              <section className="drawer-section">
                <h3>Investigation</h3>
                <p className="drawer-description">Case notes, timeline review, and operator assignment remain operator-reviewed workflows.</p>
              </section>
              <CaseNotesPanel items={notes} onAddNote={onAddNote} busy={busy} />
            </>
          ) : null}

          {activeTab === 'drone/fusion' ? (
            <section className="drawer-section">
              <div className="panel-subheader">
                <h3>Drone / Fusion</h3>
                <span>review workflow</span>
              </div>
              <div className="drawer-grid">
                <span>Simulated drone source</span><strong>{caseItem?.metadata?.simulated_drone_source ? 'yes' : 'review case metadata'}</strong>
                <span>Fusion candidate</span><strong>{caseItem?.metadata?.fusion_candidate ? 'yes' : 'review tags'}</strong>
                <span>Track count</span><strong>{(caseItem.track_ids || []).length}</strong>
                <span>Source event count</span><strong>{(caseItem.source_event_ids || []).length}</strong>
              </div>
              <div className="button-row">
                <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-operations' }}>
                  Open drone operations
                </button>
                <button type="button" className="text-button" onClick={() => { window.location.hash = 'drone-fusion' }}>
                  Open drone fusion
                </button>
              </div>
            </section>
          ) : null}

          {activeTab === 'osint' ? (
            showEnrichment ? (
              <CaseEnrichmentPanel
                enrichmentState={enrichmentState}
                canRead={canReadEnrichment}
                canWrite={canWriteEnrichment}
                canSummarize={canSummarizeEnrichment}
              />
            ) : (
              <section className="drawer-section">
                <h3>OSINT</h3>
                <p className="drawer-description">OSINT enrichment is not available for this case or role.</p>
              </section>
            )
          ) : null}

          {activeTab === 'llm reports' ? (
            <>
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
                enrichmentCount={(enrichmentState?.sources || []).length + (enrichmentState?.summaries || []).length}
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
            </>
          ) : null}

          {activeTab === 'export' ? (
            <section className="drawer-section">
              <div className="panel-subheader">
                <h3>Export</h3>
                <span>operator action</span>
              </div>
              <p className="drawer-description">Exports remain source-grounded and operator-reviewed.</p>
              <div className="button-row">
                <button type="button" className="text-button" disabled={busy} onClick={() => onExport?.('markdown')}>Export markdown</button>
                <button type="button" className="text-button" disabled={busy} onClick={() => onExport?.('json')}>Export json</button>
                <button type="button" className="text-button" disabled={busy || !generatedReport} onClick={() => onOpenGeneratedReport?.()}>Open generated report</button>
              </div>
            </section>
          ) : null}
        </>
      )}
    </aside>
  )
}
