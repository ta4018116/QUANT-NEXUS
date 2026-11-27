import asyncio
from datetime import date, timedelta

from app.free_market_data import fetch_free_daily, fetch_frankfurter_daily, fetch_stooq_daily


class Response:
    def __init__(self, text=None, payload=None):
        self.text = text or ""
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_stooq_daily_csv_parses_sorted_ohlcv():
    today = date.today()
    csv = "Date,Open,High,Low,Close,Volume\n"
    for i in range(70):
        d = today - timedelta(days=100-i)
        csv += f"{d.isoformat()},10,12,9,11,1000\n"
    client = Client(Response(text=csv))
    rows = asyncio.run(fetch_stooq_daily(client, "aapl.us", 70))
    assert len(rows) == 70
    assert rows[0][1:] == ["10.0", "12.0", "9.0", "11.0", "1000.0"]
    assert client.calls[0][0] == "https://stooq.com/q/d/l/"


def test_frankfurter_daily_is_explicitly_reference_close_only():
    rates = {}
    for i in range(70):
        day = (date.today() - timedelta(days=100-i)).isoformat()
        rates[day] = {"USD": 1.08}
    client = Client(Response(payload={"rates": rates}))
    rows = asyncio.run(fetch_frankfurter_daily(client, "EURUSD", 70))
    assert len(rows) == 70
    assert rows[-1][1:5] == ["1.08"] * 4
    assert rows[-1][5] == "0"
    assert "api.frankfurter.app" in client.calls[0][0]


def test_free_daily_routes_by_market_and_declares_quality():
    rates = {}
    for i in range(70):
        rates[(date.today() - timedelta(days=100-i)).isoformat()] = {"USD": 1.08}
    rows, info = asyncio.run(fetch_free_daily(Client(Response(payload={"rates": rates})), "forex", "EURUSD", 70))
    assert len(rows) == 70
    assert info["provider"] == "Frankfurter"
    assert info["data_quality"] == "daily_reference_close_only"
    assert info["auth_required"] is False


def test_free_daily_rejects_invalid_fx_symbol():
    client = Client(Response(payload={"rates": {}}))
    try:
        asyncio.run(fetch_frankfurter_daily(client, "BTCUSDT", 100))
    except ValueError as exc:
        assert "six_letter" in str(exc)
    else:
        raise AssertionError("invalid FX pair was accepted")
