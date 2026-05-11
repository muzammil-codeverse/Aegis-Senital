# Phase 37 Persistence and Storage Architecture

## Scope

Phase 37 moves Aegis Sentinel from mixed development persistence toward production-grade durability for:

- case metadata and case audit history
- OSINT metadata
- identity registry metadata and observations
- runtime audit logs
- retention action records
- open-vocabulary result metadata
- replay clip metadata

Raw evidence binaries, uploaded files, replay clips, and model binaries remain file-backed artifacts. This phase keeps those artifacts out of PostgreSQL by default and persists metadata, hashes, and manifests instead.

## Runtime Persistence Policy

Primary runtime policy is defined in `configs/runtime/persistence.yaml`.

- Development allows JSONL and local filesystem storage.
- Production requires PostgreSQL for required stores.
- Production forbids silent JSONL fallback for required stores.
- Production requires managed artifact storage semantics for evidence files.
- Backup and restore are metadata-first and confirmation-gated.

## PostgreSQL Schema Bootstrap

Schema bootstrap entrypoints:

- `backend/app/db/schema_definitions.py`
- `backend/app/db/schema_bootstrap.py`
- `scripts/bootstrap_postgres_schema.py`

Bootstrap is idempotent and only uses `CREATE TABLE IF NOT EXISTS`, additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, additive indexes, and compatibility view creation. No destructive `DROP` statements are used by default.

### Tables Bootstrapped

- `events`
- `cases`
- `case_evidence`
- `case_notes`
- `case_audit_logs`
- `case_reports`
- `osint_sources`
- `osint_summaries`
- `osint_audit`
- `identity_enrollments`
- `identity_observations`
- `global_identity_links`
- `watchlists`
- `open_vocab_results`
- `stream_replay_metadata`
- `system_audit_logs`
- `retention_actions`
- `model_registry_entries`

### Compatibility

- `case_audit` compatibility view now maps to `case_audit_logs`.

## Store Mapping

### Required in production

- `events` -> PostgreSQL
- `cases` -> PostgreSQL
- `evidence_metadata` -> PostgreSQL
- `evidence_files` -> managed filesystem or object storage
- `identity_registry` -> PostgreSQL
- `audit_logs` -> PostgreSQL
- `osint` -> PostgreSQL
- `retention_actions` -> PostgreSQL

### Optional in production

- `analytics` -> derived or PostgreSQL-backed sources
- `watchlists` -> PostgreSQL when used
- `open_vocab_results` -> PostgreSQL-ready metadata store
- `stream_replay_metadata` -> PostgreSQL-ready metadata store
- `model_registry` -> file-backed metadata today, PostgreSQL table reserved

## Identity Storage Safety

Durable identity registry persistence stores:

- global identity ids
- camera observations
- first seen / last seen
- confidence history
- source scores
- review status
- linked case ids
- TTL / decay metadata

Phase 37 does not persist raw face embeddings or raw face images into the new registry tables.

Legacy track/event/scenario persistence was also tightened so embedded payloads written to metadata do not retain raw embedding vectors or raw face-image-style fields.

## Retention Workflow

Retention runtime policy is defined in `configs/runtime/evidence.yaml`.

Modes:

- `dry_run`
- `quarantine`
- `delete`

Safety rules:

- default mode is `dry_run`
- execution requires explicit reviewed mode
- legal-hold evidence is excluded from quarantine and delete
- delete requires the explicit confirmation token
- quarantine moves files into `storage/evidence_quarantine/`
- metadata and hashes remain preserved
- retention actions are durably recorded
- retention actions are audited before and after execution

## Backup and Restore

Scripts:

- `scripts/backup_runtime_metadata.py`
- `scripts/restore_runtime_metadata.py`

Backup includes:

- runtime config snapshots
- JSONL metadata stores
- model registry metadata
- case, OSINT, identity, audit, replay, open-vocab, and retention metadata snapshots
- file manifests and checksums

Backup excludes by default:

- raw evidence binaries
- replay video binaries
- uploaded source binaries
- model weights
- datasets

Restore is dry-run by default and validates:

- `manifest.json`
- `checksums.json`
- copied file checksums
- overwrite confirmation before replacing runtime files

## Runtime Readiness

`RuntimeHealthService` now includes a dedicated persistence block and production fail-fast rules for:

- missing `POSTGRES_DSN`
- missing required PostgreSQL tables
- prohibited JSONL fallback on required stores
- unavailable required artifact storage

`scripts/validate_runtime.py` now surfaces the same persistence expectations in offline validation runs.

## Phase 38 Carry-Forward Notes

Phase 37 intentionally keeps several data domains metadata-first:

- alerts/incidents remain primarily runtime-managed
- analytics exports are represented through metadata snapshots and metrics, not a dedicated export repository
- model registry PostgreSQL table is reserved for later activation

Phase 38 should only expand these areas if the next workflow requires durable queryable history beyond the current metadata coverage.
