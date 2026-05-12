import React from 'react'

export default function ModelRegistryPanel({ entries = [] }) {
  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Registry</p>
          <h2>Runtime models</h2>
        </div>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ width: '100%', fontSize: 12 }}>
          <thead>
            <tr>
              <th>Model ID</th>
              <th>Task</th>
              <th>Status</th>
              <th>Approval</th>
              <th>Path</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((row) => (
              <tr key={`${row.model_key}-${row.version}`}>
                <td>{row.model_id}</td>
                <td>{row.task}</td>
                <td>{row.status}</td>
                <td>{row.approval_status}</td>
                <td style={{ wordBreak: 'break-all' }}>{row.path}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
