#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the configured OpenAI LLM provider.")
    parser.add_argument("--model", default=None, help="Override the verification model ID.")
    args = parser.parse_args()

    from app.services.llm_service import get_llm_service

    result = get_llm_service().verify_provider(model_override=args.model)
    model = result.get("model") or args.model or "configured default"
    print(f"Model used: {model}")

    if result.get("status") == "not_verified":
        print(result.get("detail") or "OpenAI provider not verified.")
        return 0

    if result.get("status") != "ok":
        print(result.get("detail") or "OpenAI provider verification failed.")
        return 1

    print("Verification result: ok")
    print(f"Safe response: {result.get('response_preview') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
