"""Phase 25 — Open-vocab prompt benchmark runner."""
from __future__ import annotations

import logging
from pathlib import Path

from backend.app.evaluation.schemas import BenchmarkTaskResult
from backend.app.evaluation.metrics.open_vocab_metrics import compute_open_vocab_metrics

logger = logging.getLogger(__name__)


class OpenVocabBenchmarkRunner:

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def run(
        self,
        samples_by_prompt: dict[str, list[dict]],
        predict_fn,
        prompt_configs: list[dict],
        dataset_name: str,
        run_dir: Path,
    ) -> BenchmarkTaskResult:
        """
        predict_fn: callable(image_path, prompt_text, threshold) → [{"label", "score", "bbox"}]
        """
        if not samples_by_prompt:
            return BenchmarkTaskResult(
                task="open_vocab",
                model_name="grounding_dino",
                dataset_name=dataset_name,
                skipped=True,
                skip_reason="No open-vocab evaluation data provided",
            )

        metric_result = compute_open_vocab_metrics(
            samples_by_prompt=samples_by_prompt,
            predict_fn=predict_fn,
            prompt_configs=prompt_configs,
        )

        # Write per-prompt CSV
        self._write_prompt_csv(metric_result.prompt_results, run_dir)

        return BenchmarkTaskResult(
            task="open_vocab",
            model_name="grounding_dino",
            device=self.device,
            dataset_name=dataset_name,
            metrics=metric_result.to_dict(),
            warnings=metric_result.warnings,
        )

    def _write_prompt_csv(self, prompt_results: list, run_dir: Path) -> None:
        import csv
        out = run_dir / "open_vocab_prompt_metrics.csv"
        if not prompt_results:
            return
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["prompt_id", "prompt_text", "threshold", "precision", "recall", "f1", "avg_latency_ms"],
            )
            writer.writeheader()
            for pr in prompt_results:
                writer.writerow({
                    "prompt_id": pr.prompt_id,
                    "prompt_text": pr.prompt_text,
                    "threshold": pr.threshold,
                    "precision": pr.precision,
                    "recall": pr.recall,
                    "f1": pr.f1,
                    "avg_latency_ms": pr.avg_latency_ms,
                })
