import asyncio

from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app import main


def _trend_rows(count=121):
    rows = []
    base_time = 1_700_000_000_000
    for i in range(count):
        close = 100.0 + i * 0.12
        rows.append([
            str(base_time + i * 900_000),
            str(close - 0.05),
            str(close + 0.25),
            str(close - 0.25),
            str(close),
            "1000",
        ])
    return rows


def test_engine_suite_receives_confirmation_risk_and_mark_context(monkeypatch):
    captured = {}

    async def fake_klines(symbol, category, interval, limit):
        return _trend_rows(), "TEST"

    async def fake_book(symbol, category):
        return [["114", "100"]], [["114.1", "100"]], "TEST"

    async def fake_trades(symbol, category):
        return [
            {"price": 114, "size": 10, "side": "BUY", "time": 1},
            {"price": 114, "size": 2, "side": "SELL", "time": 2},
        ], "TEST"

    def capture_suite(context, selected=None):
        captured.update(context)
        return {"total_requested": 0, "results": []}

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    monkeypatch.setattr(main, "get_orderbook", fake_book)
    async def fake_enrichment(symbol, category, interval, candles):
        return {}, {"derivatives":{"status":"unavailable"},"cross_market":{"status":"unavailable"}}

    monkeypatch.setattr(main, "get_recent_trades", fake_trades)
    monkeypatch.setattr(main, "collect_engine_enrichment", fake_enrichment)
    monkeypatch.setattr(main, "run_engine_suite", capture_suite)

    response = TestClient(main.app).get(
        "/api/engine-suite/BTCUSDT?category=spot&interval=15m"
    )
    assert response.status_code == 200
    assert captured["symbol"] == "BTCUSDT"
    assert len(captured["raw_candle_rows"]) == 121
    assert captured["current_prices"]["BTCUSDT"] > 0
    assert captured["entry_confirmation"]["state"] in {
        "WAITING", "APPROACH", "CONFIRMED"
    }
    assert captured["risk_checks"]["visible_orderbook_available"] is True
    assert captured["risk_checks"]["recent_trade_flow_available"] is True
    assert captured["orderbook"]["provider"] == "TEST"
    assert captured["orderbook_observed_at"]
    assert captured["trades_observed_at"]
    assert captured["risk_checks"]["live_trading_disabled"] is True
    assert captured["risk_approval"]["approved"] is all(
        captured["risk_checks"].values()
    )
    assert captured["daily_loss_limit_pct"] > 0
    assert captured["risk_pct"] == 1.0
    assert captured["volatility_pct"] >= 0
    assert isinstance(captured["strategy_returns"], list)
    assert isinstance(captured["opportunity_candidates"], list)
    
def test_multi_market_engine_suite_uses_twelve_data_and_keeps_paper_only(monkeypatch):
    async def fake_twelve(symbol, interval, limit, market=None):
        return _trend_rows(), {
            "provider":"Stooq","timezone":"UTC","market":"Common Stock","exchange":"NASDAQ","data_quality":"daily_ohlcv"
        }

    monkeypatch.setattr(main, "get_twelve_data_klines", fake_twelve)
    response = TestClient(main.app).get(
        "/api/multi-market-engine-suite?market=stocks&symbol=aapl.us&interval=1d"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"]["provider"] == "Stooq"
    assert payload["market"] == "stocks"
    assert payload["completed_candles"] == 120
    assert payload["engine_suite"]["total_requested"] == 156
    assert payload["engine_readiness"]["total"] == 156
    assert payload["engine_readiness"]["counts"]["ACTIVE"] + payload["engine_readiness"]["counts"]["PARTIAL"] + payload["engine_readiness"]["counts"]["BLOCKED"] + payload["engine_readiness"]["counts"]["PLANNED"] == 156
    assert payload["engine_readiness"]["engines"][0]["source_evidence"]["market_snapshot"]["frequency"] == "daily"
    assert payload["engine_readiness"]["engines"][0]["source_evidence"]["market_snapshot"]["data_quality"] == "daily_ohlcv"
    assert payload["live_trading_enabled"] is False
    assert payload["trading_mode"] == "simulation"


def test_market_snapshot_marks_intraday_and_daily_fallbacks_distinctly():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    candle = {"time":now_ms,"open":100,"high":101,"low":99,"close":100,"volume":1}
    daily = main._market_snapshot_evidence([candle], "1d", "Stooq", {
        "provider":"Stooq","interval":"1d","data_quality":"daily_ohlcv",
        "freshness":"daily","limitations":"Daily bars only",
    })
    intraday = main._market_snapshot_evidence([candle], "5m", "Twelve Data")
    assert daily["frequency"] == "daily"
    assert daily["data_quality"] == "daily_ohlcv"
    assert intraday["frequency"] == "intraday"
    assert intraday["data_quality"] == "exchange_ohlcv"
    assert daily["freshness_status"] == intraday["freshness_status"] == "fresh"


def test_multi_market_engine_suite_rejects_intraday_without_key(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    response = TestClient(main.app).get(
        "/api/multi-market-engine-suite?market=forex&symbol=EUR%2FUSD"
    )
    assert response.status_code == 503
    assert "daily only" in response.json()["detail"]


def test_cross_market_peer_feed_aligns_public_exchange_candles(monkeypatch):
    async def fake_klines(symbol, category, interval, limit):
        return _trend_rows(121), "TEST"

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    rows = _trend_rows(121)
    base = [{"time":int(row[0]) // 1000,"close":float(row[4])} for row in rows]
    base_values, related, evidence = asyncio.run(
        main._aligned_peer_closes("BTCUSDT", "spot", "15m", base)
    )
    assert evidence["status"] == "ok"
    assert evidence["aligned_samples"] == 120
    assert len(base_values) == 120
    assert set(related) == {"ETHUSDT", "SOLUSDT", "BNBUSDT"}

