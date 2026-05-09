/**
 * FaceEnrollmentPanel — face image upload and enrollment list for an identity.
 */
import React, { useRef, useState } from 'react';

export default function FaceEnrollmentPanel({ identityId, enrollments, uploadFace }) {
  const inputRef = useRef();
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    const res = await uploadFace(identityId, file);
    setUploadResult(res);
    setUploading(false);
    // Reset file input so the same file can be re-uploaded if needed
    e.target.value = '';
  };

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3', marginBottom: '8px' }}>
        Face Enrollments ({enrollments.length})
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', alignItems: 'center' }}>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          style={{
            padding: '6px 12px',
            borderRadius: '5px',
            border: 'none',
            cursor: 'pointer',
            background: '#1f6feb',
            color: '#e6edf3',
            fontSize: '12px',
          }}
        >
          {uploading ? 'Uploading...' : 'Upload Face Image'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".jpg,.jpeg,.png"
          onChange={handleUpload}
          style={{ display: 'none' }}
        />
        {uploadResult && (
          <span
            style={{
              fontSize: '12px',
              color: uploadResult.status === 'ok' ? '#3fb950' : '#f85149',
            }}
          >
            {uploadResult.status === 'ok'
              ? 'Enrolled successfully'
              : uploadResult.detail || 'Upload failed'}
          </span>
        )}
      </div>
      {enrollments.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {enrollments.map((e) => (
            <div
              key={e.enrollment_id}
              style={{
                padding: '6px 10px',
                background: '#0d1117',
                borderRadius: '4px',
                fontSize: '12px',
                color: '#8b949e',
              }}
            >
              Enrollment {e.enrollment_id.slice(0, 8)}
              {e.quality_score != null && (
                <span style={{ marginLeft: '8px', color: '#3fb950' }}>
                  Q: {(e.quality_score * 100).toFixed(0)}%
                </span>
              )}
              <span style={{ marginLeft: '8px' }}>
                {new Date(e.created_at * 1000).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ color: '#8b949e', fontSize: '12px' }}>No enrollments yet</div>
      )}
    </div>
  );
}
