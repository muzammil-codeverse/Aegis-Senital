from __future__ import annotations

import os
import sys
from typing import Any

import requests


def _top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(payload.keys())
    return []


def _print_result(path: str, response: requests.Response) -> None:
    content_type = response.headers.get("content-type", "")
    payload = response.json() if "application/json" in content_type else {}
    keys = _top_level_keys(payload)
    print(f"{path} status={response.status_code} keys={keys[:12]}")


def main() -> int:
    base_url = os.getenv("AEGIS_API_BASE_URL", "http://localhost:8000").rstrip("/")
    username = os.getenv("AEGIS_BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.getenv("AEGIS_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123")

    session = requests.Session()
    login = session.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if login.status_code != 200:
        print(f"/api/auth/login status={login.status_code}")
        return 1

    for path in ("/api/system/health", "/api/system/readiness", "/api/system/liveness"):
        response = session.get(f"{base_url}{path}", timeout=12)
        _print_result(path, response)

    return 0


if __name__ == "__main__":
    sys.exit(main())

