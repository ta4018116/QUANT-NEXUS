from fastapi.testclient import TestClient

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
    assert captured["current_prices"]["BTCUSDT"] > 0
    assert captured["entry_confirmation"]["state"] in {
        "WAITING", "APPROACH", "CONFIRMED"
    }
    assert captured["risk_checks"]["visible_orderbook_available"] is True
    assert captured["risk_checks"]["recent_trade_flow_available"] is True
    assert captured["risk_checks"]["live_trading_disabled"] is True
    assert captured["risk_approval"]["approved"] is all(
        captured["risk_checks"].values()
    )
    assert captured["daily_loss_limit_pct"] > 0
    assert captured["risk_pct"] == 1.0
    assert captured["volatility_pct"] >= 0
    assert isinstance(captured["strategy_returns"], list)
