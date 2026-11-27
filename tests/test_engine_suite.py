import pytest
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
    assert coverage["callable_adapter_coverage_pct"] == 100
    assert coverage["callable_adapters"] == 156
    assert coverage["active_runtime_adapters"] == 0
    assert coverage["external_or_model_blocked_ids"] == []
    assert coverage["catalogue_status_counts"]["planned"] == 0
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


def test_market_ingestion_activates_only_with_provider_timestamp_and_fresh_source():
    from app.engine_readiness import build_engine_readiness

    context={"candles":make_candles(80),"symbol":"BTCUSDT","category":"spot","interval":"15m",
             "provider":"OKX","source_timestamp":"2026-11-27T12:00:00+00:00",
             "source_health":"healthy","market_snapshot":{
                 "provider":"OKX","source_timestamp":"2026-11-27T12:00:00+00:00",
                 "interval":"15m","frequency":"intraday","freshness_status":"fresh","age_seconds":10,
             }}
    suite=run_engine_suite(context,["E001"])
    readiness=build_engine_readiness(suite,market_provider="OKX",
        provider_health={"market_data":{"status":"ok"}},market_snapshot=context["market_snapshot"])
    item=readiness["engines"][0]
    assert item["status"]=="ACTIVE"
    assert item["test_result"]["status"]=="passed"
    assert item["source_evidence"]["market_snapshot_provider"]=="OKX"


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
    async def fake_enrichment(symbol, category, interval, candles):
        return {}, {"derivatives":{"status":"unavailable"},"cross_market":{"status":"unavailable"}}

    monkeypatch.setattr(main, "get_recent_trades", fake_trades)
    monkeypatch.setattr(main, "collect_engine_enrichment", fake_enrichment)

    response = TestClient(main.app).get("/api/early-opportunity/BTCUSDT?category=spot&interval=15m")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "TEST"
    assert payload["completed_candles"] == 120
    assert payload["engine_suite"]["total_requested"] == 156
    assert payload["engine_readiness"]["total"] == 156
    assert sum(payload["engine_readiness"]["counts"][key] for key in ("ACTIVE", "PARTIAL", "BLOCKED", "PLANNED")) == 156
    assert all("test_result" in item and "source_evidence" in item for item in payload["engine_readiness"]["engines"])
    assert payload["engine_readiness"]["live_trading_enabled"] is False
    assert payload["early_opportunity"]["live_trading_enabled"] is False
    assert payload["live_trading_enabled"] is False


def test_coverage_read_endpoint_never_delivers_opportunity_notifications(monkeypatch):
    import time
    delivered = []

    async def fake_klines(symbol, category, interval, limit):
        now_ms = int(time.time() * 1000)
        rows=[]
        for i, candle in enumerate(make_candles(121)):
            rows.append([str(now_ms - (120-i)*900_000), str(candle["open"]), str(candle["high"]),
                         str(candle["low"]), str(candle["close"]), str(candle["volume"])])
        return rows, "TEST"

    async def fake_book(symbol, category):
        return [[100, 100]], [[100.1, 20]], "TEST"

    async def fake_trades(symbol, category):
        return [{"price":100,"size":10,"side":"BUY"}], "TEST"

    async def fake_enrichment(symbol, category, interval, candles):
        return {}, {"derivatives":{"status":"unavailable"},"cross_market":{"status":"unavailable"}}

    async def fake_news(symbol):
        return [], {}

    async def fake_delivery(client, event):
        delivered.append(event)
        return {"status":"sent"}

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    monkeypatch.setattr(main, "get_orderbook", fake_book)
    monkeypatch.setattr(main, "get_recent_trades", fake_trades)
    monkeypatch.setattr(main, "collect_engine_enrichment", fake_enrichment)
    monkeypatch.setattr(main, "_rss_news_events", fake_news)
    monkeypatch.setattr(main, "early_opportunity_assessment", lambda context: {"status":"computed","score":80})
    monkeypatch.setattr(main, "deliver_notification", fake_delivery)

    response = TestClient(main.app).get("/api/engine-suite/coverage")
    assert response.status_code == 200
    assert response.json()["live_trading_enabled"] is False
    assert delivered == []


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


