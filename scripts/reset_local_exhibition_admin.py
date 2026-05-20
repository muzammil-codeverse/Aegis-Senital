"""
Phase XV — Local Exhibition Admin Recovery Script

Usage:
    python scripts/reset_local_exhibition_admin.py --i-understand-local-only

This script:
  1. Loads the local user store (storage/security/users.jsonl)
  2. Resets or creates the admin user with the exhibition password
  3. Sets status=active and clears failed_login_count
  4. Writes credentials to storage/security/exhibition_admin_password.txt
  5. Optionally verifies by calling /api/auth/login if backend is running

LOCAL ONLY. Never run against production. All changes are file-based.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

EXHIBITION_USERNAME = "admin"
EXHIBITION_PASSWORD = "AegisLocalAdmin2026!"
EXHIBITION_DISPLAY = "System Administrator"
EXHIBITION_ROLE = "admin"
USERS_FILE = PROJECT_ROOT / "storage" / "security" / "users.jsonl"
CRED_FILE = PROJECT_ROOT / "storage" / "security" / "exhibition_admin_password.txt"
SECRET_FILE = PROJECT_ROOT / "storage" / "security" / "local_jwt_secret.txt"


def _load_env() -> None:
    try:
        from app.core.env_loader import load_project_env
        load_project_env()
    except Exception:
        pass


def _warn_local_only() -> None:
    print("=" * 60)
    print("  AEGIS LOCAL EXHIBITION ADMIN RESET")
    print("  Scope: LOCAL DEVELOPMENT / EXHIBITION ONLY")
    print("  Do NOT run against any production environment.")
    print("=" * 60)


def _verify_gitignore() -> None:
    gi = PROJECT_ROOT / ".gitignore"
    if not gi.exists():
        print("[WARN] .gitignore not found at project root")
        return
    content = gi.read_text(encoding="utf-8")
    issues = []
    if "storage/" not in content and "storage" not in content:
        issues.append("storage/ is not in .gitignore")
    if "*.local" not in content and ".env.local" not in content:
        issues.append("*.local is not in .gitignore")
    if issues:
        print("[WARN] .gitignore may not cover sensitive files:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("[OK] .gitignore covers storage/ and *.local")


def _reset_admin_in_store() -> dict:
    from app.services.user_store import UserStore
    from app.models.security_models import UserStatus

    store = UserStore(str(USERS_FILE))

    existing = store.get_user_by_username(EXHIBITION_USERNAME)
    if existing is not None:
        print(f"[INFO] Found existing user '{existing.username}' (id={existing.user_id}, status={existing.status})")
        updates: dict = {
            "status": UserStatus.ACTIVE.value,
            "password": EXHIBITION_PASSWORD,
            "must_change_password": False,
        }
        if existing.role != EXHIBITION_ROLE:
            updates["role"] = EXHIBITION_ROLE
        updated = store.update_user(existing.user_id, updates)
        if updated is None:
            raise RuntimeError("update_user returned None — user not found in store")
        # Clear failed login count manually
        with store._lock:
            user = store._users.get(updated.user_id)
            if user:
                user.failed_login_count = 0
                user.updated_at = time.time()
                meta = dict(user.metadata or {})
                meta.pop("locked_at", None)
                meta.pop("lockout_seconds", None)
                user.metadata = meta
                store._rewrite()
        print(f"[OK] Reset admin password, status=active, failed_login_count=0")
        final = store.get_user(updated.user_id)
    else:
        print(f"[INFO] Admin user not found — creating fresh admin account")
        final = store.create_user(
            username=EXHIBITION_USERNAME,
            password=EXHIBITION_PASSWORD,
            display_name=EXHIBITION_DISPLAY,
            role=EXHIBITION_ROLE,
            metadata={"bootstrap": True, "phase_xv": True},
        )
        print(f"[OK] Created admin user (id={final.user_id})")

    return {"user_id": final.user_id, "username": final.username, "role": final.role, "status": final.status}


def _write_credential_file(info: dict) -> None:
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        "Aegis local-only exhibition admin credential",
        f"username={EXHIBITION_USERNAME}",
        f"password={EXHIBITION_PASSWORD}",
        "Scope=local development/exhibition only",
        "Rotate before deployment. This file lives under ignored storage/.",
        "",
    ])
    CRED_FILE.write_text(content, encoding="utf-8")
    print(f"[OK] Credentials written to {CRED_FILE.relative_to(PROJECT_ROOT)}")


def _verify_backend_login() -> bool:
    try:
        import requests
        base = os.getenv("AEGIS_API_BASE_URL", "http://localhost:8000").rstrip("/")
        resp = requests.post(
            f"{base}/api/auth/login",
            json={"username": EXHIBITION_USERNAME, "password": EXHIBITION_PASSWORD},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print(f"[OK] Backend login verified: user={user.get('username')} role={user.get('role')} token={'present' if token else 'MISSING'}")
            if token:
                me = requests.get(
                    f"{base}/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5,
                )
                if me.status_code == 200:
                    me_data = me.json()
                    print(f"[OK] /api/auth/me confirmed: user={me_data.get('user', {}).get('username')} permissions={'*' in (me_data.get('permissions') or [])}")
                    return True
                else:
                    print(f"[WARN] /api/auth/me returned {me.status_code}")
            return resp.status_code == 200
        else:
            body = resp.text[:200]
            print(f"[WARN] Backend login returned {resp.status_code}: {body}")
            return False
    except Exception as exc:
        print(f"[INFO] Backend not reachable (start backend to verify): {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset local exhibition admin credentials")
    parser.add_argument("--i-understand-local-only", action="store_true", required=True,
                        help="Required safety flag confirming local-only operation")
    parser.add_argument("--verify-backend", action="store_true", default=True,
                        help="Attempt to verify by calling /api/auth/login (default: True)")
    args = parser.parse_args()

    _warn_local_only()
    _load_env()
    _verify_gitignore()

    print(f"\n[Step 1] Resetting admin in user store ({USERS_FILE.relative_to(PROJECT_ROOT)})")
    info = _reset_admin_in_store()

    print(f"\n[Step 2] Writing credential file")
    _write_credential_file(info)

    print(f"\n[Step 3] Backend verification (optional)")
    if args.verify_backend:
        _verify_backend_login()

    print("\n" + "=" * 60)
    print("  Admin Reset Complete")
    print(f"  username : {EXHIBITION_USERNAME}")
    print(f"  password : {EXHIBITION_PASSWORD}")
    print(f"  role     : {info['role']}")
    print(f"  status   : {info['status']}")
    print(f"  user_id  : {info['user_id']}")
    print("  Credential file: storage/security/exhibition_admin_password.txt")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
