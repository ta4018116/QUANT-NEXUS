from fastapi.testclient import TestClient

from app import main
from app.engine_suite import (
    catalogue_runtime_coverage,
    early_opportunity_assessment,
    run_engine,
    run_engine_suite,
    _logistic_model,
    _random_forest,
    _anomaly_detection,
    _clustering,
)


def make_candles(count=120):
    rows = []
    for i in range(count):
        close = 100 + i * 0.08 + (i % 5) * 0.025
        open_price = close - 0.025
        rows.append({
            "time": i * 60,
            "open": open_price,
            "high": close + 0.16,
            "low": open_price - 0.14,
            "close": close,
            "volume": 1000 + i * 3,
        })
    return rows


def test_all_156_engine_ids_have_runtime_adapters():
    coverage = catalogue_runtime_coverage()
    assert coverage["catalogue_engines"] == 156
    assert coverage["routed_adapters"] == 156
    assert coverage["unrouted_adapters"] == []
    assert coverage["live_trading_enabled"] is False


def test_engine_suite_returns_one_auditable_result_per_catalogue_engine():
    context = {
        "symbol": "BTCUSDT",
        "category": "spot",
        "interval": "15m",
        "candles": make_candles(),
        "closes": [x["close"] for x in make_candles()],
        "orderbook": {"bids": [[100, 12], [99.9, 10]], "asks": [[100.1, 4], [100.2, 5]]},
        "trades": [
            {"price": 100, "size": 4, "side": "BUY"},
            {"price": 100, "size": 1, "side": "SELL"},
        ],
        "regime": {"status": "ok", "trend": "UPTREND"},
        "structure": {"status": "ok", "break_of_structure": "NONE"},
        "account": {"equity": 10000},
        "positions": [],
        "closed_trades": [],
    }
    result = run_engine_suite(context)
    assert result["total_requested"] == 156
    assert len(result["results"]) == 156
    assert all(item["engine_id"] for item in result["results"])
    assert all(item["live_trading_enabled"] is False for item in result["results"])
    assert any(item["runtime"]["status"] == "computed" for item in result["results"])
    assert any(item["runtime"]["status"] == "blocked_missing_input" for item in result["results"])


def test_early_opportunity_assessment_is_bounded_and_explainable():
    rows = make_candles()
    context = {
        "symbol": "BTCUSDT",
        "category": "spot",
        "interval": "15m",
        "candles": rows,
        "orderbook": {"bids": [[100, 100]], "asks": [[100.1, 20]]},
        "trades": [
            {"price": 100, "size": 10, "side": "BUY"},
            {"price": 100, "size": 2, "side": "SELL"},
        ],
        "regime": {"status": "ok", "trend": "UPTREND"},
        "structure": {"status": "ok", "break_of_structure": "NONE"},
    }
    result = early_opportunity_assessment(context)
    assert result["status"] == "computed"
    assert 0 <= result["score"] <= 100
    assert result["max_score"] == 100
    assert result["tier"] in {
        "GOLD_EARLY", "GREEN_WATCH", "SILVER_EARLY", "NO_SETUP", "BREAKOUT_CONFIRMED"
    }
    assert isinstance(result["reasons"], list)
    assert result["live_trading_enabled"] is False


def test_engine_fails_closed_when_inputs_are_missing():
    result = run_engine("E047", {"candles": make_candles()})
    assert result["runtime"]["status"] == "blocked_missing_input"
    assert result["live_trading_enabled"] is False


