"""Phase 9/10 — Exhibition Demo Controller Service.

Phase 10 enhancements:
- Part B: session recovery from persisted JSON on startup
- Part D: auto-run duplicate prevention lock
- Part E: fallback/dry-run replay mode from deterministic scenario definition
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEMO_STATE_DIR = _PROJECT_ROOT / "runtime_state" / "exhibition_demo"
_SESSION_FILE = _DEMO_STATE_DIR / "demo_session.json"

DEMO_SCENARIO_ID = "bank_robbery_demo"
DEMO_DRONE_ID = "DRONE-ALPHA"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Demo session model
# ---------------------------------------------------------------------------

class ExhibitionDemoSession:
    """Mutable demo session."""

    VALID_STATUSES = {
        "not_started", "preflight_required", "ready",
        "running", "completed", "failed", "cancelled", "stale",
    }

    def __init__(self) -> None:
        self.demo_id: str = str(uuid.uuid4())
        self.status: str = "not_started"
        self.scenario_run_id: str | None = None
        self.current_step: int = 0
        self.total_steps: int = 0
        self.preflight_status: str | None = None
        self.active_alert_ids: list[str] = []
        self.active_incident_ids: list[str] = []
        self.assigned_drone_ids: list[str] = []
        self.tracking_ready: bool = False
        self.command_center_ready: bool = False
        self.started_at: str | None = None
        self.completed_at: str | None = None
        self.last_error: str | None = None
        self.metadata: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "demo_id": self.demo_id,
            "status": self.status,
            "scenario_run_id": self.scenario_run_id,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "preflight_status": self.preflight_status,
            "active_alert_ids": list(self.active_alert_ids),
            "active_incident_ids": list(self.active_incident_ids),
            "assigned_drone_ids": list(self.assigned_drone_ids),
            "tracking_ready": self.tracking_ready,
            "command_center_ready": self.command_center_ready,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "last_error": self.last_error,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExhibitionDemoSession":
        s = cls()
        s.demo_id = data.get("demo_id") or str(uuid.uuid4())
        raw_status = data.get("status", "not_started")
        s.status = raw_status if raw_status in cls.VALID_STATUSES else "stale"
        s.scenario_run_id = data.get("scenario_run_id")
        s.current_step = int(data.get("current_step", 0))
        s.total_steps = int(data.get("total_steps", 0))
        s.preflight_status = data.get("preflight_status")
        s.active_alert_ids = list(data.get("active_alert_ids") or [])
        s.active_incident_ids = list(data.get("active_incident_ids") or [])
        s.assigned_drone_ids = list(data.get("assigned_drone_ids") or [])
        s.tracking_ready = bool(data.get("tracking_ready", False))
        s.command_center_ready = bool(data.get("command_center_ready", False))
        s.started_at = data.get("started_at")
        s.completed_at = data.get("completed_at")
        s.last_error = data.get("last_error")
        s.metadata = dict(data.get("metadata") or {})
        return s


# ---------------------------------------------------------------------------
# Runbook definition
# ---------------------------------------------------------------------------

DEMO_RUNBOOK_STEPS = [
    {
        "step": 1, "title": "System Startup", "phase": "setup",
        "description": "Backend and frontend are running. Admin/operator is logged in.",
        "operator_note": "Confirm both services are healthy at /api/health.",
    },
    {
        "step": 2, "title": "Exhibition Preflight", "phase": "setup",
        "description": "Run preflight to verify all core capabilities are ready.",
        "operator_note": "Click 'Run Preflight' in the Exhibition Demo Panel. Resolve any blocking failures.",
    },
    {
        "step": 3, "title": "Start Bank Robbery Demo", "phase": "demo_start",
        "description": "Click 'Start Demo' to initialise the scenario run.",
        "operator_note": "Choose step mode for controlled exhibition or auto-run for timed demo.",
    },
    {
        "step": 4, "title": "Step 1 — Routine Surveillance", "phase": "scenario",
        "description": "Normal CCTV surveillance. Suspicious individual enters Financial District (CAM-BANK-01).",
        "operator_note": "Narrate: 'Our city-wide CCTV network covers 16 cameras across 10 zones.'",
    },
    {
        "step": 5, "title": "Step 2 — Suspicious Behaviour", "phase": "scenario",
        "description": "Suspect loiters near bank entrance. Behaviour flagged (medium severity).",
        "operator_note": "Point to alert severity badge. Show camera network panel.",
    },
    {
        "step": 6, "title": "Step 3 — Civilian Group Observed", "phase": "scenario",
        "description": "Civilian group of 5 observed entering bank (CAM-BANK-02).",
        "operator_note": "Narrate: 'All actors are tracked. Civilians are differentiated from suspects.'",
    },
    {
        "step": 7, "title": "Step 4 — CRITICAL: Weapon Detected", "phase": "critical_event",
        "description": "Armed suspect displays weapon. CRITICAL alert created. Incident opened. DRONE-ALPHA dispatched.",
        "operator_note": "PAUSE HERE. Show alert. Show incident. Show drone dispatch status.",
    },
    {
        "step": 8, "title": "Step 5 — Security Response", "phase": "scenario",
        "description": "Bank lockdown initiated. Security guard responding (CAM-BANK-02).",
        "operator_note": "Show multi-actor tracking.",
    },
    {
        "step": 9, "title": "Step 6 — DRONE-ALPHA Airborne", "phase": "drone_response",
        "description": "DRONE-ALPHA dispatched and conducting aerial surveillance of Financial District.",
        "operator_note": "Show drone route panel. Narrate: 'Drone dispatched automatically on weapon detection.'",
    },
    {
        "step": 10, "title": "Step 7 — Suspect Escape: Parking Lot", "phase": "escape_sequence",
        "description": "Suspect moving north toward parking lot (CAM-PARKING-01).",
        "operator_note": "Show suspect path map. Camera handoff chain is now active.",
    },
    {
        "step": 11, "title": "Step 8 — Escape Vehicle Detected", "phase": "escape_sequence",
        "description": "Escape vehicle detected in restricted parking zone (CAM-PARKING-01).",
        "operator_note": "Point to vehicle actor in tracking view.",
    },
    {
        "step": 12, "title": "Step 9 — Suspect in Alley", "phase": "escape_sequence",
        "description": "Suspect exits via alley. DRONE-ALPHA maintaining tracking (CAM-ALLEY-01).",
        "operator_note": "Show fused track — drone + CCTV combined path.",
    },
    {
        "step": 13, "title": "Step 10 — DRONE-ALPHA Aerial Confirmation", "phase": "drone_response",
        "description": "Drone confirms suspect in alley sector.",
        "operator_note": "Show drone route waypoints alongside suspect path.",
    },
    {
        "step": 14, "title": "Step 11 — Road Checkpoint", "phase": "escape_sequence",
        "description": "Suspect approaching road checkpoint. Intercept recommended.",
        "operator_note": "Show operational tracking panel and suggest intercept point.",
    },
    {
        "step": 15, "title": "Step 12 — Scenario Complete", "phase": "summary",
        "description": "Full observation timeline captured. Bank robbery incident closed.",
        "operator_note": "Show report/evidence summary. Analytics updated. Show incident count.",
    },
    {
        "step": 16, "title": "Evidence & Report Review", "phase": "evidence",
        "description": "Review scenario-generated alert/incident IDs, camera chain, drone route, and analytics.",
        "operator_note": "Navigate to Evidence/Report section. All data is simulated and clearly marked.",
    },
    {
        "step": 17, "title": "Optional: Uploaded-Video Analysis", "phase": "optional",
        "description": "Run uploaded-video intelligence workflow to show ML-based analysis.",
        "operator_note": "Navigate to Uploaded Video Analysis page. Upload any short video clip.",
    },
    {
        "step": 18, "title": "Demo Reset", "phase": "cleanup",
        "description": "Click Reset Demo to clear state and prepare for the next run.",
        "operator_note": "Demo can be re-run immediately after reset.",
    },
]


# ---------------------------------------------------------------------------
# Deterministic fallback snapshot (Part E)
# ---------------------------------------------------------------------------

def _build_fallback_snapshot() -> dict[str, Any]:
    """Return a deterministic snapshot from the scenario definition.
    Does NOT start a live run. Used when scenario engine fails.
    """
    from app.services.scenario_engine_service import (
        BANK_ROBBERY_DEMO,
        BANK_ROBBERY_SUSPECT_PATH,
        BANK_ROBBERY_CAMERA_HANDOFFS,
        DRONE_ALPHA_ROUTE_WAYPOINTS,
    )

    timeline_summary = [
        {
            "step": ev.step,
            "event_type": ev.event_type,
            "description": ev.description,
            "camera_id": ev.camera_id,
            "severity": ev.severity,
            "drone_id": ev.drone_id,
        }
        for ev in BANK_ROBBERY_DEMO.timeline
    ]

    cameras = list(BANK_ROBBERY_DEMO.camera_ids)
    actors = [
        {"actor_id": a.actor_id, "name": a.name, "role": a.role.value}
        for a in BANK_ROBBERY_DEMO.actors
    ]

    suspect_path_preview = [
        {
            "waypoint_id": w["waypoint_id"],
            "zone_id": w["zone_id"],
            "zone_name": w["zone_name"],
            "offset_seconds": w["offset_seconds"],
            "source_id": w.get("source_id"),
        }
        for w in BANK_ROBBERY_SUSPECT_PATH
    ]

    handoff_preview = [
        {
            "handoff_id": h["handoff_id"],
            "from_camera_id": h["from_camera_id"],
            "to_camera_id": h["to_camera_id"],
        }
        for h in BANK_ROBBERY_CAMERA_HANDOFFS
    ]

    drone_waypoints_preview = [
        {
            "waypoint_id": w["waypoint_id"],
            "zone_name": w["zone_name"],
            "offset_seconds": w["offset_seconds"],
        }
        for w in DRONE_ALPHA_ROUTE_WAYPOINTS
    ]

    return {
        "fallback": True,
        "fallback_label": "Demo Replay Mode — deterministic fallback, not a live scenario run",
        "scenario_id": DEMO_SCENARIO_ID,
        "scenario_name": BANK_ROBBERY_DEMO.name,
        "description": BANK_ROBBERY_DEMO.description,
        "cameras": cameras,
        "actors": actors,
        "total_steps": len(BANK_ROBBERY_DEMO.timeline),
        "timeline_summary": timeline_summary,
        "suspect_path_preview": suspect_path_preview,
        "camera_handoffs_preview": handoff_preview,
        "drone_route_preview": drone_waypoints_preview,
        "drone_assigned": DEMO_DRONE_ID,
        "simulated": True,
        "disclaimer": "This is a deterministic fallback view. No live scenario run is active.",
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ExhibitionDemoService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._autorun_lock = threading.Lock()  # Part D: prevent duplicate auto-run
        _DEMO_STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Part B: attempt to recover persisted session
        self._session: ExhibitionDemoSession = self._load_persisted_session()

    # ------------------------------------------------------------------
    # Part B: Persistent session recovery
    # ------------------------------------------------------------------

    def _load_persisted_session(self) -> ExhibitionDemoSession:
        """Load session from JSON file on startup. Mark stale if run_id is gone."""
        if not _SESSION_FILE.exists():
            s = ExhibitionDemoSession()
            return s

        try:
            data = json.loads(_SESSION_FILE.read_text(encoding="utf-8"))
            session = ExhibitionDemoSession.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to load persisted demo session: %s — starting fresh", exc)
            return ExhibitionDemoSession()

        # Validate: if session was "running", check whether the scenario run still exists
        if session.status == "running" and session.scenario_run_id:
            try:
                from app.services.scenario_engine_service import get_scenario_engine
                engine = get_scenario_engine()
                run = engine.active_run()
                if run is None or run.run_id != session.scenario_run_id:
                    logger.info(
                        "Persisted demo session %s references stale run %s — marking stale",
                        session.demo_id, session.scenario_run_id,
                    )
                    session.status = "stale"
                    session.last_error = (
                        f"Backend restarted. Previous run '{session.scenario_run_id}' is no longer active. "
                        "Click Reset to start a fresh demo."
                    )
            except Exception as exc:
                logger.warning("Cannot validate persisted run_id: %s — marking stale", exc)
                session.status = "stale"
                session.last_error = "Could not validate previous run after restart. Click Reset."

        logger.info(
            "Recovered demo session %s (status=%s) from persisted file",
            session.demo_id, session.status,
        )
        return session

    # ------------------------------------------------------------------
    # Session accessors
    # ------------------------------------------------------------------

    def get_session(self) -> ExhibitionDemoSession:
        with self._lock:
            return self._session

    def get_demo_status(self) -> dict[str, Any]:
        with self._lock:
            session = self._session
        self._sync_scenario_state(session)
        return session.to_dict()

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def reset_demo(self) -> dict[str, Any]:
        """Clear active demo state safely. Can reset stale sessions."""
        with self._lock:
            old_run_id = self._session.scenario_run_id

        if old_run_id:
            try:
                from app.services.scenario_engine_service import get_scenario_engine
                engine = get_scenario_engine()
                run = engine.active_run()
                if run and run.run_id == old_run_id:
                    engine.cancel()
            except Exception as exc:
                logger.warning("Scenario cancel during demo reset: %s", exc)

        with self._lock:
            self._session = ExhibitionDemoSession()
            self._session.status = "ready"
            self._session.preflight_status = "not_run"
        self._persist()
        return {"reset": True, "demo_id": self._session.demo_id, "status": "ok"}

    def start_demo(self, mode: str = "step", run_preflight: bool = False) -> dict[str, Any]:
        with self._lock:
            session = self._session
            if session.status in ("running",):
                raise RuntimeError("Demo is already running. Reset or cancel first.")

        if run_preflight:
            pf_result = self._run_preflight_check()
            with self._lock:
                self._session.preflight_status = pf_result.get("overall_status", "unknown")
            if pf_result.get("blocking_failures"):
                with self._lock:
                    self._session.status = "preflight_required"
                    self._session.last_error = "Preflight blocking failures: " + ", ".join(
                        pf_result["blocking_failures"][:3]
                    )
                return {"status": "preflight_required", "preflight": pf_result}

        # Start scenario — use fallback if engine fails
        try:
            from app.services.scenario_engine_service import get_scenario_engine
            engine = get_scenario_engine()
            try:
                run = engine.start(DEMO_SCENARIO_ID, mode=mode)
            except RuntimeError:
                # Already running — cancel and restart
                engine.cancel()
                run = engine.start(DEMO_SCENARIO_ID, mode=mode)
        except Exception as exc:
            with self._lock:
                self._session.status = "failed"
                self._session.last_error = str(exc)
            self._persist()
            raise RuntimeError(f"Could not start scenario: {exc}") from exc

        with self._lock:
            self._session.status = "running"
            self._session.scenario_run_id = run.run_id
            self._session.current_step = run.current_step
            self._session.total_steps = run.total_steps
            self._session.started_at = _now_iso()
            self._session.last_error = None
            self._session.metadata["mode"] = mode
            self._session.metadata["scenario_id"] = DEMO_SCENARIO_ID

        self._persist()
        return {"status": "running", "demo": self._session.to_dict()}

    def step_demo(self) -> dict[str, Any]:
        with self._lock:
            session = self._session
            if session.status != "running":
                raise RuntimeError(
                    f"Demo is not running (status={session.status}). Start demo first."
                )
            if not session.scenario_run_id:
                raise RuntimeError("No active scenario run. Start demo first.")

        try:
            from app.services.scenario_engine_service import get_scenario_engine
            engine = get_scenario_engine()
            result = engine.step()
        except RuntimeError as exc:
            with self._lock:
                self._session.last_error = str(exc)
            raise

        self._sync_scenario_state(self._session)
        self._persist()
        return {
            "status": "ok",
            "step_result": result,
            "demo": self._session.to_dict(),
        }

    def auto_run_demo(self) -> dict[str, Any]:
        """Part D: Auto-run all remaining steps. Duplicate calls are blocked."""
        # Part D: Lock prevents two concurrent auto-run calls
        if not self._autorun_lock.acquire(blocking=False):
            raise RuntimeError("Auto-run is already in progress. Wait for it to complete.")

        try:
            with self._lock:
                session = self._session
                if session.status not in ("running",):
                    raise RuntimeError(
                        f"Demo must be running to auto-run. Status={session.status}"
                    )

            try:
                from app.services.scenario_engine_service import get_scenario_engine
                engine = get_scenario_engine()
                run = engine.active_run()
                if run is None:
                    raise RuntimeError("No active scenario run.")

                # Step until complete (synchronous — 12 steps, typically <1s)
                max_steps = 20  # safety ceiling
                steps_taken = 0
                while steps_taken < max_steps:
                    try:
                        result = engine.step()
                        steps_taken += 1
                        if result.get("status") == "completed":
                            break
                        run_status = result.get("run_status", {})
                        if run_status.get("state") in ("completed", "cancelled"):
                            break
                    except RuntimeError:
                        break

            except Exception as exc:
                with self._lock:
                    self._session.last_error = str(exc)
                logger.warning("Auto-run error: %s", exc)

            self._sync_scenario_state(self._session)
            self._persist()
            return {"status": "ok", "demo": self._session.to_dict()}

        finally:
            self._autorun_lock.release()

    def cancel_demo(self) -> dict[str, Any]:
        with self._lock:
            session = self._session
            run_id = session.scenario_run_id

        if run_id:
            try:
                from app.services.scenario_engine_service import get_scenario_engine
                engine = get_scenario_engine()
                run = engine.active_run()
                if run and run.run_id == run_id:
                    engine.cancel()
            except Exception as exc:
                logger.warning("Scenario cancel error: %s", exc)

        with self._lock:
            self._session.status = "cancelled"
        self._persist()
        return {"status": "cancelled", "demo": self._session.to_dict()}

    def complete_demo(self) -> dict[str, Any]:
        with self._lock:
            self._session.status = "completed"
            self._session.completed_at = _now_iso()
        self._persist()
        return {"status": "completed", "demo": self._session.to_dict()}

    # ------------------------------------------------------------------
    # Part E: Fallback / dry-run replay
    # ------------------------------------------------------------------

    def get_fallback_snapshot(self) -> dict[str, Any]:
        """Return deterministic snapshot without requiring a live scenario run.

        This is the exhibition safety net: if the scenario engine is broken,
        this lets the operator show the full story from the scenario definition.
        """
        try:
            fallback = _build_fallback_snapshot()
        except Exception as exc:
            logger.warning("Fallback snapshot build error: %s", exc)
            fallback = {
                "fallback": True,
                "fallback_label": "Demo Replay Mode — deterministic fallback",
                "scenario_id": DEMO_SCENARIO_ID,
                "error": str(exc),
                "simulated": True,
            }

        with self._lock:
            session_dict = self._session.to_dict()

        return {
            "demo_session": session_dict,
            "fallback_data": fallback,
            "analytics_summary": self._safe_analytics_summary(),
            "ui_links": {
                "tracking_panel": "/#operational-tracking",
                "alerts_page": "/alerts",
                "incidents_page": "/incidents",
                "analytics_page": "/analytics",
                "uploaded_video_page": "/uploaded-video-analysis",
            },
            "status": "ok",
        }

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_demo_snapshot(self) -> dict[str, Any]:
        """Return the combined operator-facing demo state snapshot."""
        with self._lock:
            session = self._session

        self._sync_scenario_state(session)

        run_id = session.scenario_run_id
        scenario_run: dict[str, Any] | None = None
        active_event: dict[str, Any] | None = None
        observations: list[dict[str, Any]] = []
        camera_observations: list[dict[str, Any]] = []
        promotions: list[dict[str, Any]] = []
        drone_state: dict[str, Any] | None = None
        suspect_path: list[dict[str, Any]] = []
        camera_handoffs: list[dict[str, Any]] = []
        drone_route: dict[str, Any] | None = None
        fused_track: dict[str, Any] | None = None
        report_links: dict[str, Any] = {}

        if run_id:
            try:
                from app.services.scenario_engine_service import get_scenario_engine
                engine = get_scenario_engine()

                run = engine.active_run()
                if run and run.run_id == run_id:
                    scenario_run = run.to_status().model_dump(mode="json")
                    obs = engine.run_observation_timeline()
                    observations = obs[-5:] if obs else []
                    if obs:
                        active_event = obs[-1].get("observation") or obs[-1]
                        camera_observations = [
                            o.get("observation", o)
                            for o in obs
                            if (o.get("observation") or {}).get("source_type") != "drone_camera"
                        ][-5:]

                promotions = engine.list_promotions(run_id)
                sp = engine.get_suspect_path(run_id)
                suspect_path = [w.model_dump(mode="json") for w in sp]
                ch = engine.get_camera_handoffs(run_id)
                camera_handoffs = [h.model_dump(mode="json") for h in ch]
                dr = engine.get_drone_route(run_id)
                if dr:
                    drone_route = dr.model_dump(mode="json")
                ft = engine.get_fused_track(run_id)
                if ft:
                    fused_track = ft.model_dump(mode="json")

            except Exception as exc:
                logger.warning("Snapshot scenario fetch error: %s", exc)

            try:
                from app.services.drone_operational_state_service import get_drone_operational_state_service
                svc = get_drone_operational_state_service()
                drone_fleet = svc.get_fleet_state()
                for d in drone_fleet.drones:
                    if d.drone_id == DEMO_DRONE_ID:
                        drone_state = d.model_dump(mode="json")
                        break
            except Exception as exc:
                logger.warning("Snapshot drone state error: %s", exc)

        analytics_summary = self._safe_analytics_summary()

        if run_id and promotions:
            report_links = self._build_report_links(run_id, session, promotions)

        with self._lock:
            session_dict = session.to_dict()

        return {
            "demo_session": session_dict,
            "scenario_run": scenario_run,
            "active_event": active_event,
            "recent_observations": observations,
            "camera_observations": camera_observations,
            "promotions": promotions,
            "drone_state": drone_state,
            "suspect_path": suspect_path,
            "camera_handoffs": camera_handoffs,
            "drone_route": drone_route,
            "fused_track": fused_track,
            "analytics_summary": analytics_summary,
            "report_links": report_links,
            "ui_links": {
                "tracking_panel": "/#operational-tracking",
                "alerts_page": "/alerts",
                "incidents_page": "/incidents",
                "analytics_page": "/analytics",
                "uploaded_video_page": "/uploaded-video-analysis",
                "scenario_tracking": f"/#scenario-tracking/{run_id}" if run_id else None,
            },
        }

    # ------------------------------------------------------------------
    # Runbook
    # ------------------------------------------------------------------

    def get_runbook(self) -> dict[str, Any]:
        return {
            "title": "Bank Robbery Demo — Operator Runbook",
            "scenario_id": DEMO_SCENARIO_ID,
            "total_steps": len(DEMO_RUNBOOK_STEPS),
            "steps": DEMO_RUNBOOK_STEPS,
            "startup_commands": {
                "backend": ".venv\\Scripts\\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000",
                "frontend": "cd frontend && npm run dev",
            },
            "admin_credentials": {
                "note": "Default admin credentials are configured in auth.yaml. See dev-guidelines.md."
            },
            "troubleshooting": [
                "If preflight fails: check /api/health and /api/preflight/summary",
                "If scenario is stuck: use Reset Demo button then Start Demo again",
                "If drone state missing: AirSim not required — drone state uses simulation registry",
                "If alerts missing: check promotions in runtime_state/scenario_promotions/",
                "If frontend 401: token expired — re-login as admin/operator",
                "If demo shows 'stale': backend restarted — click Reset to start fresh",
                "If scenario engine fails: use Fallback Replay to show demo without live run",
            ],
            "known_limitations": [
                "Drone video feed is simulated (no live AirSim required)",
                "ML detection is not active during scenario (uses deterministic events)",
                "LLM/OSINT disabled unless OPENAI_API_KEY configured",
                "Uploaded-video ML inference requires model files to be present",
                "Auto-run executes synchronously — takes ~1 second for 12 steps",
            ],
            "reset_instructions": (
                "Click 'Reset Demo' in the Exhibition Demo Panel, or POST /api/exhibition-demo/reset"
            ),
            "fallback_instructions": (
                "If scenario engine fails: click 'Fallback Replay' or GET /api/exhibition-demo/fallback"
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_analytics_summary(self) -> dict[str, Any]:
        try:
            from app.services.analytics_service import get_analytics_service
            svc = get_analytics_service()
            counters = svc.get_counters()
            return {
                "total_alerts": counters.get("total_alerts", 0),
                "total_incidents": counters.get("total_incidents", 0),
                "critical_alerts": counters.get("critical_alerts", 0),
                "high_alerts": counters.get("high_alerts", 0),
            }
        except Exception:
            return {"total_alerts": 0, "total_incidents": 0, "critical_alerts": 0, "high_alerts": 0}

    def _sync_scenario_state(self, session: ExhibitionDemoSession) -> None:
        if not session.scenario_run_id:
            return
        try:
            from app.services.scenario_engine_service import get_scenario_engine
            engine = get_scenario_engine()
            run = engine.active_run()
            if run and run.run_id == session.scenario_run_id:
                with self._lock:
                    session.current_step = run.current_step
                    session.total_steps = run.total_steps
                    if run.state.value == "completed":
                        session.status = "completed"
                        session.completed_at = run.completed_at or _now_iso()
                    elif run.state.value == "cancelled":
                        session.status = "cancelled"

                promotions = engine.list_promotions(run.run_id)
                alert_ids = [p["alert"]["alert_id"] for p in promotions if p.get("alert")]
                incident_ids = [p["incident"]["incident_id"] for p in promotions if p.get("incident")]
                with self._lock:
                    session.active_alert_ids = alert_ids
                    session.active_incident_ids = incident_ids

                drone_route = engine.get_drone_route(run.run_id)
                if drone_route:
                    with self._lock:
                        if DEMO_DRONE_ID not in session.assigned_drone_ids:
                            session.assigned_drone_ids = [DEMO_DRONE_ID]
                    session.tracking_ready = True

                session.command_center_ready = len(alert_ids) > 0

        except Exception as exc:
            logger.debug("Scenario sync error: %s", exc)

    def _run_preflight_check(self) -> dict[str, Any]:
        try:
            from app.core.preflight import get_preflight_service, PreflightMode
            svc = get_preflight_service()
            run = svc.start_preflight(mode=PreflightMode.EXHIBITION)
            return {
                "overall_status": run.overall_status.value,
                "blocking_failures": run.blocking_failures,
                "warnings": run.warnings,
            }
        except Exception as exc:
            logger.warning("Preflight check error: %s", exc)
            return {"overall_status": "error", "blocking_failures": [str(exc)], "warnings": []}

    def _build_report_links(
        self,
        run_id: str,
        session: ExhibitionDemoSession,
        promotions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        alert_ids = [p["alert"]["alert_id"] for p in promotions if p.get("alert")]
        incident_ids = [p["incident"]["incident_id"] for p in promotions if p.get("incident")]
        return {
            "scenario_id": DEMO_SCENARIO_ID,
            "run_id": run_id,
            "simulated": True,
            "source_cameras": [
                "CAM-BANK-01", "CAM-BANK-02", "CAM-BANK-03",
                "CAM-ROAD-01", "CAM-MARKET-01",
                "CAM-PARKING-01", "CAM-GATE-01", "CAM-ALLEY-01",
            ],
            "suspect_actor": "SUSPECT-001",
            "drone_assigned": DEMO_DRONE_ID,
            "alert_ids": alert_ids,
            "incident_ids": incident_ids,
            "timeline_steps": session.total_steps,
            "steps_completed": session.current_step,
            "analytics_page": "/analytics",
            "alerts_page": "/alerts",
            "incidents_page": "/incidents",
            "disclaimer": (
                "All data is simulated. This is a demonstration scenario, not real-world evidence."
            ),
        }

    def _persist(self) -> None:
        try:
            _DEMO_STATE_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = self._session.to_dict()
            _SESSION_FILE.write_text(json.dumps(data, default=str), encoding="utf-8")
        except Exception as exc:
            logger.debug("Demo session persist error: %s", exc)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service_lock = threading.Lock()
_exhibition_demo_service: ExhibitionDemoService | None = None


def get_exhibition_demo_service() -> ExhibitionDemoService:
    global _exhibition_demo_service
    if _exhibition_demo_service is None:
        with _service_lock:
            if _exhibition_demo_service is None:
                _exhibition_demo_service = ExhibitionDemoService()
    return _exhibition_demo_service
