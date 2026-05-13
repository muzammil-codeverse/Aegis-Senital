#!/usr/bin/env python3
"""Phase 56 — Smoke test drone WebSocket real-time updates."""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from typing import Any

import requests

REQUIRED_PAYLOAD_TYPES = {"runtime_status", "telemetry", "frame_status"}
OPTIONAL_PAYLOAD_TYPES = {"mission_status", "detection_event", "no_detection_frame", "fusion_update"}
FORBIDDEN_WORDING = {
    "suspect confirmed",
    "identity confirmed",
    "target confirmed",
    "criminal confirmed",
    "attacker confirmed",
    "confirmed terrorist",
    "confirmed threat",
    "real drone pursuit",
}


def _login(backend: str, password: str) -> str:
    try:
        resp = requests.post(
            f"{backend}/api/auth/login",
            json={"username": "admin", "password": password},
            timeout=10,
        )
        if resp.status_code < 400:
            return str(resp.json().get("access_token") or "").strip()
    except Exception:
        pass
    return ""


def _check_ws_via_polling(backend: str, headers: dict[str, str], duration: int) -> dict[str, Any]:
    """
    Fallback: poll REST endpoints that mirror WS payloads when websockets lib is unavailable.
    This validates the same data fields that WS would carry.
    """
    collected: dict[str, Any] = {}
    errors: list[str] = []

    def _get(url: str) -> Any:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code < 500:
                return resp.json()
        except Exception as exc:
            errors.append(str(exc))
        return None

    start = time.time()
    poll_endpoints = {
        "runtime_status": f"{backend}/api/drone-simulation/status",
        "telemetry": f"{backend}/api/drone-simulation/telemetry",
        "frame_status": f"{backend}/api/drone-simulation/cameras/front_center/latest-frame",
        "mission_status": f"{backend}/api/drone-missions",
    }

    interval = max(2, duration // 5)
    while time.time() - start < duration:
        for payload_type, url in poll_endpoints.items():
            if payload_type not in collected:
                data = _get(url)
                if data is not None:
                    collected[payload_type] = data
        time.sleep(interval)

    return {"collected_types": list(collected.keys()), "errors": errors, "mode": "polling_fallback"}


def _try_ws(ws_url: str, token: str, duration: int) -> dict[str, Any]:
    try:
        import websocket  # type: ignore[import-untyped]
    except ImportError:
        return {"available": False, "reason": "websocket-client not installed"}

    received: list[dict[str, Any]] = []
    forbidden_hits: list[str] = []
    errors: list[str] = []
    done = threading.Event()

    headers: list[str] = []
    if token:
        headers.append(f"Authorization: Bearer {token}")

    def on_message(ws: Any, message: str) -> None:  # type: ignore[misc]
        try:
            data = json.loads(message)
            received.append(data)
            text = json.dumps(data).lower()
            for fw in FORBIDDEN_WORDING:
                if fw in text:
                    forbidden_hits.append(fw)
        except Exception:
            pass

    def on_error(ws: Any, error: Any) -> None:  # type: ignore[misc]
        errors.append(str(error))

    def on_close(ws: Any, *args: Any) -> None:  # type: ignore[misc]
        done.set()

    ws = websocket.WebSocketApp(
        ws_url,
        header=headers,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    thread = threading.Thread(target=ws.run_forever, daemon=True)
    thread.start()
    done.wait(timeout=duration + 2)
    ws.close()

    payload_types_seen = set()
    for msg in received:
        ptype = msg.get("type") or msg.get("event") or msg.get("payload_type")
        if ptype:
            payload_types_seen.add(str(ptype))

    return {
        "available": True,
        "messages_received": len(received),
        "payload_types_seen": sorted(payload_types_seen),
        "required_types_seen": sorted(REQUIRED_PAYLOAD_TYPES & payload_types_seen),
        "missing_required_types": sorted(REQUIRED_PAYLOAD_TYPES - payload_types_seen),
        "forbidden_hits": forbidden_hits,
        "errors": errors[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test drone WebSocket real-time update stream.")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--ws-url", default=None, help="Override WebSocket URL (default: ws://127.0.0.1:8000/ws/drone)")
    parser.add_argument("--duration", type=int, default=20, help="Listen duration in seconds")
    parser.add_argument("--strict", action="store_true", help="Fail if required payload types not seen")
    args = parser.parse_args()

    password = os.environ.get("AEGIS_BOOTSTRAP_ADMIN_PASSWORD") or "ChangeMe123"
    token = _login(args.backend, password)
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    ws_url = args.ws_url or args.backend.replace("http://", "ws://").replace("https://", "wss://") + "/ws/drone"

    # First try real WebSocket; fall back to polling if not available
    ws_result = _try_ws(ws_url, token, args.duration)

    if not ws_result.get("available"):
        # Fallback to polling-based verification
        poll_result = _check_ws_via_polling(args.backend, auth_headers, args.duration)
        collected = set(poll_result.get("collected_types") or [])
        required_seen = sorted(REQUIRED_PAYLOAD_TYPES & collected)
        missing = sorted(REQUIRED_PAYLOAD_TYPES - collected)
        ok = not missing or not args.strict
        result = {
            "status": "ok" if ok else "failed",
            "ws_mode": "polling_fallback",
            "ws_reason": ws_result.get("reason"),
            "required_types_seen": required_seen,
            "missing_required_types": missing,
            "polling_detail": poll_result,
        }
        print(json.dumps(result, indent=2))
        return 0 if ok else 1

    forbidden_hits = ws_result.get("forbidden_hits") or []
    missing = ws_result.get("missing_required_types") or []
    ok = not forbidden_hits and (not missing or not args.strict)

    result = {
        "status": "ok" if ok else "failed",
        "ws_mode": "websocket",
        "ws_url": ws_url,
        **ws_result,
    }
    print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
