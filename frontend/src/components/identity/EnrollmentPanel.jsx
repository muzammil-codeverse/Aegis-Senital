import React, { useMemo, useRef, useState } from 'react';

function formatPercent(value) {
  if (!Number.isFinite(value)) return 'n/a';
  return `${Math.round(value * 100)}%`;
}

function formatReason(reason) {
  return String(reason || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatTime(value) {
  if (!Number.isFinite(value)) return 'n/a';
  return new Date(value * 1000).toLocaleString();
}

export default function EnrollmentPanel({
  selectedIdentity,
  enrollments,
  enrollmentProfiles,
  batchEnroll,
  deleteEnrollment,
}) {
  const inputRef = useRef(null);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const rejectionReasonsByBatch = useMemo(() => {
    const reasons = new Map();
    for (const enrollment of enrollments || []) {
      const key = enrollment.batch_enrollment_id || enrollment.enrollment_id;
      if (!reasons.has(key)) reasons.set(key, new Set());
      for (const reason of enrollment.rejection_reasons || []) {
        reasons.get(key).add(formatReason(reason));
      }
    }
    return reasons;
  }, [enrollments]);

  const recentEnrollments = useMemo(
    () => [...(enrollments || [])].sort((left, right) => (right.created_at || 0) - (left.created_at || 0)).slice(0, 8),
    [enrollments],
  );

  const handleFilesSelected = (event) => {
    const files = Array.from(event.target.files || []);
    setSelectedFiles(files);
  };

  const handleSubmit = async () => {
    if (!selectedFiles.length || !selectedIdentity) return;
    setSubmitting(true);
    setResult(null);
    const response = await batchEnroll(selectedFiles, {
      identity_id: selectedIdentity.identity_id,
      display_name: selectedIdentity.display_name || undefined,
    });
    setResult(response);
    setSubmitting(false);
    setSelectedFiles([]);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div
      style={{
        border: '1px solid #21262d',
        background: '#161b22',
        borderRadius: '8px',
        padding: '16px',
        display: 'grid',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: '#e6edf3' }}>Enrollment Quality</div>
          <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>
            Possible identity match records are created only from accepted images.
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".jpg,.jpeg,.png"
            onChange={handleFilesSelected}
            style={{ maxWidth: '250px', color: '#8b949e', fontSize: '12px' }}
          />
          <button
            onClick={handleSubmit}
            disabled={!selectedFiles.length || submitting}
            style={{
              padding: '7px 12px',
              borderRadius: '6px',
              border: 'none',
              background: !selectedFiles.length || submitting ? '#30363d' : '#1f6feb',
              color: '#e6edf3',
              cursor: !selectedFiles.length || submitting ? 'default' : 'pointer',
              fontSize: '12px',
            }}
          >
            {submitting ? 'Enrolling...' : `Enroll ${selectedFiles.length || ''} Images`.trim()}
          </button>
        </div>
      </div>

      {result && (
        <div
          style={{
            border: `1px solid ${result.status === 'ok' ? '#3fb95055' : '#f8514955'}`,
            background: result.status === 'ok' ? '#0d1117' : '#251116',
            borderRadius: '8px',
            padding: '12px',
            fontSize: '12px',
            color: result.status === 'ok' ? '#3fb950' : '#f85149',
          }}
        >
          {result.status === 'ok'
            ? `Enrollment complete. Accepted ${result.accepted_images || 0}, rejected ${result.rejected_images || 0}.`
            : result.detail || 'Enrollment failed.'}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: '12px',
        }}
      >
        {(enrollmentProfiles || []).length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>No enrollment batches recorded.</div>
        ) : (
          enrollmentProfiles.map((profile) => {
            const rejectionReasons = Array.from(
              rejectionReasonsByBatch.get(profile.enrollment_id) || [],
            );
            const qualityAverage = profile.quality_summary?.accepted_quality_avg;
            return (
              <div
                key={profile.enrollment_id}
                style={{
                  border: '1px solid #21262d',
                  background: '#0d1117',
                  borderRadius: '8px',
                  padding: '12px',
                  display: 'grid',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                  <div>
                    <div style={{ fontSize: '13px', color: '#e6edf3', fontWeight: 600 }}>
                      {profile.display_name || selectedIdentity?.display_name || 'Unnamed Identity'}
                    </div>
                    <div style={{ fontSize: '11px', color: '#8b949e', fontFamily: 'monospace' }}>
                      {profile.enrollment_id}
                    </div>
                  </div>
                  <button
                    onClick={() => deleteEnrollment(profile.enrollment_id)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: '5px',
                      border: '1px solid #30363d',
                      background: 'transparent',
                      color: '#8b949e',
                      cursor: 'pointer',
                      fontSize: '11px',
                    }}
                  >
                    Delete
                  </button>
                </div>

                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '12px' }}>
                  <span style={{ color: '#3fb950' }}>Accepted {profile.accepted_images}</span>
                  <span style={{ color: '#f85149' }}>Rejected {profile.rejected_images}</span>
                  <span style={{ color: '#58a6ff' }}>Quality {formatPercent(qualityAverage)}</span>
                </div>

                <div style={{ fontSize: '12px', color: '#8b949e', display: 'grid', gap: '4px' }}>
                  <span>Status: {formatReason(profile.status)}</span>
                  <span>Aggregate: {formatReason(profile.aggregate_method)}</span>
                  <span>Updated: {formatTime(profile.updated_at || profile.created_at)}</span>
                </div>

                {rejectionReasons.length > 0 && (
                  <div style={{ fontSize: '12px', color: '#d29922' }}>
                    Low-quality face rejected: {rejectionReasons.join(', ')}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      <div style={{ display: 'grid', gap: '8px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3' }}>Per-Image Review</div>
        {recentEnrollments.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>No per-image records yet.</div>
        ) : (
          recentEnrollments.map((enrollment) => (
            <div
              key={enrollment.enrollment_id}
              style={{
                border: '1px solid #21262d',
                background: '#0d1117',
                borderRadius: '8px',
                padding: '10px 12px',
                display: 'grid',
                gap: '6px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: '#e6edf3' }}>
                  {enrollment.status === 'accepted' ? 'Accepted face image' : 'Low-quality face rejected'}
                </span>
                <span style={{ fontSize: '11px', color: '#8b949e' }}>{formatTime(enrollment.created_at)}</span>
              </div>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '12px', color: '#8b949e' }}>
                <span>Quality {formatPercent(enrollment.quality_score)}</span>
                <span>Batch {enrollment.batch_enrollment_id || 'single-image'}</span>
              </div>
              {(enrollment.rejection_reasons || []).length > 0 && (
                <div style={{ fontSize: '12px', color: '#d29922' }}>
                  Reasons: {enrollment.rejection_reasons.map(formatReason).join(', ')}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
