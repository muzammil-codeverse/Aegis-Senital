import { useState } from 'react'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import AddExternalLinkForm from './AddExternalLinkForm'
import DocumentUploadPanel from './DocumentUploadPanel'
import EnrichmentSummaryPanel from './EnrichmentSummaryPanel'
import ExternalSourceList from './ExternalSourceList'
import OsintSafetyNotice from './OsintSafetyNotice'

export default function CaseEnrichmentPanel({
  enrichmentState,
  canRead = false,
  canWrite = false,
  canSummarize = false,
}) {
  const [manualType, setManualType] = useState('analyst_note')
  const [manualTitle, setManualTitle] = useState('')
  const [manualDescription, setManualDescription] = useState('')

  if (!canRead) return null

  function submitManual(event) {
    event.preventDefault()
    if (!manualDescription.trim()) return
    enrichmentState?.createSource?.({
      source_type: manualType,
      title: manualTitle || (manualType === 'analyst_note' ? 'Analyst note' : 'Manual metadata'),
      description: manualDescription,
      source_reliability: 'unknown',
      metadata: {},
    })
    setManualTitle('')
    setManualDescription('')
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Analyst-Provided Enrichment</h3>
        <span>Not independently verified</span>
      </div>
      <OsintSafetyNotice />
      {enrichmentState?.loading ? <LoadingState label="Loading enrichment" /> : null}
      {enrichmentState?.error ? <ErrorState message={enrichmentState.error} /> : null}
      {canWrite ? (
        <>
          <AddExternalLinkForm
            busy={enrichmentState?.actionLoading}
            disabled={!canWrite}
            onSubmit={payload => enrichmentState?.addExternalLink?.(payload)}
          />
          <DocumentUploadPanel
            busy={enrichmentState?.actionLoading}
            disabled={!canWrite}
            onUpload={(file, metadata) => enrichmentState?.uploadDocument?.(file, metadata)}
          />
          <form className="case-inline-form" onSubmit={submitManual}>
            <select value={manualType} onChange={event => setManualType(event.target.value)}>
              <option value="analyst_note">Analyst note</option>
              <option value="manual_metadata">Manual metadata</option>
            </select>
            <input aria-label="Manual source title" value={manualTitle} onChange={event => setManualTitle(event.target.value)} placeholder="Manual source title" />
            <input aria-label="Analyst enrichment note" value={manualDescription} onChange={event => setManualDescription(event.target.value)} placeholder="Analyst-provided enrichment note" />
            <button type="submit" className="text-button" disabled={enrichmentState?.actionLoading}>Save Manual Source</button>
          </form>
        </>
      ) : null}
      <ExternalSourceList
        items={enrichmentState?.sources || []}
        busy={enrichmentState?.actionLoading}
        canWrite={canWrite}
        onDelete={sourceId => enrichmentState?.deleteSource?.(sourceId)}
        onUpdateReliability={(sourceId, source_reliability) => enrichmentState?.updateSource?.(sourceId, { source_reliability })}
      />
      <EnrichmentSummaryPanel
        items={enrichmentState?.summaries || []}
        sourceCount={(enrichmentState?.sources || []).length}
        busy={enrichmentState?.actionLoading}
        canSummarize={canSummarize}
        onSummarize={payload => enrichmentState?.summarize?.(payload)}
      />
    </section>
  )
}
