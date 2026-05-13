from __future__ import annotations

import os
import sys
from typing import Any

import requests


def _mask(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-2:]}"


def main() -> int:
    base_url = os.getenv("AEGIS_API_BASE_URL", "http://localhost:8000").rstrip("/")
    username = os.getenv("AEGIS_BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.getenv("AEGIS_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123")

    session = requests.Session()
    payload: dict[str, Any] = {"username": username, "password": password}
    login = session.post(f"{base_url}/api/auth/login", json=payload, timeout=10)
    if login.status_code != 200:
        print(f"[FAIL] login status={login.status_code}")
        return 1

    login_json = login.json() if login.headers.get("content-type", "").startswith("application/json") else {}
    me = session.get(f"{base_url}/api/auth/me", timeout=10)
    if me.status_code != 200:
        print(f"[FAIL] session check status={me.status_code}")
        return 1

    me_json = me.json()
    cookie_names = sorted(session.cookies.keys())
    has_auth_cookie = any("access" in name for name in cookie_names)
    has_csrf_cookie = any("csrf" in name for name in cookie_names)

    print("[PASS] admin login smoke")
    print(f"  base_url={base_url}")
    print(f"  username={_mask(username)}")
    print(f"  auth_storage_mode={me_json.get('auth_storage_mode')}")
    print(f"  has_auth_cookie={has_auth_cookie}")
    print(f"  has_csrf_cookie={has_csrf_cookie}")
    print(f"  user={me_json.get('user', {}).get('username')} role={me_json.get('user', {}).get('role')}")
    print(f"  bearer_returned={'access_token' in login_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
