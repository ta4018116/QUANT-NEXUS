import asyncio

from fastapi import HTTPException

from app import main


def _fail_provider(*args, **kwargs):
    raise HTTPException(status_code=502, detail="provider unavailable")


def test_spot_tickers_fall_back_to_binance_and_normalize_schema(monkeypatch):
    async def fake_binance(category, path, params):
        assert category == "spot"
        assert path == "/api/v3/ticker/24hr"
        return [{
            "symbol": "BTCUSDT", "lastPrice": "65000", "openPrice": "64000",
            "priceChangePercent": "1.5625", "highPrice": "66000",
            "lowPrice": "63000", "quoteVolume": "1000000", "volume": "15.3",
        }]

    monkeypatch.setattr(main, "bybit_get", _fail_provider)
    monkeypatch.setattr(main, "okx_get", _fail_provider)
    monkeypatch.setattr(main, "_binance_get", fake_binance)

    rows, provider = asyncio.run(main.get_market_tickers("spot"))
    assert provider == "Binance"
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["lastPrice"] == 65000
    assert rows[0]["price24hPcnt"] == 0.015625
    assert rows[0]["turnover24h"] == 1_000_000


def test_linear_klines_fall_back_to_binance_without_changing_interval(monkeypatch):
    expected = [[str(i), "100", "102", "99", "101", "50"] for i in range(30)]
    async def fake_binance(category, path, params):
        assert category == "linear"
        assert path == "/fapi/v1/klines"
        assert params == {"symbol": "BTCUSDT", "interval": "15m", "limit": 120}
        return expected

    monkeypatch.setattr(main, "bybit_get", _fail_provider)
    monkeypatch.setattr(main, "okx_get", _fail_provider)
    monkeypatch.setattr(main, "_binance_get", fake_binance)

    rows, provider = asyncio.run(main.get_market_klines("BTCUSDT", "linear", "15m", 120))
    assert provider == "Binance"
    assert rows == expected


def test_orderbook_and_recent_trades_fall_back_to_binance(monkeypatch):
    async def fake_binance(category, path, params):
        assert category == "spot"
        if path == "/api/v3/depth":
            return {"bids": [["100", "2"]], "asks": [["101", "3"]]}
        if path == "/api/v3/trades":
            return [
                {"price": "100", "qty": "2", "isBuyerMaker": False, "time": 10},
                {"price": "101", "qty": "1", "isBuyerMaker": True, "time": 11},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(main, "bybit_get", _fail_provider)
    monkeypatch.setattr(main, "okx_get", _fail_provider)
    monkeypatch.setattr(main, "_binance_get", fake_binance)

    bids, asks, book_provider = asyncio.run(main.get_orderbook("BTCUSDT", "spot"))
    trades, trade_provider = asyncio.run(main.get_recent_trades("BTCUSDT", "spot"))

    assert book_provider == "Binance"
    assert bids == [["100", "2"]] and asks == [["101", "3"]]
    assert trade_provider == "Binance"
    assert trades[0]["side"] == "BUY"
    assert trades[1]["side"] == "SELL"
    assert trades[1]["size"] == 1


def test_derivatives_snapshot_falls_back_to_binance_oi_funding_and_ratio(monkeypatch):
    async def fake_binance(category, path, params):
        assert category == "linear"
        if path == "/fapi/v1/openInterest":
            return {"symbol": "BTCUSDT", "openInterest": "1200"}
        if path == "/futures/data/openInterestHist":
            return [
                {"sumOpenInterest": "1000", "timestamp": 1},
                {"sumOpenInterest": "1100", "timestamp": 2},
            ]
        if path == "/fapi/v1/fundingRate":
            return [{"fundingRate": "0.0002", "fundingTime": 2}]
        if path == "/futures/data/globalLongShortAccountRatio":
            return [{"longShortRatio": "1.25", "timestamp": 2}]
        raise AssertionError(path)

    monkeypatch.setattr(main, "bybit_get", _fail_provider)
    monkeypatch.setattr(main, "_binance_get", fake_binance)

    result = asyncio.run(main.get_derivatives_snapshot("BTCUSDT"))
    assert result["provider"] == "Binance USD-M Futures"
    assert result["open_interest"] == 1200
    assert result["open_interest_change_pct"] == 10
    assert result["funding_rate"] == 0.0002
    assert result["long_short_ratio"] == 1.25


def test_derivatives_snapshot_rejects_non_usdt_symbols():
    try:
        asyncio.run(main.get_derivatives_snapshot("BTCUSD"))
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("non-USDT derivatives symbol should be rejected")
