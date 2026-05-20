# Phase 3 Uploaded Video API Contract

Scope: exhibition-critical uploaded-video intelligence path only.

## Endpoints

| Caller | Method | Endpoint | Request | Success response |
| --- | --- | --- | --- | --- |
| `listUploadedVideoSessions` | `GET` | `/api/uploaded-videos` | Authenticated request | `{ "items": UploadedVideoSession[], "count": number, "status": "ok" \| "empty" }` |
| `uploadUploadedVideo` | `POST` | `/api/uploaded-videos` | `multipart/form-data` with `file` and JSON string `options` | `{ "session": UploadedVideoSession, "status": "uploaded", "detail": string }` |
| `getUploadedVideoSession` | `GET` | `/api/uploaded-videos/{session_id}` | Authenticated request | `{ "item": UploadedVideoSession, "status": "ok" }` |
| `startUploadedVideoProcessing` | `POST` | `/api/uploaded-videos/{session_id}/process` | Empty body | `{ "item": UploadedVideoProcessingStatus, "status": "ok" }` |
| `getUploadedVideoStatus` | `GET` | `/api/uploaded-videos/{session_id}/status` | Authenticated request | `{ "item": UploadedVideoProcessingStatus, "status": "ok" }` |
| `getUploadedVideoTimeline` | `GET` | `/api/uploaded-videos/{session_id}/timeline` | Authenticated request | `{ "items": UploadedVideoTimelineItem[], "count": number, "status": "ok" \| "empty" }` |
| `getUploadedVideoEvents` | `GET` | `/api/uploaded-videos/{session_id}/events` | Authenticated request | `{ "items": UploadedVideoEvent[], "count": number, "status": "ok" \| "empty" }` |
| `getUploadedVideoReport` | `GET` | `/api/uploaded-videos/{session_id}/report` | Authenticated request | `{ "item": UploadedVideoReport, "status": "ok" }` |
| `cancelUploadedVideoProcessing` | `POST` | `/api/uploaded-videos/{session_id}/cancel` | Empty body | `{ "item": UploadedVideoProcessingStatus, "status": "ok" }` |

## State Machine

Backend states are lowercase on the wire and map directly to operator UI labels:

`created -> uploaded -> queued -> processing -> frame_extraction -> inference -> event_generation -> report_generation -> completed`

Terminal alternatives:

`failed`, `cancelled`

The frontend treats unknown states as explicit warnings, not success.

## Error Shape

Uploaded-video route-level errors use FastAPI HTTP status codes with a structured `detail` object:

```json
{
  "detail": {
    "status": "error",
    "code": "processing_unavailable",
    "detail": "Detector capability not ready for uploaded-video processing."
  }
}
```

The frontend API client normalizes both string `detail` and object `detail.detail` into an actionable `ApiError.message`.

## Persistence

Processing status is persisted under `storage/uploaded_video_results/{session_id}/status.json`.
Events, timeline, and report are persisted as `events.json`, `timeline.json`, and `report.json`.
Failures persist `last_error` on the status object and `session.metadata.last_error`.

## Contract Fixes In Phase 3

- Completed reports are no longer cleared by `useUploadedVideo`.
- `getUploadedVideoStatus` is loaded with session detail so failed sessions show persisted backend causes.
- Report rendering accepts missing or partial summary fields and displays honest no-detection output.
- Route errors for upload/process use structured error objects, and the shared client extracts human-readable messages.
- Processing states now expose frame extraction, inference, event generation, and report generation instead of a single opaque `processing` state.

## Remaining Risks

- WebSocket messages currently send raw status objects while REST status wraps them in `{ item, status }`; the progress hook intentionally handles the raw WebSocket shape.
- Processing is still file-backed and in-process; run history and job orchestration are not durable across backend restarts.
- Full event/alert/case command-center promotion remains Phase 4 scope.
