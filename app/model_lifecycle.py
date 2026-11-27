"""Persistent research-model lifecycle with chronological purging and calibration.

Artifacts are JSON (never pickle) and are kept separate by symbol/interval.
A model is a research candidate only; it is not an order authorization signal.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

FEATURE_NAMES = (
    "return_1", "return_3", "return_5", "body_pct", "close_location",
    "volume_ratio", "atr_pct", "rsi_scaled", "ema_gap",
)
FEATURE_VERSION = "ohlcv9_v1"
HORIZON_BARS = 3


def _sigmoid(value: float) -> float:
    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _safe_symbol(symbol: str) -> str:
    value = re.sub(r"[^A-Z0-9_-]", "", str(symbol or "").upper())[:32]
    return value or "UNKNOWN"


def _registry_dir() -> Path:
    return Path(os.getenv("MODEL_REGISTRY_PATH", "data/models")).expanduser()


def _artifact_path(symbol: str, interval: str, registry_dir: str | Path | None = None) -> Path:
    safe_interval = re.sub(r"[^A-Za-z0-9_-]", "", str(interval or ""))[:8] or "unknown"
    root = Path(registry_dir).expanduser() if registry_dir is not None else _registry_dir()
    return root / f"{_safe_symbol(symbol)}_{safe_interval}_direction_logistic_v1.json"


def _rsi(closes: list[float], period: int = 14) -> float:
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(value, 0.0) for value in changes[-period:]]
    losses = [max(-value, 0.0) for value in changes[-period:]]
    gain = mean(gains) if gains else 0.0
    loss = mean(losses) if losses else 0.0
    if loss <= 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def _features_at(rows: list[dict], index: int) -> list[float] | None:
    if index < 50 or index >= len(rows):
        return None
    closes = [float(x["close"]) for x in rows[: index + 1]]
    current = rows[index]
    previous = rows[index - 1]
    volume_history = [float(x["volume"]) for x in rows[index - 20:index]]
    volume_base = mean(volume_history) if volume_history else 0.0
    candle_range = float(current["high"]) - float(current["low"])
    tr_values = []
    for position in range(max(1, index - 13), index + 1):
        candle = rows[position]
        prev_close = float(rows[position - 1]["close"])
        tr_values.append(max(
            float(candle["high"]) - float(candle["low"]),
            abs(float(candle["high"]) - prev_close),
            abs(float(candle["low"]) - prev_close),
        ))
    atr = mean(tr_values) if tr_values else 0.0
    ema_fast = mean(closes[-20:])
    ema_slow = mean(closes[-50:])
    return [
        closes[-1] / closes[-2] - 1.0 if closes[-2] else 0.0,
        closes[-1] / closes[-4] - 1.0 if closes[-4] else 0.0,
        closes[-1] / closes[-6] - 1.0 if closes[-6] else 0.0,
        (float(current["close"]) - float(current["open"])) / float(current["close"]),
        (float(current["close"]) - float(current["low"])) / candle_range if candle_range > 0 else 0.5,
        float(current["volume"]) / volume_base if volume_base > 0 else 1.0,
        atr / float(current["close"]) if float(current["close"]) > 0 else 0.0,
        _rsi(closes) / 100.0,
        ema_fast / ema_slow - 1.0 if ema_slow > 0 else 0.0,
    ]


def _validated_rows(candles: list[dict]) -> list[dict]:
    valid = []
    for row in candles if isinstance(candles, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            item = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if any(not math.isfinite(v) for v in item.values()):
            continue
        if min(item["open"], item["high"], item["low"], item["close"]) <= 0 or item["volume"] < 0:
            continue
        if item["high"] < max(item["open"], item["close"], item["low"]):
            continue
        if item["low"] > min(item["open"], item["close"], item["high"]):
            continue
        valid.append(item)
    return valid


def _dataset(rows: list[dict]) -> list[tuple[list[float], int]]:
    data = []
    for index in range(50, len(rows) - HORIZON_BARS):
        features = _features_at(rows, index)
        if features is None:
            continue
        label = int(rows[index + HORIZON_BARS]["close"] > rows[index]["close"])
        data.append((features, label))
    return data


def _standardize(train, samples):
    width = len(FEATURE_NAMES)
    means = [mean(row[0][j] for row in train) for j in range(width)]
    scales = [pstdev(row[0][j] for row in train) or 1.0 for j in range(width)]
    normalized = [
        ([(features[j] - means[j]) / scales[j] for j in range(width)], label)
        for features, label in samples
    ]
    return normalized, means, scales


def _fit_logistic(train, epochs: int = 320):
    width = len(FEATURE_NAMES)
    weights = [0.0] * width
    bias = 0.0
    learning_rate = 0.035
    l2 = 0.02
    for _ in range(epochs):
        gradients = [0.0] * width
        bias_gradient = 0.0
        for features, label in train:
            error = _sigmoid(sum(weights[j] * features[j] for j in range(width)) + bias) - label
            for j, value in enumerate(features):
                gradients[j] += error * value
            bias_gradient += error
        count = max(1, len(train))
        weights = [weights[j] - learning_rate * (gradients[j] / count + l2 * weights[j]) for j in range(width)]
        bias -= learning_rate * bias_gradient / count
    return weights, bias


def _fit_calibrator(logits: list[float], labels: list[int]) -> tuple[float, float] | None:
    if len(logits) < 20 or len(set(labels)) < 2:
        return None
    scale = 1.0
    bias = 0.0
    learning_rate = 0.02
    for _ in range(400):
        grad_scale = 0.0
        grad_bias = 0.0
        for value, label in zip(logits, labels):
            error = _sigmoid(scale * value + bias) - label
            grad_scale += error * value
            grad_bias += error
        n = len(logits)
        scale -= learning_rate * (grad_scale / n + 0.001 * (scale - 1.0))
        bias -= learning_rate * grad_bias / n
        scale = max(0.05, min(5.0, scale))
        bias = max(-5.0, min(5.0, bias))
    return scale, bias


def _auc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(probabilities, labels), key=lambda x: x[0])
    rank_sum = 0.0
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][0] == ordered[index][0]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        rank_sum += average_rank * sum(label for _, label in ordered[index:end])
        index = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _metrics(labels: list[int], probabilities: list[float], baseline: float) -> dict:
    if not labels:
        return {}
    brier = mean((p - y) ** 2 for p, y in zip(probabilities, labels))
    accuracy = mean(int((p >= 0.5) == bool(y)) for p, y in zip(probabilities, labels))
    log_loss = mean(
        -(y * math.log(max(1e-8, min(1 - 1e-8, p))) +
          (1 - y) * math.log(max(1e-8, min(1 - 1e-8, 1 - p))))
        for p, y in zip(probabilities, labels)
    )
    return {
        "samples": len(labels),
        "accuracy_pct": round(accuracy * 100, 3),
        "brier_score": round(brier, 6),
        "baseline_brier_score": round(mean((baseline - y) ** 2 for y in labels), 6),
        "log_loss": round(log_loss, 6),
        "roc_auc": round(_auc(labels, probabilities), 6) if _auc(labels, probabilities) is not None else None,
        "base_rate_up_pct": round(mean(labels) * 100, 3),
    }


def train_direction_model(
    candles: list[dict],
    symbol: str,
    interval: str,
    registry_dir: str | Path | None = None,
) -> dict:
    """Train, calibrate and validate a simple directional model on completed OHLCV."""
    rows = _validated_rows(candles)
    dataset = _dataset(rows)
    if len(dataset) < 160:
        return {
            "status": "blocked_insufficient_history",
            "required_samples": 160,
            "available_samples": len(dataset),
            "required_input": "at least 214 valid completed candles",
        }

    total = len(dataset)
    train_end = int(total * 0.65)
    calibration_end = int(total * 0.82)
    train_raw = dataset[: max(0, train_end - HORIZON_BARS)]
    calibration_raw = dataset[train_end: max(train_end, calibration_end - HORIZON_BARS)]
    test_raw = dataset[calibration_end:]
    if len(train_raw) < 80 or len(calibration_raw) < 20 or len(test_raw) < 20:
        return {"status": "blocked_insufficient_split", "samples": total}

    train, means, scales = _standardize(train_raw, train_raw)
    calibration, _, _ = _standardize(train_raw, calibration_raw)
    test, _, _ = _standardize(train_raw, test_raw)
    weights, bias = _fit_logistic(train)

    logit = lambda features: sum(weights[j] * features[j] for j in range(len(weights))) + bias
    calibration_logits = [logit(features) for features, _ in calibration]
    calibration_labels = [label for _, label in calibration]
    calibrator = _fit_calibrator(calibration_logits, calibration_labels)
    if calibrator is None:
        return {"status": "blocked_calibration_data", "samples": total, "calibration_samples": len(calibration)}

    calibration_scale, calibration_bias = calibrator
    test_labels = [label for _, label in test]
    raw_probabilities = [_sigmoid(logit(features)) for features, _ in test]
    calibrated_probabilities = [
        _sigmoid(calibration_scale * logit(features) + calibration_bias) for features, _ in test
    ]
    baseline_rate = mean(label for _, label in train)
    metrics = _metrics(test_labels, calibrated_probabilities, baseline_rate)
    raw_metrics = _metrics(test_labels, raw_probabilities, baseline_rate)
    promotion_eligible = bool(
        metrics.get("brier_score") is not None
        and metrics["brier_score"] < metrics["baseline_brier_score"]
        and metrics.get("roc_auc") is not None
        and metrics["roc_auc"] > 0.52
        and metrics["samples"] >= 20
    )

    latest_features = _features_at(rows, len(rows) - 1)
    latest_normalized = [(latest_features[j] - means[j]) / scales[j] for j in range(len(FEATURE_NAMES))]
    latest_probability = _sigmoid(
        calibration_scale * logit(latest_normalized) + calibration_bias
    )
    artifact = {
        "model_id": "direction_logistic_v1",
        "symbol": _safe_symbol(symbol),
        "interval": str(interval),
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "horizon_bars": HORIZON_BARS,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "weights": weights,
        "bias": bias,
        "means": means,
        "scales": scales,
        "calibration": {"scale": calibration_scale, "bias": calibration_bias},
        "training_samples": len(train),
        "calibration_samples": len(calibration),
        "test_metrics": metrics,
        "raw_test_metrics": raw_metrics,
        "promotion_eligible": promotion_eligible,
        "promotion": "MANUAL_REVIEW_REQUIRED",
        "data_rows": len(rows),
    }
    path = _artifact_path(symbol, interval, registry_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(artifact, handle, separators=(",", ":"), allow_nan=False)
            temporary = handle.name
        os.replace(temporary, path)
        saved = True
    except OSError as exc:
        return {
            "status": "artifact_save_failed",
            "reason": type(exc).__name__,
            "metrics": metrics,
            "promotion_eligible": False,
        }

    return {
        "status": "trained_candidate",
        "model_id": artifact["model_id"],
        "symbol": artifact["symbol"],
        "interval": artifact["interval"],
        "training_samples": len(train),
        "calibration_samples": len(calibration),
        "test_metrics": metrics,
        "raw_test_metrics": raw_metrics,
        "calibration": artifact["calibration"],
        "latest_research_probability_up": round(latest_probability, 6),
        "promotion_eligible": promotion_eligible,
        "promotion": "MANUAL_REVIEW_REQUIRED",
        "artifact_saved": saved,
        "artifact_path": str(path),
        "artifact_format": "JSON",
        "durable_storage_verified": os.getenv("MODEL_REGISTRY_DURABLE", "false").lower() == "true",
        "warning": "Single logistic research model; calibrated on a chronological calibration slice, tested on a later holdout, and never authorizes orders.",
    }


def predict_direction_model(context: dict) -> dict | None:
    symbol = str(context.get("symbol") or "")
    interval = str(context.get("interval") or "")
    path = _artifact_path(symbol, interval)
    if not path.is_file():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        rows = _validated_rows(context.get("candles") or [])
        features = _features_at(rows, len(rows) - 1)
        if features is None or artifact.get("feature_version") != FEATURE_VERSION:
            return None
        means = artifact["means"]
        scales = artifact["scales"]
        weights = artifact["weights"]
        if not (len(features) == len(means) == len(scales) == len(weights) == len(FEATURE_NAMES)):
            return None
        normalized = [(features[j] - means[j]) / (scales[j] or 1.0) for j in range(len(features))]
        raw_logit = sum(weights[j] * normalized[j] for j in range(len(weights))) + float(artifact["bias"])
        calibration = artifact["calibration"]
        probability = _sigmoid(float(calibration["scale"]) * raw_logit + float(calibration["bias"]))
        return {
            "status": "computed",
            "method": "persisted_logistic_model_with_chronological_calibration_and_holdout",
            "value": {
                "model": artifact["model_id"],
                "research_probability_up": round(probability, 6),
                "horizon_bars": HORIZON_BARS,
                "test_metrics": artifact.get("test_metrics"),
                "trained_at": artifact.get("trained_at"),
                "promotion": artifact.get("promotion", "MANUAL_REVIEW_REQUIRED"),
                "promotion_eligible": artifact.get("promotion_eligible") is True,
                "artifact_persisted": True,
                "durable_storage_verified": os.getenv("MODEL_REGISTRY_DURABLE", "false").lower() == "true",
                "warning": "Research candidate only; calibration and historical metrics do not guarantee future edge.",
            },
        }
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return None


def list_model_artifacts(registry_dir: str | Path | None = None) -> list[dict]:
    root = Path(registry_dir).expanduser() if registry_dir is not None else _registry_dir()
    if not root.exists():
        return []
    output = []
    for path in sorted(root.glob("*_direction_logistic_v1.json")):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            output.append({
                "model_id": artifact.get("model_id"),
                "symbol": artifact.get("symbol"),
                "interval": artifact.get("interval"),
                "trained_at": artifact.get("trained_at"),
                "training_samples": artifact.get("training_samples"),
                "calibration_samples": artifact.get("calibration_samples"),
                "test_metrics": artifact.get("test_metrics"),
                "promotion": artifact.get("promotion"),
                "promotion_eligible": artifact.get("promotion_eligible") is True,
                "artifact_path": str(path),
                "artifact_format": "JSON",
                "durable_storage_verified": os.getenv("MODEL_REGISTRY_DURABLE", "false").lower() == "true",
            })
        except (OSError, ValueError, TypeError):
            continue
    return output
