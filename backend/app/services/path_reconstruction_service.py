from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.investigation_models import (
    InvestigationObservation,
    InvestigationSubjectRef,
    PathConfidenceBreakdown,
    PathHypothesis,
    PathHypothesisStep,
    PathReconstructionRequest,
    PathReconstructionResponse,
)
from app.models.security_models import UserAccount
from app.repositories.gis_repository import GisRepository
from app.repositories.investigation_repository import (
    InvestigationRepository,
    new_hypothesis_id,
)
from app.services.camera_graph_service import (
    build_camera_graph,
    estimate_travel_seconds,
    get_edges_from,
)
from inference.config_runtime import load_runtime_config
from inference.metrics import metrics

SAFE_SUMMARY = "Possible movement path requiring operator review. This is an investigative hypothesis, not a confirmed fact."
INSUFFICIENT_DATA_MSG = (
    "Insufficient evidence to reconstruct a movement path. "
    "No observations with location data were found in the specified time window."
)

FORBIDDEN_PHRASES = (
    "criminal confirmed",
    "suspect confirmed",
    "identity confirmed",
    "attacker confirmed",
    "guilty",
    "confirmed criminal",
)


def _load_cfg() -> dict[str, Any]:
    return dict((load_runtime_config("investigation").get("investigation") or {}))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _score_time_consistency(
    observations: list[InvestigationObservation],
    edges_by_from: dict[str, list[Any]],
) -> float:
    if len(observations) < 2:
        return 0.5
    ok = 0
    total = len(observations) - 1
    for i in range(total):
        a = observations[i]
        b = observations[i + 1]
        ta = _parse_ts(a.timestamp)
        tb = _parse_ts(b.timestamp)
        if ta is None or tb is None:
            continue
        elapsed = (tb - ta).total_seconds()
        edges = edges_by_from.get(a.camera_id, [])
        edge = next((e for e in edges if e.to_camera_id == b.camera_id), None)
        if edge is None:
            if elapsed > 0:
                ok += 0.5
            continue
        min_feasible = edge.estimated_run_seconds
        max_feasible = edge.estimated_walk_seconds * 4
        if min_feasible <= elapsed <= max_feasible:
            ok += 1.0
        elif elapsed > 0:
            ok += 0.3
    return round(ok / max(total, 1), 4)


def _score_geo_distance(observations: list[InvestigationObservation]) -> float:
    scored = [o for o in observations if o.latitude is not None and o.longitude is not None]
    if len(scored) < 2:
        return 0.5
    return 0.7


def _safe_summary_check(text: str) -> str:
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            return SAFE_SUMMARY
    return text


def reconstruct_path(
    request: PathReconstructionRequest,
    gis_repo: GisRepository,
    investigation_repo: InvestigationRepository,
    user: UserAccount,
) -> PathReconstructionResponse:
    cfg = _load_cfg()
    pr_cfg = cfg.get("path_reconstruction") or {}
    max_candidates = min(int(request.max_candidates or 5), int(pr_cfg.get("max_candidate_paths", 10)))
    min_confidence = float(pr_cfg.get("min_confidence", 0.25))

    try:
        metrics.increment("investigation_path_requests_total")
    except Exception:
        pass

    request_id = f"req_{uuid.uuid4().hex[:12]}"

    if not request.case_id and not request.event_id:
        try:
            metrics.increment("investigation_no_evidence_total")
        except Exception:
            pass
        return PathReconstructionResponse(
            request_id=request_id,
            status="insufficient_data",
            message=INSUFFICIENT_DATA_MSG,
        )

    nodes, edges = build_camera_graph(gis_repo, user)
    if not nodes:
        try:
            metrics.increment("investigation_no_evidence_total")
        except Exception:
            pass
        return PathReconstructionResponse(
            request_id=request_id,
            status="insufficient_data",
            message="No camera profiles available for graph construction.",
        )

    edges_by_from: dict[str, list[Any]] = {}
    for e in edges:
        edges_by_from.setdefault(e.from_camera_id, []).append(e)

    node_map = {n.camera_id: n for n in nodes}

    now = _now_utc()
    backward_m = int(request.backward_minutes or pr_cfg.get("default_backward_minutes", 20))
    forward_m = int(request.forward_minutes or pr_cfg.get("default_forward_minutes", 30))
    t_start = now - timedelta(minutes=backward_m)
    t_end = now + timedelta(minutes=forward_m)

    observations = _collect_observations(
        request,
        gis_repo,
        user,
        t_start,
        t_end,
        node_map,
    )

    evidence_refs: list[str] = []
    for obs in observations:
        if obs.event_id:
            evidence_refs.append(f"event:{obs.event_id}")
        if obs.case_id:
            ref = f"case:{obs.case_id}"
            if ref not in evidence_refs:
                evidence_refs.append(ref)

    ev_cfg = cfg.get("evidence") or {}
    require_source_refs = bool(ev_cfg.get("require_source_refs", True))
    if require_source_refs and not evidence_refs:
        try:
            metrics.increment("investigation_no_evidence_total")
        except Exception:
            pass
        return PathReconstructionResponse(
            request_id=request_id,
            status="insufficient_data",
            message=INSUFFICIENT_DATA_MSG,
        )

    if not observations:
        try:
            metrics.increment("investigation_no_evidence_total")
        except Exception:
            pass
        return PathReconstructionResponse(
            request_id=request_id,
            status="insufficient_data",
            message=INSUFFICIENT_DATA_MSG,
        )

    hypotheses = _generate_hypotheses(
        observations=observations,
        edges_by_from=edges_by_from,
        node_map=node_map,
        request=request,
        evidence_refs=evidence_refs,
        max_candidates=max_candidates,
        min_confidence=min_confidence,
    )

    for hyp in hypotheses:
        investigation_repo.save_hypothesis(hyp)

    try:
        metrics.increment("investigation_hypotheses_generated_total", len(hypotheses))
    except Exception:
        pass

    return PathReconstructionResponse(
        request_id=request_id,
        status="ok",
        hypotheses=hypotheses,
        evidence_ref_count=len(evidence_refs),
        message=f"Generated {len(hypotheses)} candidate path hypothesis(es). Operator review required.",
        operator_review_required=True,
    )


