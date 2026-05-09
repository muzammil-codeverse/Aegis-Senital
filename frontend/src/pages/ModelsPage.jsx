/**
 * ModelsPage — model registry browser with per-model health, inference stats,
 * and inline editing of runtime parameters.
 */
import React, { useState } from 'react';
import { useModelRegistry } from '../hooks/useModelRegistry.js';

const HEALTH_COLORS = {
  ok: '#3fb950',
  loaded: '#3fb950',
  unknown: '#e3b341',
  error: '#f85149',
};

/**
 * ModelCard — renders a single model entry with an expandable edit panel.
 */
function ModelCard({ model, onUpdate }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    enabled: model.enabled,
    confidence_threshold: model.confidence_threshold,
    device_preference: model.device_preference,
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    await onUpdate(model.model_id, form);
    setSaving(false);
    setEditing(false);
  };

  const health = model.health || {};
  const inference = model.inference || {};
  const healthStatus = health.status || 'unknown';

  return (
    <div
      style={{
        background: '#161b22',
        border: '1px solid #21262d',
        borderRadius: '8px',
        padding: '14px',
        marginBottom: '10px',
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
          marginBottom: '8px',
        }}
      >
        <div
          style={{
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            background: model.enabled ? '#3fb950' : '#8b949e',
            flexShrink: 0,
            marginTop: '4px',
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#e6edf3' }}>
            {model.name}
          </div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>
            {model.model_id} | {model.task} | v{model.version}
          </div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>
            {model.format} | {model.device_preference}
          </div>
        </div>
        <span
          style={{
            fontSize: '11px',
            padding: '2px 8px',
            borderRadius: '10px',
            background: '#21262d',
            color: HEALTH_COLORS[healthStatus] || '#8b949e',
          }}
        >
          {healthStatus}
        </span>
        <button
          onClick={() => setEditing(!editing)}
          style={{
            padding: '4px 10px',
            borderRadius: '5px',
            border: 'none',
            cursor: 'pointer',
            background: '#21262d',
            color: '#e6edf3',
            fontSize: '12px',
          }}
        >
          Edit
        </button>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: '#8b949e' }}>
        <span>Threshold: {model.confidence_threshold}</span>
        <span>Inferences: {inference.total_inferences || 0}</span>
        {inference.avg_latency_ms != null && (
          <span>Avg: {inference.avg_latency_ms.toFixed(1)}ms</span>
        )}
        {inference.last_inference_at && (
          <span>
            Last: {new Date(inference.last_inference_at * 1000).toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Inline edit panel */}
      {editing && (
        <div
          style={{
            marginTop: '10px',
            padding: '10px',
            background: '#0d1117',
            borderRadius: '6px',
          }}
        >
          <div
            style={{
              display: 'flex',
              gap: '10px',
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <label
              style={{
                fontSize: '12px',
                color: '#e6edf3',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) =>
                  setForm((f) => ({ ...f, enabled: e.target.checked }))
                }
              />
              Enabled
            </label>
            <label style={{ fontSize: '12px', color: '#e6edf3' }}>
              Threshold:
              <input
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={form.confidence_threshold}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    confidence_threshold: parseFloat(e.target.value),
                  }))
                }
                style={{
                  marginLeft: '6px',
                  width: '70px',
                  padding: '4px',
                  background: '#21262d',
                  border: '1px solid #30363d',
                  borderRadius: '4px',
                  color: '#e6edf3',
                  fontSize: '12px',
                }}
              />
            </label>
            <label style={{ fontSize: '12px', color: '#e6edf3' }}>
              Device:
              <select
                value={form.device_preference}
                onChange={(e) =>
                  setForm((f) => ({ ...f, device_preference: e.target.value }))
                }
                style={{
                  marginLeft: '6px',
                  padding: '4px',
                  background: '#21262d',
                  border: '1px solid #30363d',
                  borderRadius: '4px',
                  color: '#e6edf3',
                  fontSize: '12px',
                }}
              >
                <option value="auto">auto</option>
                <option value="cuda">cuda</option>
                <option value="cpu">cpu</option>
              </select>
            </label>
            <button
              onClick={save}
              disabled={saving}
              style={{
                padding: '4px 12px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: '#1f6feb',
                color: '#e6edf3',
                fontSize: '12px',
              }}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => setEditing(false)}
              style={{
                padding: '4px 12px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: '#21262d',
                color: '#8b949e',
                fontSize: '12px',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ModelsPage() {
  const { models, loading, error, reloading, reload, update } = useModelRegistry();

  return (
    <div
      style={{
        height: '100%',
        background: '#0d1117',
        color: '#e6edf3',
        padding: '16px',
        overflowY: 'auto',
      }}
    >
      {/* Page header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '16px',
        }}
      >
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, flex: 1 }}>
          Model Registry
        </h2>
        <span style={{ fontSize: '13px', color: '#8b949e' }}>{models.length} models</span>
        <button
          onClick={reload}
          disabled={reloading}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: 'none',
            cursor: 'pointer',
            background: reloading ? '#21262d' : '#1f6feb',
            color: '#e6edf3',
            fontSize: '13px',
          }}
        >
          {reloading ? 'Reloading...' : 'Reload Registry'}
        </button>
      </div>

      {loading && (
        <div style={{ color: '#8b949e', textAlign: 'center', padding: '40px' }}>
          Loading models...
        </div>
      )}
      {error && (
        <div
          style={{
            color: '#f85149',
            padding: '12px',
            marginBottom: '12px',
            background: '#160b0b',
            borderRadius: '6px',
          }}
        >
          {error}
        </div>
      )}

      {models.length === 0 && !loading ? (
        <div style={{ color: '#8b949e', textAlign: 'center', padding: '40px' }}>
          No models in registry
        </div>
      ) : (
        models.map((model) => (
          <ModelCard key={model.model_id} model={model} onUpdate={update} />
        ))
      )}
    </div>
  );
}