def test_engine_suite_api_uses_completed_candles_and_stays_paper_only(monkeypatch):
    async def fake_klines(symbol, category, interval, limit):
        # Provider rows are newest last in this test; the endpoint discards the last in-progress bar.
        rows = []
        for i, candle in enumerate(make_candles(121)):
            rows.append([
                str(candle["time"] * 1000), str(candle["open"]), str(candle["high"]),
                str(candle["low"]), str(candle["close"]), str(candle["volume"])
            ])
        return rows, "TEST"

    async def fake_book(symbol, category):
        return [[100, 100]], [[100.1, 20]], "TEST"

    async def fake_trades(symbol, category):
        return [
            {"price": 100, "size": 10, "side": "BUY", "time": 1},
            {"price": 100, "size": 2, "side": "SELL", "time": 2},
        ], "TEST"

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    monkeypatch.setattr(main, "get_orderbook", fake_book)
    monkeypatch.setattr(main, "get_recent_trades", fake_trades)

    response = TestClient(main.app).get("/api/early-opportunity/BTCUSDT?category=spot&interval=15m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "TEST"
    assert payload["completed_candles"] == 120
    assert payload["engine_suite"]["total_requested"] == 156
    assert payload["early_opportunity"]["live_trading_enabled"] is False
    assert payload["live_trading_enabled"] is False


def test_engine_suite_rejects_unsupported_symbol_and_market():
    client = TestClient(main.app)
    assert client.get("/api/engine-suite/BTCUSD").status_code == 400
    assert client.get("/api/engine-suite/BTCUSDT?category=unknown").status_code == 400


def test_logistic_model_uses_chronological_holdout_and_reports_research_metrics():
    context = {"candles": make_candles(190)}
    result = _logistic_model(context)
    assert result["status"] == "computed"
    value = result["value"]
    assert value["training_samples"] > value["holdout_samples"] > 0
    assert 0 <= value["research_probability_up"] <= 1
    assert 0 <= value["chronological_holdout_accuracy_pct"] <= 100
    assert 0 <= value["holdout_brier_score"] <= 1
    assert "not independently calibrated" in value["warning"]


def test_random_forest_runs_deterministically_on_historical_candles():
    context = {"candles": make_candles(190)}
    first = _random_forest(context)
    second = _random_forest(context)
    assert first["status"] == "computed"
    assert first["value"]["research_vote_fraction_up"] == second["value"]["research_vote_fraction_up"]
    assert 0 <= first["value"]["research_vote_fraction_up"] <= 1


def test_anomaly_detection_and_clustering_return_bounded_market_evidence():
    context = {"candles": make_candles(120)}
    anomaly = _anomaly_detection(context)
    clusters = _clustering(context)
    assert anomaly["status"] == "computed"
    assert set(anomaly["value"]["z_scores"]) == {"return_pct", "volume", "range_pct"}
    assert clusters["status"] == "computed"
    assert sum(clusters["value"]["cluster_sizes"]) == 100


def test_smart_money_regime_and_exhaustion_adapters_are_explainable():
    context = {"candles": make_candles(120)}
    from app.engine_suite import _smc, _regime_detector, _trend_exhaustion
    assert _smc(context)["status"] == "computed"
    assert _regime_detector(context)["status"] == "computed"
    assert _trend_exhaustion(context)["status"] == "computed"


def test_risk_controls_fail_closed_and_bound_exposure():
    from app.engine_suite import _leverage_risk, _risk_approval, _dynamic_risk
    leverage = _leverage_risk({"plan": {
        "side": "LONG", "entry": 100, "stop": 95, "leverage": 3,
        "maintenance_margin_rate": 0.005
    }})
    assert leverage["status"] == "computed"
    assert leverage["value"]["estimated_liquidation_price"] < 100
    assert _risk_approval({"risk_checks": {"stop_valid": True, "daily_limit": False}})["value"]["approved"] is False
    dynamic = _dynamic_risk({
        "account": {"equity": 10000}, "plan": {"entry": 100, "stop": 95},
        "risk_pct": 1.0, "volatility_pct": 4.0, "drawdown_pct": 0
    })
    assert dynamic["status"] == "computed"
    assert dynamic["value"]["effective_risk_pct"] == 0.5


def test_slippage_fee_and_monte_carlo_adapters_use_supplied_inputs():
    from app.engine_suite import _slippage_estimate, _fee_calc, _monte_carlo
    slip = _slippage_estimate({
        "order_side": "BUY", "quantity": 3,
        "orderbook": {"asks": [[100, 2], [101, 3]]}
    })
    assert slip["status"] == "computed"
    assert slip["value"]["filled_quantity"] == 3
    fees = _fee_calc({"notional": 1000, "fee_rate": 0.001, "fee_sides": 2})
    assert fees["value"]["estimated_fee"] == 2
    mc = _monte_carlo({"strategy_returns": [0.01, -0.005, 0.02, -0.01] * 8})
    assert mc["status"] == "computed"
    assert mc["value"]["simulations"] == 300


def test_walk_forward_and_max_drawdown_use_chronological_trade_data():
    from app.engine_suite import _walk_forward, _max_drawdown
    wf = _walk_forward({"strategy_returns": [0.01, -0.005] * 15})
    assert wf["status"] == "computed"
    dd = _max_drawdown({
        "starting_balance": 10000,
        "closed_trades": [{"pnl": 100}, {"pnl": -250}, {"pnl": 50}]
    })
    assert dd["status"] == "computed"
    assert dd["value"]["max_drawdown_pct"] > 0


def test_position_monitor_and_trade_attribution_are_read_only():
    from app.engine_suite import _position_monitor, _attribution
    monitored = _position_monitor({
        "positions": [{"status":"OPEN","symbol":"BTCUSDT","side":"LONG","entry":100,
                       "quantity":2,"stop_loss":95,"take_profit":110}],
        "current_prices": {"BTCUSDT": 111}
    })
    assert monitored["status"] == "computed"
    assert monitored["value"]["positions"][0]["target_touched"] is True
    attr = _attribution({"closed_trades":[
        {"strategy":"breakout","pnl":10},{"strategy":"breakout","pnl":-2}
    ]})
    assert attr["value"]["net_pnl_by_strategy"]["breakout"] == 8


def test_signal_expiry_target_and_autonomous_research_are_fail_closed():
    from app.engine_suite import _signal_expiration, _take_profit, _autonomous_research
    expiry = _signal_expiration({
        "signal_created_at": "2026-11-27T08:00:00+00:00",
        "now_utc": "2026-11-27T08:20:00+00:00",
        "max_age_seconds": 900
    })
    assert expiry["status"] == "computed"
    assert expiry["value"]["expired"] is True
    targets = _take_profit({"plan":{"entry":100,"stop":95,"side":"LONG"},
                             "reward_risk_targets":[1.5,2.0,3.0]})
    assert targets["value"]["target_references"] == [107.5,110.0,115.0]
    research = _autonomous_research({"strategy_candidates":[{
        "name":"test-strategy","train_return":0.20,"validation_return":0.06,
        "validation_drawdown":9,"validation_trades":45
    }]})
    assert research["status"] == "computed"
    assert research["value"]["candidates"][0]["research_gate_passed"] is True
    assert research["value"]["candidates"][0]["promotion"] == "MANUAL_REVIEW_REQUIRED"


def test_operations_adapters_report_explicit_read_only_state():
    from app.engine_suite import _event_bus, _data_replay, _watchdog, _audit_log
    bus = _event_bus({"event_bus":{"published":12,"consumed":9}})
    assert bus["value"]["backlog"] == 3
    replay = _data_replay({"replay_events":[
        {"timestamp":"2026-11-27T10:02:00Z","type":"b"},
        {"timestamp":"2026-11-27T10:01:00Z","type":"a"}
    ]})
    assert replay["value"]["ordered_events"][0]["type"] == "a"
    watchdog = _watchdog({"heartbeats":{"scanner":{"age_seconds":90}},
                          "heartbeat_max_age_seconds":60})
    assert watchdog["value"]["watchdog_alert"] is True
    audit = _audit_log({"audit_events":[{"event_id":"x"},{"event_id":"x"}]})
    assert audit["value"]["duplicate_event_ids"] == 1
