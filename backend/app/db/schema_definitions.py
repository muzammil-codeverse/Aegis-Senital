from __future__ import annotations

from typing import Any


TABLE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "events": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            id TEXT NULL,
            track_id TEXT NULL,
            event_type TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            risk_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            timestamp TIMESTAMPTZ NOT NULL,
            severity TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NULL,
            owner_id TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE events ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_events_severity ON events (severity)",
        ),
    },
    "cases": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY,
            id TEXT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            severity TEXT NOT NULL,
            source_event_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            camera_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            track_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            assigned_to TEXT NULL,
            created_by TEXT NOT NULL,
            owner_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            closed_at TIMESTAMPTZ NULL,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            requires_review BOOLEAN NOT NULL DEFAULT TRUE,
            review_status TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE cases ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE cases ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE cases ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_cases_status ON cases (status)",
            "CREATE INDEX IF NOT EXISTS idx_cases_updated_at ON cases (updated_at DESC)",
        ),
    },
    "case_evidence": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS case_evidence (
            evidence_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            evidence_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            source_event_id TEXT NULL,
            camera_id TEXT NULL,
            track_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            storage_uri TEXT NULL,
            snapshot_uri TEXT NULL,
            original_filename TEXT NULL,
            safe_filename TEXT NULL,
            content_type TEXT NULL,
            size_bytes BIGINT NULL,
            created_by TEXT NOT NULL,
            owner_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            timestamp TIMESTAMPTZ NOT NULL,
            hash_sha256 TEXT NULL,
            hash_verified BOOLEAN NULL,
            integrity_status TEXT NOT NULL,
            chain_status TEXT NOT NULL DEFAULT 'active',
            last_verified_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_case_evidence_case_id ON case_evidence (case_id)",
            "CREATE INDEX IF NOT EXISTS idx_case_evidence_chain_status ON case_evidence (chain_status)",
        ),
    },
    "case_notes": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS case_notes (
            note_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            note TEXT NOT NULL,
            created_by TEXT NOT NULL,
            owner_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE case_notes ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE case_notes ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE case_notes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE case_notes ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_case_notes_case_id ON case_notes (case_id)",
        ),
    },
    "case_audit_logs": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS case_audit_logs (
            audit_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            action_status TEXT NULL,
            detail TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE case_audit_logs ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE case_audit_logs ADD COLUMN IF NOT EXISTS action_status TEXT NULL",
            "ALTER TABLE case_audit_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE case_audit_logs ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_case_audit_logs_case_id ON case_audit_logs (case_id)",
            "CREATE INDEX IF NOT EXISTS idx_case_audit_logs_created_at ON case_audit_logs (created_at DESC)",
        ),
    },
    "case_reports": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS case_reports (
            export_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
            format TEXT NOT NULL,
            report_type TEXT NOT NULL DEFAULT 'case_export',
            content TEXT NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL,
            generated_by TEXT NOT NULL,
            owner_id TEXT NULL,
            artifact_uri TEXT NULL,
            content_type TEXT NULL,
            size_bytes BIGINT NULL,
            hash_sha256 TEXT NULL,
            hash_verified BOOLEAN NULL,
            integrity_status TEXT NOT NULL DEFAULT 'pending',
            last_verified_at TIMESTAMPTZ NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE case_reports ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_case_reports_case_id ON case_reports (case_id)",
        ),
    },
    "osint_sources": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS osint_sources (
            source_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NULL,
            storage_uri TEXT NULL,
            original_filename TEXT NULL,
            safe_filename TEXT NULL,
            content_type TEXT NULL,
            size_bytes BIGINT NULL,
            hash_sha256 TEXT NULL,
            hash_verified BOOLEAN NULL,
            integrity_status TEXT NOT NULL DEFAULT 'not_applicable',
            last_verified_at TIMESTAMPTZ NULL,
            description TEXT NOT NULL,
            source_reliability TEXT NOT NULL,
            analyst_provided BOOLEAN NOT NULL,
            created_by TEXT NOT NULL,
            owner_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            summary TEXT NULL,
            requires_review BOOLEAN NOT NULL
        )
        """,
        "alters": (
            "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE osint_sources ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_osint_sources_case_id ON osint_sources (case_id)",
        ),
    },
    "osint_summaries": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS osint_summaries (
            summary_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL,
            source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT NOT NULL,
            key_points JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_references JSONB NOT NULL DEFAULT '[]'::jsonb,
            operator_review_caveat TEXT NOT NULL,
            limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            created_by TEXT NOT NULL,
            owner_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE osint_summaries ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE osint_summaries ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE osint_summaries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE osint_summaries ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_osint_summaries_case_id ON osint_summaries (case_id)",
        ),
    },
    "osint_audit": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS osint_audit (
            enrichment_audit_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NOT NULL,
            source_id TEXT NULL,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE osint_audit ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE osint_audit ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE osint_audit ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_osint_audit_case_id ON osint_audit (case_id)",
        ),
    },
    "identity_enrollments": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS identity_enrollments (
            enrollment_id TEXT PRIMARY KEY,
            id TEXT NULL,
            identity_id TEXT NOT NULL,
            image_ref TEXT NULL,
            embedding_vector_ref TEXT NULL,
            quality_score DOUBLE PRECISION NULL,
            status TEXT NOT NULL,
            rejection_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
            quality_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
            batch_enrollment_id TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL
        )
        """,
        "alters": (
            "ALTER TABLE identity_enrollments ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE identity_enrollments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE identity_enrollments ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_identity_enrollments_identity_id ON identity_enrollments (identity_id)",
        ),
    },
    "identity_observations": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS identity_observations (
            observation_id TEXT PRIMARY KEY,
            id TEXT NULL,
            global_identity_id TEXT NOT NULL,
            source_track_id TEXT NULL,
            source_camera_id TEXT NULL,
            source_type TEXT NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            face_score DOUBLE PRECISION NULL,
            reid_score DOUBLE PRECISION NULL,
            track_score DOUBLE PRECISION NULL,
            source_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL
        )
        """,
        "alters": (
            "ALTER TABLE identity_observations ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE identity_observations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE identity_observations ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_identity_observations_global_identity_id ON identity_observations (global_identity_id)",
            "CREATE INDEX IF NOT EXISTS idx_identity_observations_observed_at ON identity_observations (observed_at DESC)",
        ),
    },
    "global_identity_links": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS global_identity_links (
            global_identity_id TEXT PRIMARY KEY,
            id TEXT NULL,
            status TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            first_seen TIMESTAMPTZ NOT NULL,
            last_seen TIMESTAMPTZ NOT NULL,
            last_source_id TEXT NULL,
            last_camera_id TEXT NULL,
            observation_count BIGINT NOT NULL DEFAULT 0,
            confidence_history JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
            camera_observations JSONB NOT NULL DEFAULT '{}'::jsonb,
            cameras_seen JSONB NOT NULL DEFAULT '[]'::jsonb,
            ttl_expires_at TIMESTAMPTZ NULL,
            decay_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            operator_review_status TEXT NULL,
            linked_case_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """,
        "alters": (
            "ALTER TABLE global_identity_links ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE global_identity_links ADD COLUMN IF NOT EXISTS operator_review_status TEXT NULL",
            "ALTER TABLE global_identity_links ADD COLUMN IF NOT EXISTS linked_case_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE global_identity_links ADD COLUMN IF NOT EXISTS decay_metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE global_identity_links ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_global_identity_links_status ON global_identity_links (status)",
            "CREATE INDEX IF NOT EXISTS idx_global_identity_links_last_seen ON global_identity_links (last_seen DESC)",
        ),
    },
    "watchlists": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS watchlists (
            watchlist_id TEXT PRIMARY KEY,
            id TEXT NULL,
            identity_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            reason TEXT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            expires_at TIMESTAMPTZ NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_watchlists_identity_id ON watchlists (identity_id)",
        ),
    },
    "open_vocab_results": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS open_vocab_results (
            scan_id TEXT PRIMARY KEY,
            id TEXT NULL,
            camera_id TEXT NULL,
            incident_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            risk_score DOUBLE PRECISION NULL,
            detections JSONB NOT NULL DEFAULT '[]'::jsonb,
            prompts JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS risk_score DOUBLE PRECISION NULL",
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS detections JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS prompts JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE open_vocab_results ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_open_vocab_results_camera_id ON open_vocab_results (camera_id)",
            "CREATE INDEX IF NOT EXISTS idx_open_vocab_results_created_at ON open_vocab_results (created_at DESC)",
        ),
    },
    "stream_replay_metadata": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS stream_replay_metadata (
            clip_id TEXT PRIMARY KEY,
            id TEXT NULL,
            camera_id TEXT NOT NULL,
            source_uri TEXT NULL,
            file_path TEXT NULL,
            metadata_path TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            clip_start_at TIMESTAMPTZ NULL,
            clip_end_at TIMESTAMPTZ NULL,
            size_bytes BIGINT NULL,
            hash_sha256 TEXT NULL,
            integrity_status TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE stream_replay_metadata ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE stream_replay_metadata ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE stream_replay_metadata ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_stream_replay_metadata_camera_id ON stream_replay_metadata (camera_id)",
        ),
    },
    "system_audit_logs": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS system_audit_logs (
            audit_id TEXT PRIMARY KEY,
            id TEXT NULL,
            timestamp DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            user_id TEXT NULL,
            username TEXT NULL,
            role TEXT NULL,
            action TEXT NOT NULL,
            resource_type TEXT NULL,
            resource_id TEXT NULL,
            ip_address TEXT NULL,
            user_agent TEXT NULL,
            success BOOLEAN NOT NULL,
            detail TEXT NULL,
            previous_hash TEXT NULL,
            entry_hash TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "alters": (
            "ALTER TABLE system_audit_logs ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE system_audit_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE system_audit_logs ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_system_audit_logs_created_at ON system_audit_logs (created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_system_audit_logs_action ON system_audit_logs (action)",
        ),
    },
    "retention_actions": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS retention_actions (
            action_id TEXT PRIMARY KEY,
            id TEXT NULL,
            case_id TEXT NULL,
            evidence_id TEXT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            requested_by TEXT NULL,
            reviewed_by TEXT NULL,
            review_required BOOLEAN NOT NULL DEFAULT TRUE,
            storage_uri TEXT NULL,
            hash_sha256 TEXT NULL,
            before_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL,
            action_completed_at TIMESTAMPTZ NULL
        )
        """,
        "alters": (
            "ALTER TABLE retention_actions ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE retention_actions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE retention_actions ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_retention_actions_case_id ON retention_actions (case_id)",
            "CREATE INDEX IF NOT EXISTS idx_retention_actions_evidence_id ON retention_actions (evidence_id)",
        ),
    },
    "model_registry_entries": {
        "ddl": """
        CREATE TABLE IF NOT EXISTS model_registry_entries (
            entry_id TEXT PRIMARY KEY,
            id TEXT NULL,
            model_key TEXT NOT NULL,
            model_name TEXT NULL,
            version TEXT NULL,
            path TEXT NULL,
            owner_id TEXT NULL,
            hash_sha256 TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NULL
        )
        """,
        "alters": (
            "ALTER TABLE model_registry_entries ADD COLUMN IF NOT EXISTS id TEXT NULL",
            "ALTER TABLE model_registry_entries ADD COLUMN IF NOT EXISTS owner_id TEXT NULL",
            "ALTER TABLE model_registry_entries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL",
            "ALTER TABLE model_registry_entries ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        ),
        "indexes": (
            "CREATE INDEX IF NOT EXISTS idx_model_registry_entries_model_key ON model_registry_entries (model_key)",
        ),
    },
}

COMPATIBILITY_STATEMENTS: tuple[str, ...] = (
    """
    CREATE OR REPLACE VIEW case_audit AS
    SELECT
        audit_id,
        case_id,
        action,
        actor,
        created_at AS timestamp,
        detail,
        metadata
    FROM case_audit_logs
    """,
)

REQUIRED_TABLES: tuple[str, ...] = (
    "events",
    "cases",
    "case_evidence",
    "case_notes",
    "case_audit_logs",
    "case_reports",
    "osint_sources",
    "osint_summaries",
    "identity_enrollments",
    "identity_observations",
    "global_identity_links",
    "watchlists",
    "open_vocab_results",
    "stream_replay_metadata",
    "system_audit_logs",
    "retention_actions",
    "model_registry_entries",
)

