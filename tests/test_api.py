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
