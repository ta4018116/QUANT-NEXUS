from app.derivatives_engine import normalize_binance_liquidation


def test_normalize_binance_force_order_long_liquidation():
    payload = {"e":"forceOrder","E":1700000000000,"o":{"s":"BTCUSDT","S":"SELL","q":"0.2","z":"0.2","p":"50000","ap":"49900","T":1700000000000}}
    result = normalize_binance_liquidation(payload)
    assert len(result) == 1
    assert result[0]["liquidated_position"] == "LONG"
    assert result[0]["notional_usdt"] == 9980.0
    assert result[0]["provider"] == "Binance"


def test_normalize_binance_force_order_short_liquidation():
    payload = {"e":"forceOrder","E":1700000000000,"o":{"s":"ETHUSDT","S":"BUY","q":"1","z":"1","p":"3000","ap":"3010","T":1700000000000}}
    result = normalize_binance_liquidation(payload)
    assert result[0]["liquidated_position"] == "SHORT"
    assert result[0]["notional_usdt"] == 3010.0


def test_normalize_binance_rejects_invalid_or_non_usdt_rows():
    assert normalize_binance_liquidation({"e":"trade","o":{}}) == []
    assert normalize_binance_liquidation({"e":"forceOrder","o":{"s":"BTCUSD","S":"SELL","z":"1","ap":"50000","T":1700000000000}}) == []
    assert normalize_binance_liquidation({"e":"forceOrder","o":{"s":"BTCUSDT","S":"SELL","z":"0","ap":"50000","T":1700000000000}}) == []
