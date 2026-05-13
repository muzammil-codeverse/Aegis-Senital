from __future__ import annotations

import os
import sys

import requests


def _csrf_header(session: requests.Session) -> dict[str, str]:
  token = session.cookies.get("aegis_csrf_token")
  return {"X-CSRF-Token": token} if token else {}


def _ok(name: str, response: requests.Response) -> bool:
  good = response.status_code == 200
  print(f"{name}: status={response.status_code} {'PASS' if good else 'FAIL'}")
  if not good:
    try:
      print(f"  body={response.json()}")
    except Exception:
      print(f"  body={response.text[:300]}")
  return good


def main() -> int:
  base = os.getenv("AEGIS_API_BASE_URL", "http://localhost:8000").rstrip("/")
  username = os.getenv("AEGIS_BOOTSTRAP_ADMIN_USERNAME", "admin")
  password = os.getenv("AEGIS_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123")
  s = requests.Session()

  login = s.post(f"{base}/api/auth/login", json={"username": username, "password": password}, timeout=15)
  if not _ok("login", login):
    return 1

  checks = [
    ("start_session", s.post(f"{base}/api/drone-simulation/start", headers=_csrf_header(s), timeout=30)),
    ("status", s.get(f"{base}/api/drone-simulation/status", timeout=30)),
    ("telemetry", s.get(f"{base}/api/drone-simulation/telemetry", timeout=30)),
    ("cameras", s.get(f"{base}/api/drone-simulation/cameras", timeout=30)),
    ("front_center_frame", s.get(f"{base}/api/drone-simulation/cameras/front_center/latest-frame", timeout=30)),
    ("stop_session", s.post(f"{base}/api/drone-simulation/stop", headers=_csrf_header(s), timeout=30)),
  ]
  failed = [name for name, resp in checks if not _ok(name, resp)]
  print("RESULT:", "PASS" if not failed else f"FAIL ({', '.join(failed)})")
  return 0 if not failed else 1


if __name__ == "__main__":
  sys.exit(main())
