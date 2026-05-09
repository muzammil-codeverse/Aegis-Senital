import json

from app.security.audit_integrity import compute_entry_hash, verify_audit_chain


def _entry(audit_id: str, detail: str) -> dict:
    return {
        "audit_id": audit_id,
        "timestamp": 1.0,
        "action": "login_success",
        "detail": detail,
        "metadata": {},
    }


def test_hash_chain_verifies_valid_logs(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = _entry("1", "ok")
    first["previous_hash"] = None
    first["entry_hash"] = compute_entry_hash(first, None)
    second = _entry("2", "ok2")
    second["previous_hash"] = first["entry_hash"]
    second["entry_hash"] = compute_entry_hash(second, first["entry_hash"])
    path.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n", encoding="utf-8")
    result = verify_audit_chain(str(path))
    assert result["status"] == "ok"
    assert result["checked_entries"] == 2


def test_tampered_entry_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    entry = _entry("1", "ok")
    entry["previous_hash"] = None
    entry["entry_hash"] = compute_entry_hash(entry, None)
    entry["detail"] = "tampered"
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    result = verify_audit_chain(str(path))
    assert result["status"] == "broken"
    assert result["broken_entries"]
