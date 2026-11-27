import random

from app.engine_catalog import ENGINE_CATALOG
from app.engine_suite import run_engine


def make_candles(count=180):
    rng = random.Random(20261127)
    price = 100.0
    rows = []
    for index in range(count):
        open_price = price
        close = max(1.0, open_price * (1 + rng.uniform(-0.012, 0.014)))
        high = max(open_price, close) * 1.004
        low = min(open_price, close) * 0.996
        rows.append({
            "time": (index + 1) * 900000,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1000 + rng.uniform(0, 3000),
        })
        price = close
    return rows


def test_every_catalogue_engine_runs_individually_with_auditable_contract():
    candles = make_candles()
    context = {
        "symbol": "BTCUSDT",
        "category": "spot",
        "interval": "15m",
        "candles": candles,
        "closes": [row["close"] for row in candles],
        "orderbook": {
            "bids": [[100.0, 12.0], [99.9, 10.0]],
            "asks": [[100.1, 4.0], [100.2, 5.0]],
        },
        "trades": [
            {"price": 100.0, "size": 4.0, "side": "BUY", "time": 1},
            {"price": 100.1, "size": 1.0, "side": "SELL", "time": 2},
        ],
        "derivatives": {
            "open_interest": 1000000,
            "open_interest_change_pct": 2.5,
            "funding_rate": 0.0001,
            "long_short_ratio": 1.1,
        },
        "liquidations": [
            {
                "symbol": "BTCUSDT",
                "liquidated_position": "LONG",
                "notional_usdt": 1200,
                "bankruptcy_price": 99000,
            }
        ],
        "liquidations_aggregate": {
            "status": "ok",
            "total_liquidation_usd": 1000000,
            "long_liquidation_usd": 600000,
            "short_liquidation_usd": 400000,
        },
        "exchange_prices": {"Bybit": 100.0, "OKX": 100.1, "Binance": 99.95},
        "spot_price": 100.0,
        "futures_price": 100.2,
        "options_chain": [
            {
                "type": "CALL",
                "strike": 100,
                "days_to_expiry": 30,
                "implied_volatility": 0.5,
                "open_interest": 10,
                "contract_multiplier": 1,
                "risk_free_rate": 0.02,
            }
        ],
        "underlying_price": 100.0,
        "news_events": [
            {
                "title": "Example Bitcoin market headline",
                "summary": "Example event for adapter contract testing",
                "source": "fixture",
                "published_at": "2026-11-27T10:00:00Z",
                "url": "https://example.com/fixture",
            }
        ],
        "correlation_base_closes": [100 + i * 0.1 for i in range(100)],
        "related_closes": {
            "ETHUSDT": [50 + i * 0.05 for i in range(100)],
            "SOLUSDT": [30 + i * 0.03 for i in range(100)],
        },
        "timeframes": {
            "5m": {"timeframe": "5m", "direction": "UP", "score": 80},
            "1h": {"timeframe": "1h", "direction": "UP", "score": 75},
            "4h": {"timeframe": "4h", "direction": "RANGE", "score": 55},
        },
        "regime": {"status": "ok", "trend": "UPTREND"},
        "structure": {"status": "ok", "break_of_structure": "NONE"},
        "account": {"equity": 10000},
        "positions": [],
        "closed_trades": [{"status": "CLOSED", "pnl": 25, "strategy": "test"}],
        "current_prices": {"BTCUSDT": candles[-1]["close"]},
        "plan": {"side": "LONG", "entry": 100, "stop": 95, "leverage": 2},
        "risk_pct": 1.0,
        "volatility_pct": 1.5,
        "daily_pnl": 10,
        "daily_loss_limit_pct": 3,
        "strategy_returns": [0.01, -0.005, 0.02, -0.01] * 10,
        "entry_confirmation": {"confirmed": True},
        "risk_checks": {
            "stop_valid": True,
            "daily_limit": True,
            "paper_equity_positive": True,
        },
        "risk_approval": {"approved": True, "failed_checks": []},
        "reward_risk_targets": [1.5, 2.0, 3.0],
        "model_versions": [
            {"name": "fixture_model", "version": "test-v1", "artifact_persisted": True}
        ],
        "resource_snapshot": {"memory_pct": 20, "cpu_pct": 10},
        "cache": {"status": "ok"},
        "database": {"status": "ok"},
        "websocket": {"status": "ok"},
        "scheduled_jobs": [
            {"name": "fixture", "enabled": True, "interval_seconds": 60}
        ],
        "scheduler_backend_configured": True,
        "recent_failures": [],
        "notification_events": [
            {"type": "INFO", "title": "fixture", "message": "fixture"}
        ],
        "heartbeats": {"api": {"age_seconds": 0}},
        "event_bus": {"published": 10, "consumed": 10},
        "audit_events": [{"event_id": "fixture-1"}],
        "security_policy": {
            "trading_mode": "simulation",
            "live_trading_enabled": False,
            "exchange_trade_credentials_present": False,
            "https_enabled": True,
            "secrets_redacted": True,
            "admin_auth_enabled": True,
        },
    }

    seen = set()
    errors = []
    for item in ENGINE_CATALOG:
        result = run_engine(item["id"], context)
        assert result["engine_id"] == item["id"]
        assert result["trading_mode"] == "simulation"
        assert result["live_trading_enabled"] is False
        runtime = result["runtime"]
        assert isinstance(runtime, dict)
        assert isinstance(runtime.get("status"), str) and runtime["status"]
        seen.add(result["engine_id"])
        if runtime["status"] == "input_error":
            errors.append((item["id"], runtime.get("reason")))

    assert len(ENGINE_CATALOG) == 156
    assert len(seen) == 156
    assert errors == []


def test_watchdog_missing_heartbeat_age_is_json_safe():
    import json
    from app.engine_suite import run_engine

    result = run_engine("E156", {
        "heartbeats": {
            "api": {"age_seconds": 0},
            "background_scheduler": {"age_seconds": None},
        }
    })
    assert result["runtime"]["status"] == "computed"
    value = result["runtime"]["value"]
    assert value["heartbeat_ages_seconds"]["background_scheduler"] is None
    assert value["unknown_services"] == ["background_scheduler"]
    json.dumps(result, allow_nan=False)
