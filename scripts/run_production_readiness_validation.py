#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.core.env_loader import load_project_env
from app.core.secret_safety import sanitize_secret_text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _openai_enabled() -> bool:
    config_path = ROOT / "configs" / "runtime" / "llm.yaml"
    if not config_path.exists():
        return False
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    llm_cfg = payload.get("llm", payload)
    if not isinstance(llm_cfg, dict) or not bool(llm_cfg.get("enabled", False)):
        return False
    provider_name = str(llm_cfg.get("provider") or llm_cfg.get("default_provider") or "local_stub").strip().lower()
    return provider_name == "openai"


def _run_command(command: list[str]) -> dict[str, object]:
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, env=os.environ.copy())
    stdout = sanitize_secret_text(result.stdout or "").strip()
    stderr = sanitize_secret_text(result.stderr or "").strip()
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "status": "passed" if result.returncode == 0 else "failed",
    }


def _write_report(output_dir: Path, summary: dict[str, object]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "production_readiness_summary.json"
    report_path = output_dir / "production_readiness_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# Production Readiness Validation",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Result: `{summary['result']}`",
        "",
        "## Steps",
    ]
    for step in summary["steps"]:
        lines.append(f"- `{step['name']}`: `{step['status']}`")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path, report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the production readiness validation sequence.")
    parser.add_argument("--skip-openai", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument("--generate-governance-evidence", action="store_true")
    args = parser.parse_args()

    load_project_env()
    steps: list[dict[str, object]] = []

    if not args.skip_docker:
        steps.append(
            {
                "name": "docker_compose_postgres_redis",
                **_run_command(["docker", "compose", "up", "-d", "postgres", "redis"]),
            }
        )

    steps.append(
        {
            "name": "validate_production_secrets",
            **_run_command([sys.executable, str(ROOT / "scripts" / "validate_production_secrets.py"), "--profile", "production"]),
        }
    )
    steps.append(
        {
            "name": "check_redis_runtime",
            **_run_command([sys.executable, str(ROOT / "scripts" / "check_redis_runtime.py")]),
        }
    )
    steps.append(
        {
            "name": "check_postgres_schema",
            **_run_command([sys.executable, str(ROOT / "scripts" / "check_postgres_schema.py")]),
        }
    )

    if args.generate_governance_evidence:
        steps.append(
            {
                "name": "generate_anomaly_live_eval_summary",
                **_run_command([sys.executable, str(ROOT / "scripts" / "generate_anomaly_live_eval_summary.py"), "--device", "cuda"]),
            }
        )

    if not args.skip_openai and _openai_enabled():
        steps.append(
            {
                "name": "verify_openai_llm",
                **_run_command([sys.executable, str(ROOT / "scripts" / "verify_openai_llm.py"), "--model", str(os.getenv("OPENAI_LLM_MODEL") or "gpt-5.4-mini")]),
            }
        )

    steps.append(
        {
            "name": "validate_runtime_production",
            **_run_command([sys.executable, str(ROOT / "scripts" / "validate_runtime.py"), "--profile", "production"]),
        }
    )

    failures = [step["name"] for step in steps if step["status"] == "failed"]
    summary = {
        "generated_at": _now_iso(),
        "result": "passed" if not failures else "failed",
        "failures": failures,
        "steps": steps,
    }
    summary_path, report_path = _write_report(ROOT / "storage" / "production_readiness", summary)
    print(
        json.dumps(
            {
                "result": summary["result"],
                "summary_path": str(summary_path),
                "report_path": str(report_path),
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
