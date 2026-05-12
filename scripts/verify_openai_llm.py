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

from app.core.env_loader import load_project_env
from app.core.secret_safety import sanitize_secret_text


def _safe_print(value: str) -> None:
    print(sanitize_secret_text(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the configured OpenAI LLM provider.")
    parser.add_argument("--model", default=None, help="Override the verification model ID.")
    parser.add_argument("--verify-escalation", action="store_true", help="Also verify the configured escalation model.")
    parser.add_argument("--verify-final-report", action="store_true", help="Also verify the configured final report model.")
    args = parser.parse_args()

    load_project_env()

    from app.services.llm_service import get_llm_service

    result = get_llm_service().verify_provider(
        model_override=args.model,
        include_escalation=args.verify_escalation,
        include_final_report=args.verify_final_report,
    )
    model = result.get("model") or args.model or "configured default"
    _safe_print(f"Model used: {model}")

    if result.get("status") == "not_verified":
        _safe_print(result.get("detail") or "OpenAI provider not verified.")
        return 0

    if result.get("status") != "ok":
        _safe_print(result.get("detail") or "OpenAI provider verification failed.")
        for item in result.get("models_checked") or []:
            _safe_print(f"Checked {item.get('kind')}: {item.get('model')} -> {item.get('status')}")
        return 1

    _safe_print("Verification result: ok")
    _safe_print(f"Safe response: {result.get('response_preview') or ''}")
    for item in result.get("models_checked") or []:
        _safe_print(f"Checked {item.get('kind')}: {item.get('model')} -> {item.get('status')}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
