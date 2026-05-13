from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests


def _csrf_header(session: requests.Session) -> dict[str, str]:
  token = session.cookies.get("aegis_csrf_token")
  return {"X-CSRF-Token": token} if token else {}


def _print(name: str, response: requests.Response) -> bool:
  ok = response.status_code == 200
  print(f"{name}: status={response.status_code} {'PASS' if ok else 'FAIL'}")
  if not ok:
    try:
      print(f"  body={response.json()}")
    except Exception:
      print(f"  body={response.text[:300]}")
  return ok


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("--video", required=True)
  parser.add_argument("--device", default="cuda")
  args = parser.parse_args()

  video_path = Path(args.video)
  if not video_path.is_file():
    print(f"video_missing: {video_path}")
    return 1

  base = os.getenv("AEGIS_API_BASE_URL", "http://localhost:8000").rstrip("/")
  username = os.getenv("AEGIS_BOOTSTRAP_ADMIN_USERNAME", "admin")
  password = os.getenv("AEGIS_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123")
  s = requests.Session()

  login = s.post(f"{base}/api/auth/login", json={"username": username, "password": password}, timeout=15)
  if not _print("login", login):
    return 1

  listed = s.get(f"{base}/api/uploaded-videos", timeout=20)
  if not _print("list_sessions", listed):
    return 1

  with video_path.open("rb") as fh:
    upload = s.post(
      f"{base}/api/uploaded-videos",
      files={"file": (video_path.name, fh, "video/mp4")},
      data={"options": "{}"},
      headers=_csrf_header(s),
      timeout=120,
    )
  if not _print("upload", upload):
    return 1

  payload = upload.json()
  session_id = payload.get("session", {}).get("session_id")
  if not session_id:
    print("session_id_missing")
    return 1
  print(f"session_id={session_id}")

  process = s.post(f"{base}/api/uploaded-videos/{session_id}/process", headers=_csrf_header(s), timeout=30)
  _print("start_processing", process)

  deadline = time.time() + 180
  latest_status = None
  while time.time() < deadline:
    status_resp = s.get(f"{base}/api/uploaded-videos/{session_id}/status", timeout=20)
    if not _print("status_poll", status_resp):
      return 1
    latest_status = status_resp.json().get("item", {}).get("status")
    print(f"  session_status={latest_status}")
    if latest_status in {"completed", "failed", "cancelled"}:
      break
    time.sleep(2)

  timeline = s.get(f"{base}/api/uploaded-videos/{session_id}/timeline", timeout=20)
  events = s.get(f"{base}/api/uploaded-videos/{session_id}/events", timeout=20)
  report = s.get(f"{base}/api/uploaded-videos/{session_id}/report", timeout=20)

  timeline_ok = _print("timeline", timeline)
  events_ok = _print("events", events)
  report_ok = report.status_code in {200, 404}
  print(f"report: status={report.status_code} {'PASS' if report_ok else 'FAIL'}")

  success = timeline_ok and events_ok and report_ok and latest_status in {"completed", "failed", "cancelled"}
  print("RESULT:", "PASS" if success else "FAIL")
  return 0 if success else 1


if __name__ == "__main__":
  sys.exit(main())
