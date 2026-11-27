import json
import random

from app.model_lifecycle import (
    list_model_artifacts,
    predict_direction_model,
    train_direction_model,
)


def make_candles(count=560, seed=20261127):
    rng = random.Random(seed)
    price = 100.0
    rows = []
    for index in range(count):
        open_price = price
        change = rng.gauss(0.0002, 0.008)
        close = max(1.0, open_price * (1.0 + change))
        high = max(open_price, close) * (1.0 + rng.uniform(0.0001, 0.004))
        low = min(open_price, close) * (1.0 - rng.uniform(0.0001, 0.004))
        volume = rng.uniform(500.0, 5000.0)
        rows.append({
            "time": index * 900000,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        })
        price = close
    return rows


def test_model_training_calibration_holdout_persist_and_predict(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_REGISTRY_PATH", str(tmp_path))
    monkeypatch.setenv("MODEL_REGISTRY_DURABLE", "false")

    candles = make_candles()
    result = train_direction_model(
        candles,
        symbol="BTCUSDT",
        interval="15m",
        registry_dir=tmp_path,
    )

    assert result["status"] == "trained_candidate"
    assert result["artifact_saved"] is True
    assert result["promotion"] == "MANUAL_REVIEW_REQUIRED"
    assert result["training_samples"] >= 80
    assert result["calibration_samples"] >= 20
    assert result["test_metrics"]["samples"] >= 20
    assert 0 <= result["test_metrics"]["brier_score"] <= 1

    artifacts = list_model_artifacts(tmp_path)
    assert len(artifacts) == 1
    assert artifacts[0]["model_id"] == "direction_logistic_v1"

    prediction = predict_direction_model({
        "symbol": "BTCUSDT",
        "interval": "15m",
        "candles": candles,
    })
    assert prediction is not None
    assert prediction["status"] == "computed"
    assert 0 <= prediction["value"]["research_probability_up"] <= 1
    assert prediction["value"]["artifact_persisted"] is True

    artifact_path = result["artifact_path"]
    with open(artifact_path, encoding="utf-8") as handle:
        artifact = json.load(handle)
    assert artifact["feature_version"] == "ohlcv9_v1"
    assert artifact["promotion"] == "MANUAL_REVIEW_REQUIRED"


def test_model_training_fails_closed_for_short_history(tmp_path):
    result = train_direction_model(
        make_candles(180),
        symbol="ETHUSDT",
        interval="5m",
        registry_dir=tmp_path,
    )
    assert result["status"].startswith("blocked_")
    assert not list(tmp_path.glob("*.json"))


def test_registry_does_not_return_arbitrary_files(tmp_path):
    (tmp_path / "unrelated.json").write_text("{}", encoding="utf-8")
    assert list_model_artifacts(tmp_path) == []
