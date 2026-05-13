from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.repositories.drone_mission_repository import get_drone_mission_repository
from app.services.case_service import get_case_service
from app.services.drone.drone_mission_evidence_service import get_drone_mission_evidence_service


def main() -> int:
    case_service = get_case_service()
    mission_repo = get_drone_mission_repository()
    evidence_service = get_drone_mission_evidence_service()

    cases = case_service.list_cases({"limit": 500})
    demo_cases = [item for item in cases if bool((item.metadata or {}).get("demo"))]
    if not demo_cases:
        print(json.dumps({"status": "failed", "reason": "No demo case exists"}, indent=2))
        return 1

    sessions = mission_repo.list_sessions(limit=500)
    completed = [item for item in sessions if item.status.value in {"completed", "failed", "cancelled"}]
    if not completed:
        print(json.dumps({"status": "failed", "reason": "No mission session available for evidence bundling"}, indent=2))
        return 1

    case = demo_cases[-1]
    session = completed[-1]
    evidence = evidence_service.attach_bundle_to_case(case.case_id, session.session_id, actor="operator")

    case_evidence = case_service.get_evidence(evidence.evidence_id)
    file_backed = bool(case_evidence and case_evidence.storage_uri)
    hash_ok = True
    if file_backed:
        hash_ok = bool(case_evidence.hash_sha256)

    payload = {
        "status": "ok" if hash_ok else "failed",
        "case_id": case.case_id,
        "session_id": session.session_id,
        "evidence_id": evidence.evidence_id,
        "simulated": bool((evidence.metadata or {}).get("simulated", True)),
        "operator_review_required": bool((evidence.metadata or {}).get("operator_review_required", True)),
        "file_backed": file_backed,
        "hash_present_if_file_backed": hash_ok,
    }
    print(json.dumps(payload, indent=2))
    return 0 if hash_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
