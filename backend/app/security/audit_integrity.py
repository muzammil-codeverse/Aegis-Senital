from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical_entry(entry: dict[str, Any], previous_hash: str | None = None) -> str:
    payload = dict(entry)
    payload.pop("entry_hash", None)
    payload.pop("previous_hash", None)
    envelope = {
        "previous_hash": previous_hash,
        "entry": payload,
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(entry: dict, previous_hash: str | None = None) -> str:
    return hashlib.sha256(_canonical_entry(entry, previous_hash).encode("utf-8")).hexdigest()


def verify_audit_chain(file_path: str) -> dict:
    path = Path(file_path)
    result = {
        "file": str(path),
        "status": "ok",
        "checked_entries": 0,
        "broken_entries": [],
        "latest_hash": None,
    }
    previous_hash: str | None = None
    if not path.exists():
        result["status"] = "missing"
        return result

    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                result["broken_entries"].append({"line": line_no, "reason": "invalid_json"})
                continue

            entry_hash = entry.get("entry_hash")
            entry_previous = entry.get("previous_hash")
            if not entry_hash:
                previous_hash = None
                continue

            expected = compute_entry_hash(entry, entry_previous)
            result["checked_entries"] += 1
            if entry_previous != previous_hash:
                result["broken_entries"].append({"line": line_no, "reason": "previous_hash_mismatch"})
            if expected != entry_hash:
                result["broken_entries"].append({"line": line_no, "reason": "entry_hash_mismatch"})
            previous_hash = entry_hash
            result["latest_hash"] = entry_hash

    if result["broken_entries"]:
        result["status"] = "broken"
    return result