def _collect_observations(
    request: PathReconstructionRequest,
    gis_repo: GisRepository,
    user: UserAccount,
    t_start: datetime,
    t_end: datetime,
    node_map: dict[str, Any],
) -> list[InvestigationObservation]:
    observations: list[InvestigationObservation] = []
    camera_ids = set(request.camera_ids or []) or set(node_map.keys())

    event_markers = gis_repo.get_event_markers(
        user=user,
        start_time=t_start.isoformat(),
        end_time=t_end.isoformat(),
        severity=None,
        event_type=None,
        camera_id=None,
        case_id=request.case_id,
        source_type=None,
    )
    import uuid as _uuid

    for marker in event_markers:
        cam_id = marker.camera_id or ""
        if cam_id and cam_id not in camera_ids:
            continue
        obs = InvestigationObservation(
            observation_id=f"obs_{_uuid.uuid4().hex[:8]}",
            camera_id=cam_id or "unknown",
            timestamp=marker.timestamp,
            event_id=marker.event_id,
            case_id=marker.case_id or request.case_id,
            latitude=marker.latitude,
            longitude=marker.longitude,
            altitude_meters=getattr(marker, "altitude_meters", None),
            confidence=float(marker.risk_score or 0.5),
            source_type=marker.source_type,
            safe_label=getattr(marker, "title", None),
            metadata={
                "source_type": marker.source_type,
                "safe_label": getattr(marker, "title", None),
            },
        )
        observations.append(obs)

    observations.sort(key=lambda o: o.timestamp)
    return observations


def _generate_hypotheses(
    observations: list[InvestigationObservation],
    edges_by_from: dict[str, list[Any]],
    node_map: dict[str, Any],
    request: PathReconstructionRequest,
    evidence_refs: list[str],
    max_candidates: int,
    min_confidence: float,
) -> list[PathHypothesis]:
    if not observations:
        return []

    subject_ref = request.subject_ref or InvestigationSubjectRef(
        type="manual",
        ref_id=request.event_id or request.case_id or "unknown",
        display_label="Possible subject",
    )

    steps: list[PathHypothesisStep] = []
    for idx, obs in enumerate(observations):
        node = node_map.get(obs.camera_id)
        lat = obs.latitude or (node.latitude if node else None)
        lon = obs.longitude or (node.longitude if node else None)
        step_type = "fixed_camera"
        if obs.source_type == "drone_simulation":
            step_type = "drone_observation"
        elif obs.source_type == "uploaded_video":
            step_type = "uploaded_video"

        travel_s: float | None = None
        low_conf_transition = False
        if idx > 0:
            prev_obs = observations[idx - 1]
            edges = edges_by_from.get(prev_obs.camera_id, [])
            edge = next((e for e in edges if e.to_camera_id == obs.camera_id), None)
            if edge:
                travel_s = estimate_travel_seconds(edge, "walk")
            else:
                low_conf_transition = True

        steps.append(
            PathHypothesisStep(
                step_index=idx,
                step_type=step_type,  # type: ignore[arg-type]
                source_id=obs.camera_id,
                source_type=obs.source_type,
                camera_id=obs.camera_id,
                camera_name=node.name if node else obs.camera_id,
                latitude=lat,
                longitude=lon,
                altitude_meters=obs.altitude_meters,
                timestamp=obs.timestamp,
                event_id=obs.event_id,
                observation_id=obs.observation_id,
                step_confidence=obs.confidence,
                travel_mode="unknown" if step_type != "fixed_camera" else "walk",
                travel_seconds_from_prev=travel_s,
                low_confidence_transition=low_conf_transition,
                safe_label=(
                    "Simulated aerial observation"
                    if step_type == "drone_observation"
                    else (obs.safe_label or None)
                ),
                evidence_refs=[f"event:{obs.event_id}"] if obs.event_id else [],
            )
        )

    time_score = _score_time_consistency(observations, edges_by_from)
    geo_score = _score_geo_distance(observations)
    overall = round((time_score * 0.4 + geo_score * 0.3 + 0.5 * 0.3), 4)

    if overall < min_confidence:
        return []

    hyp = PathHypothesis(
        hypothesis_id=new_hypothesis_id(),
        case_id=request.case_id,
        subject_ref=subject_ref,
        start_event_id=request.event_id,
        steps=steps,
        confidence=overall,
        confidence_breakdown=PathConfidenceBreakdown(
            time_consistency=time_score,
            geo_distance=geo_score,
            travel_feasibility=0.5,
        ),
        review_status="pending",
        operator_review_required=True,
        safe_summary=SAFE_SUMMARY,
        created_at=_now_utc().isoformat(),
        evidence_refs=evidence_refs,
    )

    return [hyp][:max_candidates]
