from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.models.investigation_models import (
    HypothesisReviewRecord,
    HypothesisReviewRequest,
    InvestigationTimeline,
    InvestigationTimelineEntry,
    PathHypothesis,
    ReviewStatus,
)
from app.models.security_models import UserAccount

_STORAGE_ROOT = Path("storage/investigations")
_HYPOTHESES_FILE = _STORAGE_ROOT / "hypotheses.jsonl"
_REVIEWS_FILE = _STORAGE_ROOT / "reviews.jsonl"
_TIMELINES_FILE = _STORAGE_ROOT / "timelines.jsonl"

_lock = Lock()


def _ensure_storage() -> None:
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for f in [_HYPOTHESES_FILE, _REVIEWS_FILE, _TIMELINES_FILE]:
        if not f.exists():
            f.write_text("")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows),
        encoding="utf-8",
    )


class InvestigationRepository:
    def __init__(self) -> None:
        _ensure_storage()

    def save_hypothesis(self, hypothesis: PathHypothesis) -> PathHypothesis:
        with _lock:
            rows = _read_jsonl(_HYPOTHESES_FILE)
            data = hypothesis.model_dump(mode="json")
            if not data.get("created_at"):
                data["created_at"] = datetime.now(timezone.utc).isoformat()
            existing = [r for r in rows if r.get("hypothesis_id") != hypothesis.hypothesis_id]
            existing.append(data)
            _write_jsonl(_HYPOTHESES_FILE, existing)
        return PathHypothesis.model_validate(data)

    def get_hypothesis(self, hypothesis_id: str) -> PathHypothesis | None:
        for row in _read_jsonl(_HYPOTHESES_FILE):
            if row.get("hypothesis_id") == hypothesis_id:
                return PathHypothesis.model_validate(row)
        return None

    def list_hypotheses(
        self,
        case_id: str | None = None,
        subject_ref_id: str | None = None,
    ) -> list[PathHypothesis]:
        rows = _read_jsonl(_HYPOTHESES_FILE)
        result: list[PathHypothesis] = []
        for row in rows:
            if case_id and row.get("case_id") != case_id:
                continue
            if subject_ref_id:
                sr = row.get("subject_ref") or {}
                if sr.get("ref_id") != subject_ref_id:
                    continue
            try:
                result.append(PathHypothesis.model_validate(row))
            except Exception:
                pass
        return result

    def review_hypothesis(
        self,
        hypothesis_id: str,
        review_request: HypothesisReviewRequest,
        user: UserAccount,
    ) -> tuple[PathHypothesis | None, HypothesisReviewRecord | None]:
        with _lock:
            rows = _read_jsonl(_HYPOTHESES_FILE)
            updated: PathHypothesis | None = None
            new_rows: list[dict[str, Any]] = []
            for row in rows:
                if row.get("hypothesis_id") == hypothesis_id:
                    row["review_status"] = review_request.review_status
                    updated = PathHypothesis.model_validate(row)
                new_rows.append(row)
            if updated is None:
                return None, None
            _write_jsonl(_HYPOTHESES_FILE, new_rows)

            record = HypothesisReviewRecord(
                hypothesis_id=hypothesis_id,
                review_status=review_request.review_status,
                reviewed_by=user.username,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
                reviewer_notes=review_request.reviewer_notes,
            )
            review_rows = _read_jsonl(_REVIEWS_FILE)
            review_rows.append(record.model_dump(mode="json"))
            _write_jsonl(_REVIEWS_FILE, review_rows)
        return updated, record

    def save_timeline(self, timeline: InvestigationTimeline) -> InvestigationTimeline:
        with _lock:
            rows = _read_jsonl(_TIMELINES_FILE)
            data = timeline.model_dump(mode="json")
            existing = [r for r in rows if r.get("case_id") != timeline.case_id]
            existing.append(data)
            _write_jsonl(_TIMELINES_FILE, existing)
        return timeline

    def get_case_investigation_timeline(self, case_id: str) -> InvestigationTimeline | None:
        for row in _read_jsonl(_TIMELINES_FILE):
            if row.get("case_id") == case_id:
                try:
                    return InvestigationTimeline.model_validate(row)
                except Exception:
                    pass
        return None

    def build_case_timeline(self, case_id: str) -> InvestigationTimeline:
        hypotheses = self.list_hypotheses(case_id=case_id)
        entries: list[InvestigationTimelineEntry] = []
        accepted = rejected = inconclusive = pending = 0
        for hyp in hypotheses:
            if hyp.review_status == "accepted":
                accepted += 1
            elif hyp.review_status == "rejected":
                rejected += 1
            elif hyp.review_status == "inconclusive":
                inconclusive += 1
            else:
                pending += 1
            entries.append(
                InvestigationTimelineEntry(
                    entry_id=f"entry_{hyp.hypothesis_id}",
                    case_id=case_id,
                    hypothesis_id=hyp.hypothesis_id,
                    event_type="path_hypothesis",
                    summary=hyp.safe_summary,
                    timestamp=hyp.created_at or datetime.now(timezone.utc).isoformat(),
                    evidence_refs=hyp.evidence_refs,
                    operator_review_required=hyp.operator_review_required,
                )
            )
        timeline = InvestigationTimeline(
            case_id=case_id,
            entries=sorted(entries, key=lambda e: e.timestamp),
            total_hypotheses=len(hypotheses),
            accepted=accepted,
            rejected=rejected,
            inconclusive=inconclusive,
            pending=pending,
        )
        self.save_timeline(timeline)
        return timeline

    def health_check(self) -> dict[str, Any]:
        try:
            _ensure_storage()
            hyp_count = len(_read_jsonl(_HYPOTHESES_FILE))
            return {"status": "healthy", "stored_hypotheses": hyp_count, "last_error": None}
        except Exception as exc:
            return {"status": "failed", "stored_hypotheses": 0, "last_error": str(exc)}


_repo: InvestigationRepository | None = None
_repo_lock = Lock()


def get_investigation_repository() -> InvestigationRepository:
    global _repo
    with _repo_lock:
        if _repo is None:
            _repo = InvestigationRepository()
    return _repo


def new_hypothesis_id() -> str:
    return f"hyp_{uuid.uuid4().hex[:16]}"
