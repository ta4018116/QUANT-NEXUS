import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture()
def client():
    main.PAPER_TRADES.clear()
    main.PAPER_BALANCE = 10_000.0
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
    assert opened.json()["balance"] == 9_800

    closed = client.post(f"/api/paper/{trade['id']}/close?exit_price=110")
    assert closed.status_code == 200
    assert closed.json()["trade"]["status"] == "CLOSED"
    assert closed.json()["trade"]["pnl"] == 20
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


def test_paper_short_trade_pnl_is_directionally_correct(client):
    opened = client.post("/api/paper", json={
        "symbol": "ETHUSDT", "side": "SHORT", "entry": 100,
        "quantity": 2, "stop_loss": 110, "take_profit": 90
    })
    assert opened.status_code == 200
    trade_id = opened.json()["trade"]["id"]
    closed = client.post(f"/api/paper/{trade_id}/close?exit_price=90")
    assert closed.status_code == 200
    assert closed.json()["trade"]["pnl"] == 20
    assert closed.json()["balance"] == 10020


def test_paper_trade_rejects_wrong_side_levels(client):
    response = client.post("/api/paper", json={
        "symbol": "BTCUSDT", "side": "LONG", "entry": 100,
        "quantity": 1, "stop_loss": 105, "take_profit": 120
    })
    assert response.status_code == 400


def test_sqlite_paper_state_round_trip(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_MODE", "sqlite")
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "portfolio.sqlite3")
    sample = [{"id": 7, "symbol": "BTCUSDT", "side": "LONG", "status": "OPEN"}]
    main._save_paper_state(4321.5, sample)
    balance, trades = main._load_paper_state()
    assert balance == 4321.5
    assert trades == sample


def test_backtest_calculator_returns_metrics():
    candles = []
    for i in range(140):
        price = 100 + i * 0.8
        candles.append({"time": i, "open": price, "high": price + 1,
                        "low": price - 1, "close": price + 0.5, "volume": 1000})
    result = main.calculate_backtest(candles, fee_bps=10)
    assert result["strategy"].startswith("EMA20/EMA50")
    assert result["tradeCount"] >= 1
    assert result["finalBalance"] > result["initialBalance"]
    assert result["live_trading_enabled"] if "live_trading_enabled" in result else True


def test_analysis_command_executes_real_trend_analysis(client, monkeypatch):
    rows = []
    for i in range(100):
        price = 100 + i * 0.25
        rows.append([str(1_700_000_000_000 + i * 900_000), str(price),
                     str(price + 1), str(price - 1), str(price + 0.5), "1000"])
    async def fake_klines(symbol, category, interval, limit):
        return rows, "TEST"
    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    response = client.post("/api/commands/execute", json={
        "symbol": "BTCUSDT", "category": "spot", "interval": "15m",
        "command": "تحليل الاتجاه العام"
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["kind"] == "trend"
    assert payload["provider"] == "TEST"
    assert payload["data"]["ema20"] is not None
    assert payload["live_trading_enabled"] is False


def test_backtest_api_uses_historical_candles(client, monkeypatch):
    rows = []
    for i in range(120):
        price = 100 + i * 0.2
        rows.append([str(1_700_000_000_000 + i * 3_600_000), str(price),
                     str(price + 1), str(price - 1), str(price + 0.1), "1000"])
    async def fake_klines(symbol, category, interval, limit):
        return rows, "TEST"
    monkeypatch.setattr(main, "get_market_klines", fake_klines)
    response = client.get("/api/backtest/BTCUSDT?interval=1h&limit=120")
    assert response.status_code == 200
    payload = response.json()
    assert payload["candles"] == 120
    assert payload["live_trading_enabled"] is False
    assert "profitFactor" in payload

