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
    normalized = value["normalized_candles"]
    timestamps = [row["time"] for row in normalized]
    assert timestamps == sorted(set(timestamps))
    assert value["timestamp_policy"] == "source_epoch_preserved_and_sorted"


def test_data_engines_accept_raw_exchange_rows_without_losing_provider_fields():
    raw_rows = [[str((80-i)*900000), "100", "101", "99", "100.5", "12"]
                for i in range(40)]
    normalized = run_engine("E005", {"raw_candle_rows": raw_rows})
    quality = run_engine("E006", {"raw_candle_rows": raw_rows})
    assert normalized["runtime"]["status"] == "computed"
    assert normalized["runtime"]["value"]["normalized_rows"] == 40
    assert quality["runtime"]["status"] == "computed"
    assert quality["runtime"]["value"]["source_timestamp_order"] == "descending"
    assert quality["runtime"]["value"]["quality_passed"] is True


def test_data_quality_checks_raw_rows_before_filtering():
    rows = list(reversed(candles(20)))
    rows[5]["time"] = rows[4]["time"]
    rows[9]["time"] = rows[8]["time"] - 1
    rows[12]["high"] = rows[12]["low"] - 1
    rows.append({"time": "bad", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 1})

    result = run_engine("E006", {"candles": rows})
    assert result["runtime"]["status"] == "computed"
    value = result["runtime"]["value"]
    assert value["candles"] == 21
    assert value["duplicate_timestamps"] == 1
    assert value["timestamps_ordered"] is False
    assert value["invalid_timestamp_rows"] == 1
    assert value["invalid_ohlc_rows"] == 1
    assert value["quality_passed"] is False


def test_trend_engine_requires_50_bars_and_classifies_ema_and_slope():
    insufficient = run_engine("E009", {"candles": candles(49)})
    assert insufficient["runtime"]["status"] == "blocked_missing_input"

    rising = run_engine("E009", {"candles": candles(80)})
    falling_rows = candles(80)
    falling_rows.reverse()
    falling = run_engine("E009", {"candles": falling_rows})
    flat_rows = [{**row, "open": 100, "high": 101, "low": 99, "close": 100}
                 for row in candles(80)]
    flat = run_engine("E009", {"candles": flat_rows})

    assert rising["runtime"]["status"] == "computed"
    assert rising["runtime"]["value"]["direction"] == "UP"
    assert falling["runtime"]["value"]["direction"] == "DOWN"
    assert flat["runtime"]["value"]["direction"] == "RANGE"
    assert rising["live_trading_enabled"] is False


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
