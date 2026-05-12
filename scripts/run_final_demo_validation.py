#!/usr/bin/env python3
"""Run the bounded Phase 50 final demo validation workflow."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "storage" / "final_validation"


def _resolve_python() -> str:
    project_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if project_python.exists():
        return str(project_python)
    return sys.executable


PYTHON = _resolve_python()


def _run(
    name: str,
    command: list[str],
    *,
    cwd: Path | None = None,
    required: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
    )
    elapsed = round(time.monotonic() - started, 3)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    status = "passed" if result.returncode == 0 else ("failed" if required else "degraded")
    print(f"[{'PASS' if status == 'passed' else ('WARN' if status == 'degraded' else 'FAIL')}] {name} ({elapsed:.1f}s)")
    return {
        "name": name,
        "command": command,
        "cwd": str(cwd or ROOT),
        "required": required,
        "status": status,
        "returncode": result.returncode,
        "duration_seconds": elapsed,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
    }


def _pick_uploaded_video_sample() -> Path | None:
    candidates: list[Path] = []
    for pattern in ("storage/uploaded_videos/*.mp4", "storage/replay/**/*.mp4"):
        candidates.extend(sorted(ROOT.glob(pattern)))
    files = [path for path in candidates if path.is_file()]
    if not files:
        return None
    return min(files, key=lambda path: path.stat().st_size)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _summarize_existing_e2e() -> dict[str, Any]:
    report_dir = ROOT / "frontend" / "playwright-report"
    test_results = ROOT / "frontend" / "test-results"
    status = "skipped"
    detail = "No existing Playwright report found."
    if report_dir.exists():
        status = "passed"
        detail = f"playwright-report present at {report_dir}"
    elif test_results.exists():
        status = "degraded"
        detail = f"test-results present without playwright-report at {test_results}"
    return {
        "name": "e2e_summary",
        "required": False,
        "status": status,
        "returncode": 0,
        "duration_seconds": 0.0,
        "stdout_tail": detail,
        "stderr_tail": "",
    }


def _render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Final Demo Validation Report",
        "",
        f"- Generated at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(summary['generated_at']))}",
        f"- Overall status: `{summary['overall_status']}`",
        f"- Python executable: `{summary['python_executable']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Required | Duration (s) |",
        "| --- | --- | --- | ---: |",
    ]
    for item in summary["checks"]:
        lines.append(
            f"| {item['name']} | {item['status']} | {'yes' if item['required'] else 'no'} | {item['duration_seconds']:.1f} |"
        )
    lines.extend(["", "## Notes", ""])
    for item in summary["checks"]:
        note = item["stdout_tail"] or item["stderr_tail"] or ""
        if note:
            lines.append(f"### {item['name']}")
            lines.append("")
            lines.append("```text")
            lines.append(note[-1200:])
            lines.append("```")
            lines.append("")
    if summary.get("model_smoke"):
        lines.append("## Model Smoke Summary")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summary["model_smoke"], indent=2)[:6000])
        lines.append("```")
        lines.append("")
    if summary.get("backend_smoke"):
        lines.append("## Backend Smoke Summary")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summary["backend_smoke"], indent=2)[:6000])
        lines.append("```")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final demo validation.")
    parser.add_argument("--include-drone-live", action="store_true", help="Run live drone runtime checks too")
    parser.add_argument("--device", default="cuda", help="Device hint for model/drone smoke")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model_json = OUTPUT_DIR / "model_smoke_summary.json"
    backend_json = OUTPUT_DIR / "backend_smoke_summary.json"

    checks: list[dict[str, Any]] = []
    checks.append(_run("validate_runtime_development", [PYTHON, "scripts/validate_runtime.py", "--profile", "development"]))
    checks.append(_run("smoke_all_model_assets", [PYTHON, "scripts/smoke_all_model_assets.py", "--device", args.device, "--json-out", str(model_json)]))
    checks.append(_run("frontend_safe_wording", [PYTHON, "scripts/check_frontend_safe_wording.py"]))
    checks.append(_run("frontend_accessibility_static", [PYTHON, "scripts/check_frontend_accessibility_static.py"]))
    checks.append(_run("smoke_backend_runtime", [PYTHON, "scripts/smoke_backend_runtime.py", "--json-out", str(backend_json)]))
    checks.append(_run("investigation_path_reconstruction", [PYTHON, "scripts/smoke_investigation_path_reconstruction.py"]))
    checks.append(_run("llm_case_workflow", [PYTHON, "scripts/smoke_llm_case_workflow.py", "--provider", "local_stub"]))
    checks.append(_run("drone_fusion_deterministic", [PYTHON, "scripts/smoke_drone_fixed_camera_fusion.py"]))

    video_path = _pick_uploaded_video_sample()
    if video_path is None:
        checks.append(
            {
                "name": "uploaded_video_workflow",
                "command": [],
                "cwd": str(ROOT),
                "required": True,
                "status": "failed",
                "returncode": 1,
                "duration_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": "No local uploaded-video sample found under storage/uploaded_videos or storage/replay.",
            }
        )
        print("[FAIL] uploaded_video_workflow (0.0s)")
    else:
        checks.append(
            _run(
                "uploaded_video_workflow",
                [
                    PYTHON,
                    "scripts/smoke_uploaded_video_workflow.py",
                    "--video",
                    str(video_path),
                    "--device",
                    args.device,
                    "--max-frames",
                    "60",
                ],
            )
        )

    npm = shutil.which("npm")
    if npm:
        checks.append(_run("frontend_build", [npm, "run", "build"], cwd=ROOT / "frontend"))
    else:
        checks.append(
            {
                "name": "frontend_build",
                "command": ["npm", "run", "build"],
                "cwd": str(ROOT / "frontend"),
                "required": True,
                "status": "failed",
                "returncode": 127,
                "duration_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": "npm not found in PATH.",
            }
        )
        print("[FAIL] frontend_build (0.0s)")

    checks.append(_summarize_existing_e2e())

    if args.include_drone_live:
        checks.append(_run("drone_runtime_strict", [PYTHON, "scripts/verify_drone_sim_runtime.py", "--strict"], required=False))
        checks.append(_run("cosys_airsim_runtime", [PYTHON, "scripts/smoke_cosys_airsim_runtime.py"], required=False))
        checks.append(
            _run(
                "drone_simulation_pipeline_live",
                [PYTHON, "scripts/smoke_drone_simulation_pipeline.py", "--strict", "--device", args.device],
                required=False,
            )
        )
        checks.append(
            _run(
                "drone_mission_live",
                [PYTHON, "scripts/smoke_drone_mission.py", "--strict", "--device", args.device],
                required=False,
            )
        )
        checks.append(
            _run(
                "drone_fusion_live",
                [PYTHON, "scripts/smoke_drone_fixed_camera_fusion.py", "--live", "--device", args.device],
                required=False,
            )
        )

    required_failures = [item["name"] for item in checks if item["required"] and item["status"] == "failed"]
    optional_degraded = [item["name"] for item in checks if not item["required"] and item["status"] != "passed"]
    summary = {
        "generated_at": time.time(),
        "python_executable": PYTHON,
        "overall_status": "failed" if required_failures else ("passed_with_optional_degraded" if optional_degraded else "passed"),
        "required_failures": required_failures,
        "optional_degraded": optional_degraded,
        "checks": checks,
        "model_smoke": _load_json(model_json),
        "backend_smoke": _load_json(backend_json),
    }

    json_path = OUTPUT_DIR / "final_demo_validation_summary.json"
    report_path = OUTPUT_DIR / "final_demo_validation_report.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path.write_text(_render_report(summary), encoding="utf-8")

    print()
    print(f"Summary: {json_path}")
    print(f"Report: {report_path}")
    print(f"Overall: {summary['overall_status']}")
    return 1 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