def test_technical_price_action_engines_activate_only_after_their_acceptance_paths_pass():
    from datetime import datetime, timezone
    from app.engine_readiness import build_engine_readiness

    now = datetime.now(timezone.utc).isoformat()
    base = make_candles(120)
    contexts = {
        "E011": {"candles": base},
        "E012": {"candles": base},
        "E013": {"candles": base},
        "E014": {"candles": [
            *base[:-3],
            {"open": 100, "high": 101, "low": 98, "close": 99, "volume": 1000},
            {"open": 100, "high": 103, "low": 99.5, "close": 102, "volume": 1800},
            base[-1],
        ]},
        "E015": {"candles": [
            {"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
            {"open": 103, "high": 105, "low": 102, "close": 104, "volume": 1100},
            {"open": 106, "high": 108, "low": 105, "close": 107, "volume": 1200},
        ]},
        "E016": {"candles": [
            *base[:-1],
            {"open": base[-1]["close"], "high": base[-1]["close"] + 1.2,
             "low": base[-1]["close"] - 0.2, "close": base[-1]["close"] + 1.0,
             "volume": 5000},
        ]},
        "E020": {"candles": [
            {"open": 150, "high": 200 if i == 0 else 160, "low": 100 if i == 0 else 140,
             "close": 151, "volume": 1000}
            for i in range(20)
        ]},
    }
    for engine_id, context in contexts.items():
        context["symbol"] = "BTCUSDT"
        context["market_snapshot"] = {"freshness_status": "fresh", "source_timestamp": now}
        run = run_engine(engine_id, context)
        assert run["runtime"]["status"] == "computed", engine_id
        suite = {"results": [run]}
        readiness = build_engine_readiness(
            suite,
            market_provider="Bybit",
            provider_health={"market_data": {"status": "ok"}},
            market_snapshot={"freshness_status": "fresh", "source_timestamp": now},
        )
        item = next(row for row in readiness["engines"] if row["id"] == engine_id)
        assert item["status"] == "ACTIVE", (engine_id, item["readiness_reasons"])

    # A zero-volume breakout is not supported by the named volume-confirmed
    # contract and therefore must not activate on price-only input.
    no_volume = list(contexts["E016"]["candles"])
    no_volume[-1] = {**no_volume[-1], "volume": 0}
    assert run_engine("E016", {"candles": no_volume})["runtime"]["status"] == "blocked_missing_input"


def test_multi_timeframe_engines_require_fresh_completed_source_stamped_frames():
    from datetime import datetime, timedelta, timezone
    from app.engine_suite import _timeframes, _higher_timeframe, _lower_timeframe, _regime_timeframe_sync

    now = datetime.now(timezone.utc)
    frames = {
        "15m": {"timeframe":"15m", "direction":"UP", "score":70,
                "last_completed_at":(now-timedelta(minutes=4)).isoformat()},
        "4h": {"timeframe":"4h", "direction":"DOWN", "score":35,
               "last_completed_at":(now-timedelta(minutes=40)).isoformat()},
    }
    result = _timeframes({"timeframes":frames})
    assert result["status"] == "computed"
    assert result["value"]["frames_used"] == ["15m", "4h"]
    assert _higher_timeframe({"timeframes":frames})["status"] == "computed"
    assert _lower_timeframe({"timeframes":frames})["status"] == "computed"
    assert _regime_timeframe_sync({"timeframes":frames})["status"] == "computed"

    stale = {**frames, "4h":{**frames["4h"],
                              "last_completed_at":(now-timedelta(hours=10)).isoformat()}}
    assert _higher_timeframe({"timeframes":stale})["status"] == "blocked_missing_input"
    assert _timeframes({"timeframes":{"15m":frames["15m"], "4h":{"timeframe":"4h", "direction":"UP"}}})["status"] == "blocked_missing_input"


def test_volume_anomaly_requires_real_positive_baseline_and_uses_completed_bars():
    from app.engine_suite import _volume
    rows = make_candles(30)
    rows[-1]["volume"] = 3000
    result = _volume({"candles":rows})
    assert result["status"] == "computed"
    assert result["value"]["volume_zscore"] > 2.5
    assert result["value"]["anomaly"] is True
    assert _volume({"candles":[{**row,"volume":0} for row in rows]})["status"] == "blocked_missing_input"


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


def test_reward_risk_and_take_profit_engines_use_explicit_paper_plan_inputs():
    good = run_engine("E074", {"plan":{"side":"LONG","entry":100,"stop":95,"target":110}})
    assert good["runtime"]["status"] == "computed"
    assert good["runtime"]["value"]["reward_risk_ratio"] == 2
    assert good["runtime"]["value"]["meets_minimum"] is True
    wrong_side = run_engine("E074", {"plan":{"side":"LONG","entry":100,"stop":95,"target":90}})
    assert wrong_side["runtime"]["status"] == "blocked_missing_input"

    targets = run_engine("E077", {
        "plan":{"entry":100,"stop":95,"side":"LONG"},
        "reward_risk_targets":[1.5,2.0],
    })
    assert targets["runtime"]["status"] == "computed"
    assert targets["runtime"]["value"]["target_references"] == [107.5,110.0]
    assert targets["live_trading_enabled"] is False


def test_readiness_conflict_and_ranking_adapters_use_supplied_engine_evidence():
    confirmed = {"entry_confirmation":{"state":"CONFIRMED"},
                 "risk_approval":{"approved":True}}
    for engine_id in ("E079", "E085"):
        ready = run_engine(engine_id, confirmed)
        assert ready["runtime"]["status"] == "computed"
        assert ready["runtime"]["value"]["ready"] is True
        assert run_engine(engine_id, {**confirmed,"risk_approval":{"approved":False}})["runtime"]["value"]["ready"] is False

    candles = make_candles(120)
    conflict = run_engine("E081", {
        "candles":candles,
        "orderbook":{"bids":[[100,1]],"asks":[[101,100]]},
    })
    assert conflict["runtime"]["status"] == "computed"
    assert conflict["runtime"]["value"]["conflict"] is True

    ranked = run_engine("E082", {"opportunity_candidates":[
        {"symbol":"AAAUSDT","score":40,"tier":"SILVER"},
        {"symbol":"BBBUSDT","score":80,"tier":"GOLD"},
    ]})
    assert ranked["runtime"]["status"] == "computed"
    assert ranked["runtime"]["value"]["ranked"][0]["symbol"] == "BBBUSDT"


def test_volatility_stop_daily_limit_and_risk_gate_have_paper_acceptance_cases():
    missing_side = run_engine("E095", {"candles":make_candles(80)})
    assert missing_side["runtime"]["status"] == "blocked_missing_input"
    long_stop = run_engine("E095", {
        "candles":make_candles(80),"plan":{"side":"LONG"}
    })
    short_stop = run_engine("E095", {
        "candles":make_candles(80),"plan":{"side":"SHORT"}
    })
    last_price=make_candles(80)[-1]["close"]
    assert long_stop["runtime"]["value"]["stop_reference"] < last_price
    assert short_stop["runtime"]["value"]["stop_reference"] > last_price

    limit = run_engine("E098", {
        "account":{"equity":10000},"daily_pnl":-301,"daily_loss_limit_pct":3
    })
    assert limit["runtime"]["status"] == "computed"
    assert limit["runtime"]["value"]["limit_breached"] is True

    approval = run_engine("E100", {"risk_checks":{"equity":True,"stop":True}})
    assert approval["runtime"]["status"] == "computed"
    assert approval["runtime"]["value"]["approved"] is True
    assert run_engine("E100", {})["runtime"]["status"] == "blocked_missing_input"


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


def test_remaining_backtest_metrics_and_optimization_adapters():
    from app.engine_suite import _win_rate, _profit_factor, _expectancy, _strategy_optimizer, _parameter_optimizer
    trades = [{"pnl": 12}, {"pnl": -4}, {"pnl": 8}, {"pnl": 0}]
    win = _win_rate({"closed_trades": trades})
    factor = _profit_factor({"closed_trades": trades})
    expectancy = _expectancy({"closed_trades": trades})
    assert win["value"]["win_rate_pct"] == 50
    assert factor["value"]["profit_factor"] == 5
    assert expectancy["value"]["expectancy_per_trade"] == 4
    optimizer = _strategy_optimizer({"strategy_candidates": [
        {"name":"A","validation_return":0.15,"validation_drawdown":8,"validation_trades":45},
        {"name":"B","validation_return":0.20,"validation_drawdown":25,"validation_trades":80}
    ]})
    assert optimizer["value"]["selected_for_manual_review"]["name"] == "A"
    params = _parameter_optimizer({"parameter_trials": [
        {"parameters":{"fast":10},"validation_score":0.2,"validation_trades":45},
        {"parameters":{"fast":20},"validation_score":0.3,"validation_trades":35}
    ]})
    assert params["value"]["best_trial"]["parameters"]["fast"] == 20


def test_security_news_liquidation_and_scheduler_adapters_are_fail_closed():
    from app.engine_suite import _security, _news_events, _liquidation_heatmap, _scheduler
    security = _security({"security_policy":{
        "trading_mode":"simulation","live_trading_enabled":False,
        "exchange_trade_credentials_present":False,"https_enabled":True,
        "secrets_redacted":True,"admin_auth_enabled":True
    }})
    assert security["value"]["secure"] is True
    news = _news_events({"news_events":[
        {"title":"Exchange announces new listing","source":"verified","published_at":"2026-11-27T00:00:00Z"}
    ]})
    assert news["value"]["events"][0]["sentiment"] == "POSITIVE"
    heat = _liquidation_heatmap({"liquidations":[
        {"price":100,"notional_usdt":1000},{"price":110,"notional_usdt":2000}
    ]})
    assert heat["status"] == "computed"
    scheduler = _scheduler({"scheduled_jobs":[{"name":"scan","interval_seconds":5,"enabled":True}],
                            "scheduler_backend_configured":False})
    assert scheduler["value"]["enabled_jobs"] == 1
    assert scheduler["value"]["scheduler_backend_configured"] is False


def test_news_feed_stays_blocked_but_sequence_models_run_from_supplied_candles():
    from app.engine_suite import _news_events
    context = {"candles": make_candles(190)}
    assert _news_events({})["status"] == "blocked_missing_input"
    assert run_engine("E047", context)["runtime"]["status"] == "computed"
    assert run_engine("E048", context)["runtime"]["status"] == "computed"


def test_options_greeks_and_implied_volatility_are_numerically_consistent():
    from app.engine_suite import _options_analytics, _implied_volatility_engine, _gamma_exposure
    context = {
        "underlying_price": 100,
        "options_chain": [
            {"symbol":"TEST-C100","type":"CALL","strike":100,"days_to_expiry":30,
             "implied_volatility":0.25,"open_interest":1000,"contract_multiplier":1,
             "dealer_position_sign":-1},
            {"symbol":"TEST-P100","type":"PUT","strike":100,"days_to_expiry":30,
             "implied_volatility":0.25,"open_interest":500,"contract_multiplier":1,
             "dealer_position_sign":1},
        ]
    }
    analytics = _options_analytics(context)
    iv = _implied_volatility_engine(context)
    gex = _gamma_exposure(context)
    assert analytics["status"] == iv["status"] == gex["status"] == "computed"
    assert analytics["value"]["count"] == 2
    assert analytics["value"]["contracts"][0]["gamma"] > 0
    assert 0 < iv["value"]["mean_iv"] < 2
    assert gex["value"]["net_gamma_available"] is True
    assert gex["value"]["net_gamma_exposure_per_1pct_move"] is not None


def test_implied_volatility_can_be_inverted_from_mid_price():
    from app.engine_suite import _bs_price, _implied_volatility
    spot, strike, years, rate, volatility = 100, 105, 0.5, 0.03, 0.32
    market_price = _bs_price(spot, strike, years, rate, volatility, True)
    recovered = _implied_volatility(market_price, spot, strike, years, rate, True)
    assert recovered == pytest.approx(volatility, rel=1e-5)


def test_deep_learning_mlp_and_q_learning_use_time_ordered_holdouts():
    from app.engine_suite import _deep_learning_mlp, _rl_agent
    context = {"candles": make_candles(190)}
    mlp = _deep_learning_mlp(context)
    assert mlp["status"] == "computed"
    assert mlp["value"]["training_samples"] > mlp["value"]["holdout_samples"] > 0
    assert 0 <= mlp["value"]["research_score_up"] <= 1
    assert 0 <= mlp["value"]["chronological_holdout_accuracy_pct"] <= 100
    rl = _rl_agent(context)
    assert rl["status"] == "computed"
    assert rl["value"]["training_transitions"] > rl["value"]["holdout_transitions"] > 0
    assert set(rl["value"]["holdout_action_counts"]) == {"LONG", "SHORT", "FLAT"}
    assert "Toy OHLCV simulator" in rl["value"]["warning"]


def test_latest_completed_candle_features_are_used_for_live_model_inference():
    from app.engine_suite import _live_market_features, _candles, _ml_dataset
    rows = make_candles(190)
    context = {"candles": rows}
    live, error = _live_market_features(context)
    dataset, dataset_error = _ml_dataset(context)
    assert error is None and dataset_error is None
    expected = rows[-1]["close"] / rows[-2]["close"] - 1
    assert live[0] == pytest.approx(expected)
    assert live[0] != pytest.approx(dataset[-1][0][0])


def test_xgboost_style_classifier_runs_second_order_boosting_on_time_holdout():
    from app.engine_suite import _xgboost_classifier
    result = _xgboost_classifier({"candles": make_candles(190)})
    assert result["status"] == "computed"
    value = result["value"]
    assert value["model"] == "xgboost_style_second_order_gradient_boosted_trees"
    assert value["training_samples"] > value["holdout_samples"] > 0
    assert 0 <= value["research_score_up"] <= 1
    assert "not the upstream XGBoost library" in value["warning"]


def test_lstm_and_transformer_sequence_research_adapters_run_chronological_holdouts():
    from app.engine_suite import _lstm_forecast, _transformer_forecast
    context = {"candles": make_candles(190)}
    lstm = _lstm_forecast(context)
    transformer = _transformer_forecast(context)
    assert lstm["status"] == transformer["status"] == "computed"
    for result in (lstm, transformer):
        value = result["value"]
        assert value["training_sequences"] > value["holdout_sequences"] > 0
        assert 0 <= value["research_score_up"] <= 1
        assert 0 <= value["chronological_holdout_accuracy_pct"] <= 100
        assert 0 <= value["holdout_brier_score"] <= 1
        assert "only" in value["warning"]

def test_engine_specific_handlers_run_instead_of_generic_fallbacks():
    from app.engine_suite import _arbitrage

    candles = make_candles(190)
    quality = run_engine("E006", {"candles": candles})
    assert quality["runtime"]["status"] == "computed"
    assert quality["runtime"]["value"]["quality_passed"] is True

    lstm = run_engine("E047", {"candles": candles})
    assert lstm["runtime"]["status"] == "computed"
    assert lstm["runtime"]["value"]["model"].startswith("lstm_")

    spot = run_engine("E042", {"category":"spot","candles":candles})
    futures = run_engine("E041", {"category":"spot","candles":candles})
    assert spot["runtime"]["status"] == "computed"
    assert futures["runtime"]["status"] == "blocked_missing_input"


def test_cross_market_correlation_uses_aligned_base_series():
    from app.engine_suite import _cross_market_correlation

    base = [100 + i for i in range(100)]
    related = [200 + 2*i for i in range(100)]
    result = _cross_market_correlation({
        "closes":[999,998,997],
        "correlation_base_closes":base,
        "related_closes":{"ETHUSDT":related},
    })
    assert result["status"] == "computed"
    assert result["value"]["ETHUSDT"]["samples"] == 99
    assert result["value"]["ETHUSDT"]["correlation"] == pytest.approx(1.0)


def test_arbitrage_does_not_claim_net_edge_without_verified_execution_costs():
    from app.engine_suite import _arbitrage

    result = _arbitrage({"exchange_prices":{"Bybit":100.0,"OKX":101.0}})
    assert result["status"] == "computed"
    assert result["value"]["gross_spread_pct"] == pytest.approx(1.0)
    assert result["value"]["estimated_net_spread_pct"] is None
    assert result["value"]["positive_after_costs"] is None
    assert result["value"]["execution_permitted"] is False

    verified = _arbitrage({
        "exchange_prices":{"Bybit":100.0,"OKX":101.0},
        "execution_costs_verified":True,
        "round_trip_fee_pct":0.1,
        "round_trip_slippage_pct":0.05,
    })
    assert verified["value"]["estimated_net_spread_pct"] == pytest.approx(0.85)


def test_agent_consensus_can_build_transparent_rule_agents_from_market_inputs():
    from app.engine_suite import _agents

    candles = make_candles(120)
    result = _agents({
        "candles":candles,
        "orderbook":{"bids":[[110,100]],"asks":[[110.1,10]]},
    })
    assert result["status"] == "computed"
    assert result["value"]["agents"] >= 2
    assert result["value"]["independence"].startswith("shared snapshot")

