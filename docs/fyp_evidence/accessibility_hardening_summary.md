# Phase 49 — Accessibility Hardening Summary

## Phase 48 Baseline

The Phase 48 static checker reported **85 `input-no-label` warnings** across the
frontend source.  These were identified as inputs lacking `aria-label` attributes
or programmatic label association.

## Phase 49 Fixes

### Checker Improvements

The `check_frontend_accessibility_static.py` script was improved with two fixes:

1. **Label-context detection**: The checker now uses last-position tracking to
   detect inputs that are correctly wrapped inside a `<label>` element. These
   were previously flagged as false positives. The fix reduced the warning count
   by 18 (inputs already inside `<label>` wrappers).

2. **Full-tag scanning**: The original regex stopped at `>` characters inside
   JSX arrow function handlers (`onChange={e =>}`), causing inputs with existing
   `aria-label` attributes to be incorrectly flagged. The checker now scans the
   full input tag to find `aria-label=` before reporting a warning.

### Files Fixed (65 inputs received `aria-label` attributes)

| File | Inputs Fixed | Labels Added |
|------|-------------|--------------|
| `gis/CameraGeoProfileDrawer.jsx` | 8 | Latitude, Longitude, Altitude, Heading, FOV, Coverage radius, Region, Floor |
| `cases/CaseEvidencePanel.jsx` | 6 | Upload file, Upload title, Upload description, Evidence title, Source event ID, Reference URI |
| `pages/CasesPage.jsx` | 7 | Search cases, Filter by camera, Filter by tag, Case title, Case description, Camera IDs, Case tags |
| `security/UserManagementPanel.jsx` | 4 | Username, Display name, Temporary password, New password |
| `identity/IdentityTable.jsx` | 3 | Display name, Tags, Notes |
| `investigation/PathReconstructionPanel.jsx` | 2 | Case ID, Event ID |
| `identity/WatchlistPanel.jsx` | 2 | Watchlist reason, Expiry days |
| `model-governance/ModelRollbackPanel.jsx` | 2 | Model key, Model version |
| `openvocab/OpenVocabScanPanel.jsx` | 3 | Camera ID, Upload image, Incident ID |
| `openvocab/PromptLibraryPanel.jsx` | 3 | Prompt text, Confidence threshold, Edit threshold |
| `osint/AddExternalLinkForm.jsx` | 3 | Link title, URL, Link description |
| `osint/DocumentUploadPanel.jsx` | 3 | Upload document, Document title, Analyst note |
| `security/AuditLogTable.jsx` | 3 | Filter by action, Filter by user, Filter by resource |
| `cases/CaseAssignmentPanel.jsx` | 2 | Assignee username, Assignment note |
| `osint/CaseEnrichmentPanel.jsx` | 2 | Manual source title, Analyst enrichment note |
| `command/CommandPalette.jsx` | 1 | Search command palette |
| `cases/CaseNotesPanel.jsx` | 1 | Add operator note |
| `cases/NaturalLanguageQueryPanel.jsx` | 1 | Ask question |
| `drone-fusion/FusionReviewControls.jsx` | 1 | Review notes |
| `identity/EnrollmentPanel.jsx` | 1 | Upload identity images |
| `identity/FaceEnrollmentPanel.jsx` | 1 | Upload face image (hidden input) |
| `incidents/IncidentReplayDrawer.jsx` | 1 | Replay timeline position |
| `model-governance/ModelDriftPanel.jsx` | 1 | Model ID |
| `osint/EnrichmentSummaryPanel.jsx` | 1 | Summarization instructions |
| `uploaded-video/CreateCaseFromVideoButton.jsx` | 1 | Case title override |
| `uploaded-video/UploadedVideoDropzone.jsx` | 1 | Upload video file |
| `pages/DroneFusionPage.jsx` | 1 | Filter by case ID |

## After Phase 49

```
[a11y-static] No accessibility issues found.
```

**0 blocking warnings** for user-facing inputs/buttons/images.

## Regression Tests

`tests/test_phase49_accessibility_contract.py` — 11 tests:
- Checker script exists and runs
- Zero blocking warnings
- Key components have `aria-label` attributes (spot checks)

## Remaining Intentional Choices

- File inputs with `hidden` or `display: none` (e.g., `FaceEnrollmentPanel.jsx`)
  still received `aria-label` for completeness, even though they are not
  directly user-reachable.
- Inputs already inside `<label>...</label>` wrappers are correctly excluded
  from warnings by the improved checker.
