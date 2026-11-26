import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture()
def client():
    main.reset_paper_state(10_000.0)
    return TestClient(main.app)


def test_health_keeps_live_trading_disabled(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["trading_mode"] == "simulation"
    assert payload["live_trading_enabled"] is False


def test_overview_marks_unconnected_markets(client):
    response = client.get("/api/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["live_trading_enabled"] is False
    assert set(payload["unconnected_markets"]) == {
        "Forex", "US Stocks", "Indices", "Commodities"
    }


def test_invalid_market_parameters_return_4xx_not_500(client):
    assert client.get("/api/markets?category=unknown").status_code == 422
    assert client.get("/api/klines/BTCUSDT?category=unknown").status_code == 400
    assert client.get("/api/scan?category=unknown").status_code == 400


def test_paper_trade_open_and_close(client):
    opened = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "entry": 100,
        "quantity": 2, "stop_loss": 95, "take_profit": 110
    })
    assert opened.status_code == 200
    trade = opened.json()["trade"]
    assert trade["status"] == "OPEN"
    assert opened.json()["live_trading_enabled"] is False
    assert opened.json()["balance"] == pytest.approx(9_799.88)

    closed = client.post(f"/api/paper/{trade['id']}/close?exit_price=110")
    assert closed.status_code == 200
    assert closed.json()["trade"]["status"] == "CLOSED"
    assert closed.json()["trade"]["grossPnl"] == 20
    assert closed.json()["trade"]["pnl"] == pytest.approx(19.748)
    assert closed.json()["balance"] == pytest.approx(10_019.748)
    assert closed.json()["live_trading_enabled"] is False


def test_paper_trade_rejects_invalid_side_and_overdraft(client):
    bad_side = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "BUY", "entry": 100, "quantity": 1
    })
    assert bad_side.status_code == 400

    overdraft = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "entry": 20_000, "quantity": 1
    })
    assert overdraft.status_code == 400


def test_paper_close_missing_trade_is_404(client):
    response = client.post("/api/paper/999/close?exit_price=100")
    assert response.status_code == 404


def test_scan_handles_per_symbol_provider_errors_without_crashing(client, monkeypatch):
    async def fake_tickers(category):
        return ([{"symbol": "BTCUSDT", "turnover24h": 1_000_000,
                  "price24hPcnt": 0.01}], "OKX")

    async def fake_klines(symbol, category, interval, limit):
        raise main.HTTPException(status_code=502, detail="provider unavailable")

    monkeypatch.setattr(main, "get_market_tickers", fake_tickers)
    monkeypatch.setattr(main, "get_market_klines", fake_klines)

    response = client.get("/api/scan?category=spot&limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scanned"] == 1
    assert payload["returned"] == 0
    assert payload["items"] == []


def test_candle_analysis_rejects_insufficient_or_malformed_data():
    with pytest.raises(main.HTTPException) as exc:
        main.analyze_klines([["bad"]])
    assert exc.value.status_code == 502


def test_no_live_order_endpoint_is_exposed():
    paths = {route.path for route in main.app.routes}
    assert not any("/api/live" in path or "/api/order" in path for path in paths)


