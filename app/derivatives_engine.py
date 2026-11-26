"""Public derivatives analytics and liquidation normalization for Bybit linear markets."""
from __future__ import annotations

from datetime import datetime, timezone


def normalize_liquidations(rows: list[dict]) -> list[dict]:
    """Normalize Bybit allLiquidation payload rows without inventing missing values."""
    events = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            symbol = str(row.get("s") or "").upper()
            side = str(row.get("S") or "").upper()
            size = float(row.get("v"))
            price = float(row.get("p"))
            timestamp_ms = int(row.get("T"))
        except (TypeError, ValueError, OverflowError):
            continue
        if not symbol.endswith("USDT") or side not in {"BUY", "SELL"} or size <= 0 or price <= 0 or timestamp_ms <= 0:
            continue
        # Bybit documents Buy as liquidation of a long position; Sell as a short liquidation.
        notional = size * price
        events.append({
            "symbol": symbol,
            "liquidated_position": "LONG" if side == "BUY" else "SHORT",
            "side": side,
            "size": size,
            "bankruptcy_price": price,
            "notional_usdt": round(notional, 8),
            "timestamp_ms": timestamp_ms,
            "timestamp": datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat(),
            "provider": "Bybit",
            "feed": "allLiquidation",
        })
    return events


def summarize_liquidations(events: list[dict]) -> dict:
    valid = [x for x in events if isinstance(x, dict)]
    long_value = sum(float(x.get("notional_usdt") or 0) for x in valid if x.get("liquidated_position") == "LONG")
    short_value = sum(float(x.get("notional_usdt") or 0) for x in valid if x.get("liquidated_position") == "SHORT")
    return {
        "events": len(valid),
        "long_liquidations_usdt": round(long_value, 8),
        "short_liquidations_usdt": round(short_value, 8),
        "total_liquidations_usdt": round(long_value + short_value, 8),
        "dominant_side": "LONG" if long_value > short_value else ("SHORT" if short_value > long_value else "BALANCED"),
        "provider": "Bybit",
        "feed": "allLiquidation",
    }


def summarize_derivatives(open_interest_rows: list[dict], funding_rows: list[dict], liquidation_events: list[dict] | None = None) -> dict:
    oi = [float(x.get("openInterest") or 0) for x in open_interest_rows if float(x.get("openInterest") or 0) > 0]
    funding = [float(x.get("fundingRate") or 0) for x in funding_rows if x.get("fundingRate") is not None]
    oi_change_pct = ((oi[0] / oi[-1]) - 1) * 100 if len(oi) >= 2 and oi[-1] else None
    latest_funding = funding[0] if funding else None
    if latest_funding is None:
        bias = "UNKNOWN"
    elif latest_funding >= 0.001:
        bias = "LONG_CROWDED"
    elif latest_funding <= -0.001:
        bias = "SHORT_CROWDED"
    else:
        bias = "BALANCED"
    events = liquidation_events or []
    return {
        "open_interest": oi[0] if oi else None,
        "open_interest_change_pct": round(oi_change_pct, 4) if oi_change_pct is not None else None,
        "funding_rate": latest_funding,
        "funding_bias": bias,
        "samples": {"open_interest": len(oi), "funding": len(funding)},
        "liquidations_feed": "Bybit allLiquidation WebSocket; subscribe per symbol",
        "liquidations": summarize_liquidations(events),
        "disclaimer": "Liquidation prints are executed liquidation events, not a complete map of positions at risk or a standalone trade signal."
    }
