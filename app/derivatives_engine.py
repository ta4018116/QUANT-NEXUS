"""Public derivatives analytics using Bybit linear market endpoints."""
from __future__ import annotations

def summarize_derivatives(open_interest_rows: list[dict], funding_rows: list[dict]) -> dict:
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
    return {
        "open_interest": oi[0] if oi else None,
        "open_interest_change_pct": round(oi_change_pct, 4) if oi_change_pct is not None else None,
        "funding_rate": latest_funding,
        "funding_bias": bias,
        "samples": {"open_interest": len(oi), "funding": len(funding)},
        "liquidations_feed": "not_connected",
        "disclaimer": "Open interest and funding are positioning context, not a liquidation feed or standalone trade signal."
    }