def test_neon_dashboard_is_served_and_keeps_paper_only_mode(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert 'QUANT NEXUS' in html
    assert 'رادار السوق الذكي' in html
    assert 'مكتبة الأوامر التحليلية' in html
    assert '/api/scan?' in html
    assert '/api/klines/' in html
    assert '/api/paper' in html
    assert 'التداول الحقيقي: معطّل' in html
    health = client.get("/health").json()
    assert health["live_trading_enabled"] is False


def test_engine_status_exposes_supported_analysis_and_paper_only_mode(client):
    payload = client.get("/api/engine/status").json()
    assert payload["scan_depths"] == [32, 64, 128, 256, "AUTO"]
    assert "MACD12-26-9" in payload["indicators"]
    assert payload["trading_mode"] == "simulation"
    assert payload["live_trading_enabled"] is False


def test_macd_returns_values_when_history_is_sufficient():
    values = [100 + i * 0.5 + (i % 4) * 0.1 for i in range(80)]
    line, signal, histogram = main.macd(values)
    assert line is not None
    assert signal is not None
    assert histogram == pytest.approx(line - signal)


def make_rows(count=120):
    rows = []
    for i in range(count):
        close = 100 + i * 0.15 + (i % 7) * 0.08
        open_price = close - 0.05
        high = close + 0.3
        low = open_price - 0.25
        rows.append([str(i * 60_000), str(open_price), str(high), str(low),
                     str(close), str(1000 + i * 2)])
    return rows


def test_analysis_exposes_atr_and_explainable_reasons():
    result = main.analyze_klines(make_rows())
    assert result["atr14"] is not None
    assert result["atrPercent"] > 0
    assert isinstance(result["reasons"], list)
    assert result["classification"] in {"STRONG", "NEEDS_CONFIRMATION", "HIGH_RISK", "WAIT"}
    assert 0 <= result["preMoveScore"] <= 100
    assert result["preMoveLabel"] in {"WATCH", "LOW"}


def test_paper_trade_risk_guard_rejects_wrong_side_stop(client):
    response = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "entry": 100,
        "quantity": 1, "stop_loss": 101, "take_profit": 110
    })
    assert response.status_code == 400
    assert "Stop loss" in response.json()["detail"]


def test_paper_trade_state_is_saved_to_sqlite(client):
    response = client.post("/api/paper", json={
        "symbol": "ETHUSDT", "side": "LONG", "entry": 100,
        "quantity": 1, "stop_loss": 90, "take_profit": 120
    })
    assert response.status_code == 200
    balance, trades = main.PAPER_STORE.load()
    assert balance == pytest.approx(9_899.94)
    assert len(trades) == 1
    assert trades[0]["symbol"] == "ETHUSDT"


def test_position_size_endpoint_caps_risk_at_two_percent(client):
    response = client.post("/api/risk/position-size", json={
        "equity": 10000, "risk_pct": 1, "entry": 100, "stop_loss": 95
    })
    assert response.status_code == 200
    assert response.json()["riskAmount"] == 100
    assert response.json()["quantity"] == 20
    assert client.post("/api/risk/position-size", json={
        "equity": 10000, "risk_pct": 3, "entry": 100, "stop_loss": 95
    }).status_code == 422


def test_strategy_list_and_backtest_endpoint(client, monkeypatch):
    async def fake_klines(symbol, category, interval, limit):
        return make_rows(), "Bybit"

    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    strategies = client.get("/api/strategies")
    assert strategies.status_code == 200
    assert strategies.json()["strategies"][0]["id"] == "ema_crossover"
    response = client.get("/api/backtest/BTCUSDT?fast_period=5&slow_period=15")
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["sampleBars"] == 120
    assert "maxDrawdownPct" in payload
    assert payload["live_trading_enabled"] is False


def test_liquidity_endpoint_reports_depth_imbalance(client, monkeypatch):
    async def fake_orderbook(symbol, category):
        return ([["100", "10"], ["99.9", "5"]], [["100.1", "4"], ["100.2", "3"]], "Bybit")

    monkeypatch.setattr(main, "get_orderbook", fake_orderbook)
    response = client.get("/api/liquidity/BTCUSDT")
    assert response.status_code == 200
    payload = response.json()
    assert payload["spreadPct"] > 0
    assert payload["depthImbalance"] > 0
    assert payload["bias"] == "BUY_SIDE"


def test_market_flow_marks_outliers_as_large_trade_prints(client, monkeypatch):
    async def fake_trades(symbol, category):
        return ([{"price": 100, "size": 1, "side": "BUY", "time": 1},
                 {"price": 100, "size": 1, "side": "SELL", "time": 2},
                 {"price": 100, "size": 500, "side": "BUY", "time": 3}], "Bybit")

    monkeypatch.setattr(main, "get_recent_trades", fake_trades)
    response = client.get("/api/flow/BTCUSDT")
    assert response.status_code == 200
    assert response.json()["largeTradePrints"]
    assert "not proof" in response.json()["interpretation"]


