import asyncio

from app import provider_feeds


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {"content-type": "application/json"}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for prefix, response in self.responses.items():
            if url.startswith(prefix):
                return response
        raise AssertionError(f"Unexpected upstream URL: {url}")


def test_gdelt_news_is_parsed_and_cached():
    provider_feeds._CACHE.clear()
    client = FakeClient({
        "https://api.gdeltproject.org/": FakeResponse({
            "articles": [
                {
                    "title": "Bitcoin market update",
                    "url": "https://example.com/bitcoin",
                    "domain": "example.com",
                    "seendate": "20261127T100000Z",
                    "language": "English",
                    "tone": "-1.2",
                },
                {"title": "bad URL", "url": "javascript:alert(1)"},
            ]
        })
    })

    async def run():
        first = await provider_feeds.fetch_gdelt_news(client, "BTCUSDT")
        second = await provider_feeds.fetch_gdelt_news(client, "BTCUSDT")
        return first, second

    first, second = asyncio.run(run())
    assert first["status"] == "ok"
    assert first["provider"] == "GDELT"
    assert first["event_count"] == 1
    assert first["events"][0]["source"] == "GDELT"
    assert second["event_count"] == 1
    assert len(client.calls) == 1


def test_coinglass_aggregate_liquidations_requires_key_and_normalizes_totals(monkeypatch):
    provider_feeds._CACHE.clear()
    monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
    missing = asyncio.run(provider_feeds.fetch_coinglass_liquidations(FakeClient({}), "BTCUSDT"))
    assert missing["status"] == "missing_credentials"

    monkeypatch.setenv("COINGLASS_API_KEY", "test-key")
    client = FakeClient({
        "https://open-api-v4.coinglass.com/": FakeResponse({
            "code": "0",
            "data": [
                {
                    "exchange": "All",
                    "liquidation_usd": 1500000,
                    "longLiquidation_usd": 900000,
                    "shortLiquidation_usd": 600000,
                },
                {"exchange": "Binance", "liquidation_usd": 750000},
            ],
        })
    })
    result = asyncio.run(provider_feeds.fetch_coinglass_liquidations(client, "BTCUSDT"))
    assert result["status"] == "ok"
    assert result["symbol"] == "BTC"
    assert result["total_liquidation_usd"] == 1500000
    assert result["long_liquidation_usd"] == 900000
    assert result["short_liquidation_usd"] == 600000
    assert result["data_kind"] == "aggregate_liquidation_totals_not_price_heatmap"
    assert client.calls[0][1]["headers"]["CG-API-KEY"] == "test-key"


def test_cryptopanic_without_token_fails_closed(monkeypatch):
    monkeypatch.delenv("CRYPTOPANIC_API_TOKEN", raising=False)
    result = asyncio.run(provider_feeds.fetch_cryptopanic_news(FakeClient({}), "ETHUSDT"))
    assert result["status"] == "missing_credentials"
    assert result["events"] == []


def test_provider_configuration_does_not_expose_secret_values(monkeypatch):
    monkeypatch.setenv("COINGLASS_API_KEY", "DO_NOT_RETURN_THIS")
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "TWELVE_DATA_SECRET_MUST_STAY_HIDDEN")
    report = provider_feeds.provider_configuration()
    serialized = str(report)
    assert "DO_NOT_RETURN_THIS" not in serialized
    assert "TWELVE_DATA_SECRET_MUST_STAY_HIDDEN" not in serialized
    assert report["providers"]["coinglass_liquidations"]["status"] == "configured"
    assert report["providers"]["twelve_data"]["status"] == "configured"
