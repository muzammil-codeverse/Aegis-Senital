from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


def compute_auc_roc(y_true: list[int], y_score: list[float]) -> float:
    """Compute AUC-ROC using the trapezoidal rule (no sklearn dependency)."""
    if len(y_true) != len(y_score):
        raise ValueError("y_true and y_score must be the same length")

    pairs = sorted(zip(y_score, y_true), reverse=True, key=lambda x: x[0])
    positives = sum(y_true)
    negatives = len(y_true) - positives
    if positives == 0 or negatives == 0:
        return 0.5

    tp = fp = 0
    prev_fpr = prev_tpr = 0.0
    auc = 0.0
    prev_score = None

    for score, label in pairs + [(-1, -1)]:
        if score != prev_score:
            fpr = fp / negatives if negatives else 0.0
            tpr = tp / positives if positives else 0.0
            auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
            prev_fpr, prev_tpr = fpr, tpr
            prev_score = score
        if label == 1:
            tp += 1
        elif label == 0:
            fp += 1

    return min(1.0, max(0.0, auc))


def compute_confusion_matrix(
    y_true: list[str], y_pred: list[str], labels: list[str] | None = None
) -> dict[str, dict[str, int]]:
    """Return a per-class confusion dict: {actual: {predicted: count}}."""
    if labels is None:
        labels = sorted(set(y_true) | set(y_pred))
    cm: dict[str, dict[str, int]] = {l: {l2: 0 for l2 in labels} for l in labels}
    for t, p in zip(y_true, y_pred):
        if t in cm and p in cm.get(t, {}):
            cm[t][p] += 1
    return cm


def compute_precision_recall_f1(
    y_true: list[str], y_pred: list[str], label: str
) -> tuple[float, float, float]:
    """Per-class precision, recall, F1."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def compute_macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        return 0.0
    f1s = [compute_precision_recall_f1(y_true, y_pred, l)[2] for l in labels]
    return sum(f1s) / len(f1s)


def compute_weighted_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    total = len(y_true)
    if total == 0 or not labels:
        return 0.0
    weighted = 0.0
    for l in labels:
        support = sum(1 for t in y_true if t == l)
        _, _, f1 = compute_precision_recall_f1(y_true, y_pred, l)
        weighted += f1 * support
    return weighted / total


def compute_high_risk_recall(
    y_true: list[str],
    y_pred: list[str],
    high_risk_labels: list[str] | None = None,
) -> float:
    """Recall over high-risk anomaly classes (violence, shooting, explosion)."""
    high = set(high_risk_labels or ["violence", "shooting", "explosion", "panic_running"])
    tp = sum(1 for t, p in zip(y_true, y_pred) if t in high and p in high)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t in high and p not in high)
    return tp / (tp + fn) if (tp + fn) > 0 else 0.0


def compute_false_alarms_per_hour(
    y_true: list[int], y_pred: list[int], total_hours: float
) -> float:
    """False positive rate per hour for binary anomaly detection."""
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    return fp / max(total_hours, 1e-6)


def compute_p95_latency_ms(latencies_ms: list[float]) -> float:
    if not latencies_ms:
        return 0.0
    s = sorted(latencies_ms)
    idx = int(math.ceil(0.95 * len(s))) - 1
    return s[max(0, idx)]


def full_anomaly_metrics(
    y_true_binary: list[int],
    y_score: list[float],
    y_true_labels: list[str],
    y_pred_labels: list[str],
    latencies_ms: list[float],
    total_hours: float,
) -> dict[str, Any]:
    """Compute all Phase 28 anomaly evaluation metrics."""
    labels = sorted(set(y_true_labels) | set(y_pred_labels))
    per_class: dict[str, dict] = {}
    for l in labels:
        p, r, f = compute_precision_recall_f1(y_true_labels, y_pred_labels, l)
        per_class[l] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}

    overall_p = sum(v["precision"] for v in per_class.values()) / len(per_class) if per_class else 0.0
    overall_r = sum(v["recall"] for v in per_class.values()) / len(per_class) if per_class else 0.0

    return {
        "auc": round(compute_auc_roc(y_true_binary, y_score), 4),
        "macro_f1": round(compute_macro_f1(y_true_labels, y_pred_labels), 4),
        "weighted_f1": round(compute_weighted_f1(y_true_labels, y_pred_labels), 4),
        "precision": round(overall_p, 4),
        "recall": round(overall_r, 4),
        "high_risk_recall": round(compute_high_risk_recall(y_true_labels, y_pred_labels), 4),
        "false_alarms_per_hour": round(compute_false_alarms_per_hour(y_true_binary, [1 if s > 0.5 else 0 for s in y_score], total_hours), 2),
        "p95_latency_ms": round(compute_p95_latency_ms(latencies_ms), 2),
        "per_class": per_class,
        "confusion_matrix": compute_confusion_matrix(y_true_labels, y_pred_labels, labels),
        "n_samples": len(y_true_binary),
    }
