import { useState } from 'react'
import { Download } from 'lucide-react'

const SECTION_OPTIONS = [
  'overview',
  'event_timeseries',
  'events_by_type',
  'case_summary',
  'case_timeseries',
  'camera_risk',
  'model_performance',
  'anomaly_trends',
  'stream_reliability',
  'operator_workload',
  'system_performance',
  'identity_summary',
  'open_vocab_summary',
]

export default function AnalyticsExportPanel({ filters, onExport, canExport, exporting }) {
  const [format, setFormat] = useState('json')
  const [selectedSections, setSelectedSections] = useState(['overview', 'camera_risk', 'system_performance'])

  function toggleSection(section) {
    setSelectedSections(current => (
      current.includes(section)
        ? current.filter(item => item !== section)
        : [...current, section]
    ))
  }

  return (
    <section className="panel analytics-panel analytics-span-7">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Analytics Export</p>
          <h2>Download Current Intelligence Window</h2>
        </div>
        <span className="count-pill">{filters.window}</span>
      </div>
      <div className="analytics-export-layout">
        <div className="analytics-export-controls">
          <label>
            <span>Format</span>
            <select value={format} onChange={event => setFormat(event.target.value)}>
              <option value="json">JSON</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          <p className="muted">Exports use the active time window, bucket, severity, camera, and search filters already applied to the dashboard.</p>
          <button
            type="button"
            className="primary-button analytics-refresh-button"
            onClick={() => onExport({ format, sections: selectedSections })}
            disabled={!canExport || exporting || selectedSections.length === 0}
          >
            <Download size={14} />
            <span>{exporting ? 'Preparing export' : 'Export analytics'}</span>
          </button>
          {!canExport ? <p className="muted">Your role can read analytics, but export access is restricted.</p> : null}
        </div>
        <div className="analytics-section-picker">
          {SECTION_OPTIONS.map(section => (
            <label key={section} className="analytics-section-option">
              <input type="checkbox" checked={selectedSections.includes(section)} onChange={() => toggleSection(section)} />
              <span>{section.replace(/_/g, ' ')}</span>
            </label>
          ))}
        </div>
      </div>
    </section>
  )
}
