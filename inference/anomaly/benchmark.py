from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from inference.anomaly.config import load_anomaly_config
from inference.anomaly.schemas import AnomalyPrediction

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    dataset: str
    auc: float
    macro_f1: float
    weighted_f1: float
    precision: float
    recall: float
    high_risk_recall: float
    false_alarms_per_hour: float
    p95_latency_ms: float
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "auc": round(self.auc, 4),
            "macro_f1": round(self.macro_f1, 4),
            "weighted_f1": round(self.weighted_f1, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "high_risk_recall": round(self.high_risk_recall, 4),
            "false_alarms_per_hour": round(self.false_alarms_per_hour, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "passed": self.passed,
            "failure_reasons": self.failure_reasons,
        }


def check_acceptance_policy(result: BenchmarkResult) -> BenchmarkResult:
    """Evaluate a BenchmarkResult against the configured acceptance policy."""
    cfg = load_anomaly_config().get("acceptance_policy", {})
    min_auc = float(cfg.get("min_auc", 0.90))
    min_f1 = float(cfg.get("min_macro_f1", 0.87))
    min_recall = float(cfg.get("min_high_risk_recall", 0.90))
    max_fa = float(cfg.get("max_false_alarms_per_hour", 3))
    max_lat = float(cfg.get("max_p95_latency_ms", 120))

    reasons: list[str] = []
    if result.auc < min_auc:
        reasons.append(f"AUC {result.auc:.3f} < {min_auc}")
    if result.macro_f1 < min_f1:
        reasons.append(f"macro_F1 {result.macro_f1:.3f} < {min_f1}")
    if result.high_risk_recall < min_recall:
        reasons.append(f"high_risk_recall {result.high_risk_recall:.3f} < {min_recall}")
    if result.false_alarms_per_hour > max_fa:
        reasons.append(f"false_alarms/h {result.false_alarms_per_hour:.2f} > {max_fa}")
    if result.p95_latency_ms > max_lat:
        reasons.append(f"p95_latency_ms {result.p95_latency_ms:.1f} > {max_lat}")

    result.passed = len(reasons) == 0
    result.failure_reasons = reasons
    return result


def measure_latency_ms(
    service,
    window,
    n_runs: int = 50,
) -> dict[str, float]:
    """Time evaluate_window() over n_runs and return latency stats."""
    latencies: list[float] = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        service.evaluate_window(window)
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p95 = latencies[int(0.95 * len(latencies))]
    return {
        "mean_ms": round(sum(latencies) / len(latencies), 2),
        "p50_ms": round(latencies[len(latencies) // 2], 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(latencies[-1], 2),
    }
