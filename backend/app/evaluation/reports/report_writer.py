"""Phase 25 — Benchmark report writer."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from backend.app.evaluation.schemas import BenchmarkRun

logger = logging.getLogger(__name__)


class ReportWriter:
    """Writes a complete benchmark run to storage/evaluation_runs/<run_id>/."""

    def write(self, run: BenchmarkRun, run_dir: Path) -> dict[str, str]:
        """
        Write all artifacts for a benchmark run.
        Returns mapping of artifact_name → file_path.
        """
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {}

        # metrics.json
        metrics_path = run_dir / "metrics.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, indent=2, default=str)
        artifacts["metrics_json"] = str(metrics_path)

        # report.md
        report_path = run_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._render_markdown(run))
        artifacts["report_md"] = str(report_path)

        logger.info("BenchmarkRun %s artifacts written to %s", run.run_id, run_dir)
        return artifacts

    def _render_markdown(self, run: BenchmarkRun) -> str:
        lines = [
            f"# Benchmark Report — {run.run_id}",
            "",
            f"**Timestamp:** {run.timestamp}  ",
            f"**Git commit:** {run.git_commit or 'unknown'}  ",
            f"**Config hash:** {run.config_hash}  ",
            f"**Device:** {run.device}  ",
            "",
        ]

        for tr in run.task_results:
            lines += [
                f"## Task: {tr.task.upper()} — {tr.model_name}",
                "",
            ]
            if tr.skipped:
                lines += [f"> **SKIPPED:** {tr.skip_reason}", ""]
                continue

            lines += [
                f"- **Dataset:** {tr.dataset_name}",
                f"- **Device:** {tr.device}",
                f"- **Failure cases:** {tr.failure_cases_count}",
                "",
                "### Metrics",
                "",
            ]
            for key, val in tr.metrics.items():
                if isinstance(val, dict):
                    lines.append(f"**{key}:**")
                    for k, v in val.items():
                        lines.append(f"  - {k}: {v}")
                elif isinstance(val, list):
                    lines.append(f"**{key}:** (list, {len(val)} items)")
                else:
                    lines.append(f"- **{key}:** {val}")
            lines.append("")

            if tr.warnings:
                lines += ["### Warnings", ""]
                for w in tr.warnings:
                    lines.append(f"- {w}")
                lines.append("")

        if run.total_warnings:
            lines += ["## Run-level Warnings", ""]
            for w in run.total_warnings:
                lines.append(f"- {w}")

        return "\n".join(lines) + "\n"
