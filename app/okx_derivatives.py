"""Read-only OKX fallback for linear perpetual derivatives metrics."""
from __future__ import annotations

import asyncio
from fastapi import HTTPException


async def get_okx_derivatives_snapshot(okx_get, symbol: str) -> dict:
    """Fetch OKX public open interest and current funding; never infer missing ratios."""
    base = symbol.upper().removesuffix("USDT")
    if not base or not base.isalnum():
        raise HTTPException(status_code=400, detail="Invalid USDT linear symbol")
    inst_id = f"{base}-USDT-SWAP"
    oi_result, funding_result = await asyncio.gather(
        okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": inst_id}),
        okx_get("/api/v5/public/funding-rate", {"instId": inst_id}),
        return_exceptions=True,
    )
    if isinstance(oi_result, Exception) or isinstance(funding_result, Exception):
        raise HTTPException(status_code=502, detail="OKX derivatives feeds are unavailable")
    oi_rows = oi_result if isinstance(oi_result, list) else []
    funding_rows = funding_result if isinstance(funding_result, list) else []
    oi_row = next((x for x in oi_rows if isinstance(x, dict) and x.get("instId") == inst_id), None)
    funding_row = next((x for x in funding_rows if isinstance(x, dict) and x.get("instId") == inst_id), None)
    if oi_row is None or funding_row is None:
        raise HTTPException(status_code=502, detail="OKX returned incomplete derivatives data")
    # oiUsd is comparable across contracts; do not mix contract counts with USD notionals.
    oi_value = _positive_number(oi_row.get("oiUsd"))
    funding_rate = _finite_number(funding_row.get("fundingRate"))
    if oi_value is None or funding_rate is None:
        raise HTTPException(status_code=502, detail="OKX returned invalid derivatives values")
    return {
        "open_interest": oi_value,
        "open_interest_unit": "USD",
        "open_interest_change_pct": None,
        "funding_rate": funding_rate,
        "funding_bias": (
            "LONG_CROWDED" if funding_rate >= 0.001 else
            "SHORT_CROWDED" if funding_rate <= -0.001 else "BALANCED"
        ),
        "long_short_ratio": None,
        "samples": {"open_interest": 1, "funding": 1},
        "provider": "OKX",
        "data_quality": "provider_snapshot",
        "liquidations": {"events": 0, "provider": None},
        "disclaimer": "OKX fallback supplies current USD open interest and funding only; historical OI change, long/short ratio, and liquidation events are not inferred.",
    }


def _finite_number(value):
    try:
        import math
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _positive_number(value):
    number = _finite_number(value)
    return number if number is not None and number > 0 else None