def test_engine_status_discloses_storage_and_market_coverage(client):
    payload = client.get("/api/engine/status").json()
    assert payload["paper_storage"] == "sqlite"
    assert payload["markets"]["forex"] is False
    assert payload["live_trading_enabled"] is False


def test_paper_requires_stop_loss_for_every_position(client):
    response = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "entry": 100, "quantity": 1
    })
    assert response.status_code == 400
    assert "stop loss is required" in response.json()["detail"].lower()


def test_paper_monitor_closes_when_stop_is_hit(client, monkeypatch):
    async def fake_tickers(category):
        return ([{"symbol": "BTCUSDT", "lastPrice": 89}], "Bybit")

    monkeypatch.setattr(main, "get_market_tickers", fake_tickers)
    opened = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "category": "spot",
        "entry": 100, "quantity": 1, "stop_loss": 90, "take_profit": 120
    })
    assert opened.status_code == 200
    monitored = client.post("/api/paper/monitor")
    assert monitored.status_code == 200
    payload = monitored.json()
    assert payload["closed"][0]["reason"] == "STOP_LOSS"
    account = client.get("/api/paper").json()
    assert account["openCount"] == 0
    assert account["closedCount"] == 1
    assert account["trades"][0]["pnl"] == pytest.approx(-11.1134)


def test_market_flow_liquidity_and_strategy_apis_are_registered(client):
    paths = {route.path for route in main.app.routes}
    assert "/api/liquidity/{symbol}" in paths
    assert "/api/flow/{symbol}" in paths
    assert "/api/backtest/{symbol}" in paths
    assert "/api/paper/monitor" in paths
    assert "/api/risk/position-size" in paths


def test_backtest_rejects_invalid_fast_slow_period_order(client):
    response = client.get("/api/backtest/BTCUSDT?fast_period=30&slow_period=10")
    assert response.status_code == 400


def test_futures_paper_position_uses_leverage_margin_and_realized_pnl(client):
    opened = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "SHORT", "category": "linear",
        "leverage": 5, "entry": 100, "quantity": 10,
        "stop_loss": 101, "take_profit": 90
    })
    assert opened.status_code == 200
    payload = opened.json()
    assert payload["trade"]["leverage"] == 5
    assert payload["trade"]["margin"] == 200
    assert payload["balance"] == 9800

    closed = client.post(f"/api/paper/{payload['trade']['id']}/close?exit_price=95")
    assert closed.status_code == 200
    assert closed.json()["trade"]["pnl"] == pytest.approx(48.83)
    assert closed.json()["balance"] == pytest.approx(10_048.83)


def test_spot_simulation_rejects_short_and_leverage(client):
    short = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "SHORT", "category": "spot",
        "entry": 100, "quantity": 1, "stop_loss": 110
    })
    assert short.status_code == 400
    leveraged = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "category": "spot",
        "leverage": 2, "entry": 100, "quantity": 1, "stop_loss": 90
    })
    assert leveraged.status_code == 400


def test_flat_market_rsi_is_neutral_not_overbought():
    assert main.rsi([100.0] * 30) == 50.0


def test_paper_summary_includes_mark_to_market_and_fee_estimate(client, monkeypatch):
    async def fake_tickers(category):
        return ([{"symbol": "BTCUSDT", "lastPrice": 110}], "Bybit")
    monkeypatch.setattr(main, "get_market_tickers", fake_tickers)
    opened = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "category": "spot",
        "entry": 100, "quantity": 1, "stop_loss": 95, "take_profit": 120
    })
    assert opened.status_code == 200
    summary = client.get("/api/paper/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["equity"] > payload["balance"]
    assert payload["unrealizedPnlAfterFees"] == pytest.approx(9.874)
    assert payload["live_trading_enabled"] is False


def test_scan_rejects_unknown_direction_before_market_request(client):
    response = client.get("/api/scan?direction=sideways")
    assert response.status_code == 400
