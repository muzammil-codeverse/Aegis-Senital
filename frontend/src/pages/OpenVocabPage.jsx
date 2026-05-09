import { useOpenVocab } from '../hooks/useOpenVocab'
import OpenVocabStatusPanel from '../components/openvocab/OpenVocabStatusPanel'
import PromptLibraryPanel from '../components/openvocab/PromptLibraryPanel'
import OpenVocabScanPanel from '../components/openvocab/OpenVocabScanPanel'
import OpenVocabResultsPanel from '../components/openvocab/OpenVocabResultsPanel'

/**
 * OpenVocabPage — Phase 23 open-vocabulary threat scanner console.
 * Displays scanner status, prompt library management, scan panel, and results.
 */
export default function OpenVocabPage({ cameras }) {
  const {
    status,
    prompts,
    results,
    loading,
    error,
    unavailable,
    refresh,
    scanLatestFrame,
    scanIncident,
    scanImage,
    createPrompt,
    updatePrompt,
    disablePrompt,
  } = useOpenVocab()

  return (
    <div className="page-grid single-column" style={{ padding: '16px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Error banner */}
      {error && (
        <div style={{
          background: '#431407', border: '1px solid #7c2d12', borderRadius: 4,
          padding: '8px 12px', marginBottom: 12, fontSize: '0.75rem', color: '#fdba74',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{error}</span>
          <button className="ctrl-btn" onClick={refresh} style={{ fontSize: '0.68rem' }}>Retry</button>
        </div>
      )}

      {/* Status panel */}
      <OpenVocabStatusPanel status={status} loading={loading} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* Left column: prompt library + scan panel */}
        <div>
          <PromptLibraryPanel
            prompts={prompts}
            loading={loading}
            onCreate={createPrompt}
            onUpdate={updatePrompt}
            onDisable={disablePrompt}
          />
          <OpenVocabScanPanel
            cameras={cameras || []}
            loading={loading}
            onScanCamera={scanLatestFrame}
            onScanImage={scanImage}
            onScanIncident={scanIncident}
          />
        </div>

        {/* Right column: results */}
        <div>
          <OpenVocabResultsPanel
            results={results}
            loading={loading}
            onRefresh={refresh}
          />
        </div>
      </div>
    </div>
  )
}
