import { useEffect, useMemo, useState } from 'react'
import CaseDetailDrawer from '../components/cases/CaseDetailDrawer'
import GeneratedReportDrawer from '../components/cases/GeneratedReportDrawer'
import LlmSafetyBadge from '../components/cases/LlmSafetyBadge'
import CaseList from '../components/cases/CaseList'
import { useAuth } from '../hooks/useAuth'
import { useCaseEnrichment } from '../hooks/useCaseEnrichment'

export default function CasesPage({ caseState }) {
  const auth = useAuth()
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false)
  const [createForm, setCreateForm] = useState({
    title: '',
    description: '',
    priority: 'medium',
    severity: 'medium',
    camera_ids: '',
    tags: '',
  })

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const eventId = params.get('event_id')
    if (eventId) {
      caseState.createCaseFromEvent(eventId).then(created => {
        if (created?.case_id) caseState.selectCase(created.case_id)
      }).catch(() => {})
    }
  }, [caseState])

  const filteredCases = useMemo(() => caseState.cases, [caseState.cases])
  const canGenerateLlm = auth.hasPermission('llm:write')
  const canGenerateReport = auth.hasPermission('llm:report')
  const canReadEnrichment = auth.hasPermission('osint:read')
  const canWriteEnrichment = auth.hasPermission('osint:write')
  const canSummarizeEnrichment = auth.hasPermission('osint:summarize')
  const enrichmentState = useCaseEnrichment({
    caseId: caseState.selectedCase?.case_id,
    enabled: canReadEnrichment && Boolean(caseState.selectedCase?.case_id),
    onChanged: async () => {
      if (caseState.selectedCase?.case_id) {
        await caseState.selectCase(caseState.selectedCase.case_id)
      }
    },
  })

  useEffect(() => {
    if (caseState.generatedReport) {
      setReportDrawerOpen(true)
    }
  }, [caseState.generatedReport])

  function submitCreate(event) {
    event.preventDefault()
    if (!createForm.title.trim()) return
    caseState.createCase({
      title: createForm.title,
      description: createForm.description,
      priority: createForm.priority,
      severity: createForm.severity,
      camera_ids: createForm.camera_ids ? createForm.camera_ids.split(',').map(item => item.trim()).filter(Boolean) : [],
      tags: createForm.tags ? createForm.tags.split(',').map(item => item.trim()).filter(Boolean) : [],
    }).then(created => {
      setCreateForm({ title: '', description: '', priority: 'medium', severity: 'medium', camera_ids: '', tags: '' })
      if (created?.case_id) caseState.selectCase(created.case_id)
    }).catch(() => {})
  }

  return (
    <>
      <div className="page-grid two-column">
        <CaseList
          cases={filteredCases}
          selectedCaseId={caseState.selectedCase?.case_id}
          loading={caseState.loading}
          error={caseState.error}
          onRetry={caseState.refresh}
          onSelect={caseState.selectCase}
        />
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Manual Case Intake</p>
              <h2>Create Case</h2>
            </div>
            <div className="button-row">
              <span className="count-pill">{caseState.openCount} open</span>
              <button type="button" className="text-button" onClick={() => { window.location.hash = 'analytics' }}>
                Open Analytics
              </button>
              <button type="button" className="text-button" onClick={() => { window.location.hash = 'uploaded-video-analysis' }}>
                Analyze Uploaded Video
              </button>
            </div>
          </div>
          <div className="metric-strip">
            <article className="metric-tile"><span>Open Cases</span><strong>{caseState.openCount}</strong></article>
            <article className="metric-tile"><span>Critical Cases</span><strong>{caseState.criticalCount}</strong></article>
            <article className="metric-tile"><span>Requires Review</span><strong>{caseState.requiringReviewCount}</strong></article>
          </div>
          <div className="filter-row case-filter-row">
            <input aria-label="Search cases" value={caseState.filters.q || ''} onChange={event => caseState.setFilters(current => ({ ...current, q: event.target.value }))} placeholder="Search title or case ID" />
            <select value={caseState.filters.status || ''} onChange={event => caseState.setFilters(current => ({ ...current, status: event.target.value }))}>
              <option value="">All Statuses</option>
              <option value="open">Open</option>
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
              <option value="archived">Archived</option>
            </select>
            <select value={caseState.filters.priority || ''} onChange={event => caseState.setFilters(current => ({ ...current, priority: event.target.value }))}>
              <option value="">All Priorities</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
            <input aria-label="Filter by camera" value={caseState.filters.camera || ''} onChange={event => caseState.setFilters(current => ({ ...current, camera: event.target.value }))} placeholder="Camera ID" />
            <input aria-label="Filter by tag" value={caseState.filters.tag || ''} onChange={event => caseState.setFilters(current => ({ ...current, tag: event.target.value }))} placeholder="Tag" />
            <button type="button" className="text-button" onClick={() => caseState.refresh()}>Apply Filters</button>
          </div>
          <form className="case-create-form" onSubmit={submitCreate}>
            <input aria-label="Case title" value={createForm.title} onChange={event => setCreateForm(current => ({ ...current, title: event.target.value }))} placeholder="Case title" />
            <input aria-label="Case description" value={createForm.description} onChange={event => setCreateForm(current => ({ ...current, description: event.target.value }))} placeholder="Case description" />
            <select value={createForm.priority} onChange={event => setCreateForm(current => ({ ...current, priority: event.target.value }))}>
              <option value="low">Low Priority</option>
              <option value="medium">Medium Priority</option>
              <option value="high">High Priority</option>
              <option value="critical">Critical Priority</option>
            </select>
            <select value={createForm.severity} onChange={event => setCreateForm(current => ({ ...current, severity: event.target.value }))}>
              <option value="low">Low Severity</option>
              <option value="medium">Medium Severity</option>
              <option value="high">High Severity</option>
              <option value="critical">Critical Severity</option>
            </select>
            <input aria-label="Camera IDs" value={createForm.camera_ids} onChange={event => setCreateForm(current => ({ ...current, camera_ids: event.target.value }))} placeholder="Camera IDs (comma separated)" />
            <input aria-label="Case tags" value={createForm.tags} onChange={event => setCreateForm(current => ({ ...current, tags: event.target.value }))} placeholder="Tags (comma separated)" />
            <button type="submit" className="primary-button" disabled={caseState.actionLoading}>Create Case</button>
          </form>
        </section>
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">AI Assistance</p>
              <h2>LLM Status</h2>
            </div>
            <span className="count-pill">{caseState.llmStatus?.active_provider || 'pending'}</span>
          </div>
          <LlmSafetyBadge status={caseState.llmStatus} />
          <div className="drawer-grid case-health-grid">
            <span>Configured Provider</span><strong>{caseState.llmStatus?.provider || 'N/A'}</strong>
            <span>Active Provider</span><strong>{caseState.llmStatus?.active_provider || 'N/A'}</strong>
            <span>Status</span><strong>{caseState.llmStatus?.status || 'unknown'}</strong>
            <span>Default Model</span><strong>{caseState.llmStatus?.default_model || 'N/A'}</strong>
            <span>Escalation Model</span><strong>{caseState.llmStatus?.escalation_model || 'N/A'}</strong>
            <span>Final Report Model</span><strong>{caseState.llmStatus?.final_report_model || 'N/A'}</strong>
          </div>
          <p className="drawer-description">
            {caseState.llmVerification?.detail || caseState.llmStatus?.detail || 'AI-assisted drafts remain source-grounded and require operator review.'}
          </p>
          <button type="button" className="text-button" disabled={!canGenerateLlm || caseState.llmLoading || caseState.llmStatusLoading} onClick={() => caseState.verifyLlmProvider()}>
            Verify Provider
          </button>
        </section>
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">OSINT Safety</p>
              <h2>Manual Enrichment</h2>
            </div>
            <span className="count-pill">{caseState.selectedCase ? (enrichmentState.sources.length || 0) : 'case'}</span>
          </div>
          <div className="button-row">
            <span className="state-chip">Analyst-provided enrichment</span>
            <span className="state-chip">Requires operator review</span>
            <span className="state-chip">Not independently verified</span>
          </div>
          <p className="drawer-description">
            Manual source links, uploaded documents, and analyst notes can be attached to a selected case without any automatic scraping or external identity lookup.
          </p>
          <div className="drawer-grid case-health-grid">
            <span>Mode</span><strong>analyst_provided_only</strong>
            <span>Selected Case</span><strong>{caseState.selectedCase?.case_id || 'Select a case'}</strong>
            <span>Sources</span><strong>{enrichmentState.sources.length}</strong>
            <span>Summaries</span><strong>{enrichmentState.summaries.length}</strong>
          </div>
          {!canReadEnrichment ? <p className="drawer-description">Your role can view case details, but OSINT enrichment access is restricted.</p> : null}
        </section>
      </div>
      <CaseDetailDrawer
        open={Boolean(caseState.selectedCase)}
        caseItem={caseState.selectedCase}
        loading={caseState.detailLoading}
        error={caseState.error}
        timeline={caseState.timeline}
        evidence={caseState.evidence}
        notes={caseState.notes}
        busy={caseState.actionLoading}
        llmBusy={caseState.llmLoading}
        llmStatus={caseState.llmStatus}
        summaryOutput={caseState.summaryOutput}
        timelineSummary={caseState.timelineSummary}
        evidenceSummary={caseState.evidenceSummary}
        queryAnswer={caseState.queryAnswer}
        generatedReport={caseState.generatedReport}
        canGenerateLlm={canGenerateLlm}
        canGenerateReport={canGenerateReport}
        showEnrichment={canReadEnrichment}
        enrichmentState={enrichmentState}
        canReadEnrichment={canReadEnrichment}
        canWriteEnrichment={canWriteEnrichment}
        canSummarizeEnrichment={canSummarizeEnrichment}
        onClose={() => caseState.selectCase(null)}
        onAssign={(assignedTo, reason) => caseState.assignCase(caseState.selectedCase.case_id, assignedTo, reason)}
        onAddEvidence={payload => caseState.addEvidence(caseState.selectedCase.case_id, payload)}
        onUploadEvidenceFile={formData => caseState.uploadEvidenceFile(caseState.selectedCase.case_id, formData)}
        onVerifyEvidenceFile={evidenceId => caseState.verifyEvidenceFile(caseState.selectedCase.case_id, evidenceId)}
        onDownloadEvidenceFile={evidenceId => caseState.downloadEvidenceFile(caseState.selectedCase.case_id, evidenceId)}
        onExportEvidenceManifest={() => caseState.exportEvidenceManifest(caseState.selectedCase.case_id)}
        onAddNote={payload => caseState.addNote(caseState.selectedCase.case_id, payload)}
        onResolve={reason => caseState.closeCase(caseState.selectedCase.case_id, reason)}
        onReopen={reason => caseState.reopenCase(caseState.selectedCase.case_id, reason)}
        onDismiss={reason => caseState.dismissCase(caseState.selectedCase.case_id, reason)}
        onArchive={reason => caseState.archiveCase(caseState.selectedCase.case_id, reason)}
        onExport={format => caseState.exportCase(caseState.selectedCase.case_id, format)}
        onGenerateCaseSummary={() => caseState.generateCaseSummary(caseState.selectedCase.case_id, { summary_kind: 'case_summary' })}
        onGenerateIncidentSummary={() => caseState.generateCaseSummary(caseState.selectedCase.case_id, { summary_kind: 'incident_summary' })}
        onGenerateTimelineSummary={() => caseState.generateTimelineSummary(caseState.selectedCase.case_id)}
        onGenerateEvidenceSummary={() => caseState.generateEvidenceSummary(caseState.selectedCase.case_id)}
        onGenerateDraftReport={() => caseState.generateReport(caseState.selectedCase.case_id, { report_kind: 'draft_case_report' })}
        onGenerateHandoffReport={() => caseState.generateReport(caseState.selectedCase.case_id, { report_kind: 'operator_handoff_report' })}
        onAskCaseQuestion={payload => caseState.askCaseQuestion(caseState.selectedCase.case_id, payload)}
        onOpenGeneratedReport={() => setReportDrawerOpen(true)}
      />
      <GeneratedReportDrawer
        open={reportDrawerOpen && Boolean(caseState.generatedReport)}
        output={caseState.generatedReport}
        onClose={() => setReportDrawerOpen(false)}
      />
    </>
  )
}
