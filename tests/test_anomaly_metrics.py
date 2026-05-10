import pytest
from backend.app.evaluation.metrics.anomaly_metrics import (
    compute_auc_roc,
    compute_macro_f1,
    compute_weighted_f1,
    compute_precision_recall_f1,
    compute_high_risk_recall,
    compute_false_alarms_per_hour,
    compute_p95_latency_ms,
    compute_confusion_matrix,
    full_anomaly_metrics,
)


def test_auc_perfect():
    y_true = [1, 1, 0, 0]
    y_score = [0.9, 0.8, 0.2, 0.1]
    assert compute_auc_roc(y_true, y_score) == pytest.approx(1.0, abs=0.01)


def test_auc_random():
    y_true = [1, 0, 1, 0]
    y_score = [0.5, 0.5, 0.5, 0.5]
    auc = compute_auc_roc(y_true, y_score)
    assert 0.0 <= auc <= 1.0


def test_auc_all_same_class():
    y_true = [1, 1, 1]
    y_score = [0.9, 0.8, 0.7]
    auc = compute_auc_roc(y_true, y_score)
    assert auc == pytest.approx(0.5, abs=0.01)


def test_precision_recall_f1():
    y_true = ["violence", "normal", "violence", "loitering", "normal"]
    y_pred = ["violence", "normal", "loitering", "loitering", "normal"]
    p, r, f = compute_precision_recall_f1(y_true, y_pred, "violence")
    assert p == pytest.approx(1.0, abs=0.01)  # 1 TP, 0 FP
    assert r == pytest.approx(0.5, abs=0.01)  # 1 TP, 1 FN


def test_macro_f1():
    y_true = ["a", "a", "b", "b"]
    y_pred = ["a", "b", "b", "b"]
    f1 = compute_macro_f1(y_true, y_pred)
    assert 0.0 <= f1 <= 1.0


def test_high_risk_recall():
    y_true = ["violence", "violence", "normal", "loitering"]
    y_pred = ["violence", "normal", "normal", "loitering"]
    recall = compute_high_risk_recall(y_true, y_pred)
    assert recall == pytest.approx(0.5, abs=0.01)


def test_false_alarms_per_hour():
    y_true = [0, 0, 0, 1]
    y_pred = [1, 0, 0, 1]  # 1 FP
    fa = compute_false_alarms_per_hour(y_true, y_pred, total_hours=1.0)
    assert fa == pytest.approx(1.0, abs=0.01)


def test_p95_latency():
    latencies = list(range(1, 101))  # 1..100 ms
    p95 = compute_p95_latency_ms(latencies)
    assert p95 == pytest.approx(95.0, abs=1.0)


def test_confusion_matrix():
    y_true = ["a", "a", "b"]
    y_pred = ["a", "b", "b"]
    cm = compute_confusion_matrix(y_true, y_pred)
    assert cm["a"]["a"] == 1
    assert cm["a"]["b"] == 1
    assert cm["b"]["b"] == 1


def test_full_anomaly_metrics():
    y_true_binary = [1, 1, 0, 0]
    y_score = [0.8, 0.9, 0.2, 0.1]
    y_true_labels = ["violence", "loitering", "normal", "normal"]
    y_pred_labels = ["violence", "loitering", "normal", "normal"]
    latencies = [10.0, 20.0, 30.0]
    metrics = full_anomaly_metrics(y_true_binary, y_score, y_true_labels, y_pred_labels, latencies, 1.0)
    assert "auc" in metrics
    assert "macro_f1" in metrics
    assert "high_risk_recall" in metrics
    assert "false_alarms_per_hour" in metrics
    assert "p95_latency_ms" in metrics
    assert "confusion_matrix" in metrics
