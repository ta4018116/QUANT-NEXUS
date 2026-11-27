import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app import coinalyze_derivatives as coinalyze


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for suffix, payload in self.payloads.items():
            if url.endswith(suffix):
                return FakeResponse(payload)
        raise AssertionError(f"Unexpected Coinalyze URL: {url}")


def _market_list():
    return [
        {
            "symbol": "BTCUSDT_PERP.B",
            "exchange": "BYBIT",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "is_perpetual": True,
        },
        {
            "symbol": "BTCUSDT_PERP.A",
            "exchange": "BINANCE",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "is_perpetual": True,
        },
        {
            "symbol": "BTCUSDT.0",
            "exchange": "BINANCE",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "is_perpetual": False,
        },
    ]


def test_coinalyze_snapshot_maps_actual_perpetual_and_normalizes_values(monkeypatch):
    coinalyze._MARKET_CACHE.clear()
    coinalyze._SNAPSHOT_CACHE.clear()
    now = int(datetime.now(timezone.utc).timestamp())
    client = FakeClient({
        "/future-markets": _market_list(),
        "/open-interest": [{"symbol": "BTCUSDT_PERP.A", "value": 125000000, "update": now}],
        "/funding-rate": [{"symbol": "BTCUSDT_PERP.A", "value": 0.0002, "update": now}],
        "/long-short-ratio-history": [{
            "symbol": "BTCUSDT_PERP.A",
            "history": [{"t": now - 3600, "r": 1.35, "l": 57.4, "s": 42.6}],
        }],
    })
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")

    result = asyncio.run(coinalyze.get_coinalyze_derivatives_snapshot(client, "BTCUSDT"))

    assert result["provider"] == "Coinalyze"
    assert result["provider_exchange"] == "BINANCE"
    assert result["provider_market_symbol"] == "BTCUSDT_PERP.A"
    assert result["open_interest"] == 125000000
    assert result["open_interest_unit"] == "USD"
    assert result["funding_rate"] == 0.0002
    assert result["long_short_ratio"] == 1.35
    assert result["data_quality"] == "provider_snapshot"
    assert all(call[1]["headers"]["api_key"] == "test-key" for call in client.calls)


def test_coinalyze_requires_server_side_api_key(monkeypatch):
    monkeypatch.delenv("COINALYZE_API_KEY", raising=False)
    client = FakeClient({})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(coinalyze.get_coinalyze_derivatives_snapshot(client, "BTCUSDT"))
    assert exc.value.status_code == 503
    assert client.calls == []


def test_coinalyze_rejects_stale_derivatives_snapshot(monkeypatch):
    coinalyze._MARKET_CACHE.clear()
    coinalyze._SNAPSHOT_CACHE.clear()
    stale = int(datetime.now(timezone.utc).timestamp()) - 3600
    client = FakeClient({
        "/future-markets": _market_list(),
        "/open-interest": [{"symbol": "BTCUSDT_PERP.A", "value": 125000000, "update": stale}],
        "/funding-rate": [{"symbol": "BTCUSDT_PERP.A", "value": 0.0002, "update": stale}],
    })
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(coinalyze.get_coinalyze_derivatives_snapshot(client, "BTCUSDT"))
    assert exc.value.status_code == 502
    assert "stale" in exc.value.detail


def test_coinalyze_rejects_missing_usdt_perpetual_market(monkeypatch):
    coinalyze._MARKET_CACHE.clear()
    coinalyze._SNAPSHOT_CACHE.clear()
    client = FakeClient({"/future-markets": []})
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(coinalyze.get_coinalyze_derivatives_snapshot(client, "BTCUSDT"))
    assert exc.value.status_code == 502
    assert "no matching" in exc.value.detail


def test_coinalyze_configuration_reports_presence_without_secret(monkeypatch):
    from app.provider_feeds import provider_configuration

    monkeypatch.setenv("COINALYZE_API_KEY", "DO_NOT_EXPOSE")
    report = provider_configuration()
    assert report["providers"]["coinalyze_derivatives"]["status"] == "configured"
    assert "DO_NOT_EXPOSE" not in str(report)
    assert "COINALYZE_API_KEY" not in str(report)
