from app.engine_suite import run_engine


def candles(count=80):
    rows = []
    for i in range(count):
        close = 100 + i * 0.1
        rows.append({
            "time": (count-i) * 900000,
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1000 + i,
        })
    return rows


def test_market_ingestion_requires_provider_identity_and_valid_candles():
    missing = run_engine("E001", {"candles": candles(), "symbol": "BTCUSDT"})
    assert missing["runtime"]["status"] == "blocked_missing_input"
    assert "provider" in missing["runtime"]["missing_inputs"]

    good = run_engine("E001", {
        "candles": candles(), "provider": "OKX",
        "symbol": "BTCUSDT", "category": "spot", "interval": "15m",
        "source_health": "ok",
    })
    assert good["runtime"]["status"] == "computed"
    assert good["runtime"]["value"]["provider"] == "OKX"
    assert good["runtime"]["value"]["valid_candles"] == 80


def test_data_normalization_sorts_deduplicates_and_rejects_invalid_rows():
    rows = candles(40)
    rows.append(dict(rows[0]))
    rows.append({"time": "bad", "open": 1})
    result = run_engine("E005", {"candles": rows})
    assert result["runtime"]["status"] == "computed"
    value = result["runtime"]["value"]
    assert value["ordered"] is True
    assert value["input_rows"] == 42
    assert value["normalized_rows"] == 40
    assert value["duplicate_timestamps_removed"] == 1
    assert value["rejected_rows"] == 1


def test_liquidity_requires_two_sided_uncrossed_book_and_reports_spread():
    blocked = run_engine("E003", {"orderbook": {"bids": [[100, 5]], "asks": []}})
    assert blocked["runtime"]["status"] == "blocked_missing_input"

    good = run_engine("E003", {
        "orderbook": {
            "bids": [[100, 5], [99.9, 4]],
            "asks": [[100.1, 3], [100.2, 2]],
            "provider": "OKX",
        }
    })
    assert good["runtime"]["status"] == "computed"
    value = good["runtime"]["value"]
    assert value["best_bid"] == 100
    assert value["best_ask"] == 100.1
    assert value["spread_bps"] > 0
    assert value["total_depth_notional"] > 0


def test_volatility_engine_reports_atr_and_never_invents_missing_candles():
    blocked = run_engine("E004", {"candles": []})
    assert blocked["runtime"]["status"] == "blocked_missing_input"

    good = run_engine("E004", {"candles": candles(80), "interval": "15m"})
    assert good["runtime"]["status"] == "computed"
    value = good["runtime"]["value"]
    assert value["atr14"] > 0
    assert value["atr_pct"] > 0
    assert value["volatility_state"] in {"LOW", "NORMAL", "HIGH"}
    assert good["live_trading_enabled"] is False
