#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.env_loader import load_project_env


def check_redis_runtime(*, redis_url: str | None = None, ttl_seconds: int = 15) -> dict[str, object]:
    resolved_url = str(redis_url or os.getenv("REDIS_URL") or "").strip()
    if not resolved_url:
        raise RuntimeError("REDIS_URL is not configured")

    try:
        import redis
    except Exception as exc:
        raise RuntimeError("redis package is not installed") from exc

    client = redis.from_url(resolved_url, socket_connect_timeout=3, socket_timeout=3, decode_responses=True)
    key = f"phase51:redis-runtime:{uuid.uuid4().hex}"
    started = time.perf_counter()
    ping_ok = client.ping()
    client.set(key, "ok", ex=ttl_seconds)
    value = client.get(key)
    ttl = client.ttl(key)
    client.delete(key)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)

    if value != "ok":
        raise RuntimeError("Redis SET/GET verification failed")

    return {
        "status": "ok",
        "ping": bool(ping_ok),
        "set_get": value == "ok",
        "ttl_seconds": max(int(ttl), 0),
        "latency_ms": latency_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Redis runtime connectivity without printing secrets.")
    parser.add_argument("--ttl-seconds", type=int, default=15)
    args = parser.parse_args()

    load_project_env()
    result = check_redis_runtime(ttl_seconds=max(1, args.ttl_seconds))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
