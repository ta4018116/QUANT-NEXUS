"""Coinalyze read-only derivatives failover for QUANT NEXUS.

Uses documented public market metadata and current OI/funding endpoints.
The API key is read only from the server environment; no trading endpoints exist.
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from datetime import datetime, timezone

from fastapi import HTTPException

BASE_URL = "https://api.coinalyze.net/v1"
_MARKET_CACHE: dict[str, tuple[float, str, str]] = {}
_SNAPSHOT_CACHE: dict[str, tuple[float, dict]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_MARKET_LOCK = asyncio.Lock()


def _finite(value):
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _timestamp_seconds(value):
    try:
        stamp = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    if stamp > 10**12:
        stamp //= 1000
    return stamp if stamp > 0 else None


async def _request_json(client, path: str, *, headers: dict, params: dict | None = None):
    response = await client.get(
        f"{BASE_URL}/{path}",
        params=params or {},
        headers=headers,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise HTTPException(status_code=502, detail="Coinalyze returned an invalid payload")
    return payload


async def _resolve_market(client, base_asset: str, headers: dict) -> tuple[str, str]:
    cache_key = base_asset.upper()
    cached = _MARKET_CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1], cached[2]

    async with _MARKET_LOCK:
        cached = _MARKET_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]
        markets = await _request_json(client, "future-markets", headers=headers)
        matches = []
        for item in markets:
            if not isinstance(item, dict):
                continue
            if str(item.get("base_asset", "")).upper() != cache_key:
                continue
            if str(item.get("quote_asset", "")).upper() != "USDT":
                continue
            perpetual = item.get("is_perpetual")
            if perpetual is not True and str(perpetual).lower() not in ("true", "1"):
                continue
            symbol = str(item.get("symbol", "")).strip()
            exchange = str(item.get("exchange", "")).strip().upper()
            if symbol:
                matches.append((exchange, symbol))
        if not matches:
            raise HTTPException(status_code=502, detail="Coinalyze has no matching USDT perpetual market")
        preferred = {"BINANCE": 0, "BYBIT": 1, "OKX": 2, "BITGET": 3, "GATEIO": 4}
        exchange, symbol = sorted(matches, key=lambda row: (preferred.get(row[0], 99), row[0]))[0]
        _MARKET_CACHE[cache_key] = (time.monotonic() + 3600, symbol, exchange)
        return symbol, exchange


async def get_coinalyze_derivatives_snapshot(client, symbol: str) -> dict:
    """Return a verified Coinalyze USDT-perpetual OI/funding snapshot.

    Coinalyze's API limit is 40 requests/minute/key. Results are cached briefly
    and the market catalogue is cached for one hour to avoid repeated lookups.
    """
    api_key = os.getenv("COINALYZE_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="COINALYZE_API_KEY_not_configured")
    clean = str(symbol or "").upper().strip()
    if not clean.endswith("USDT") or not clean[:-4].isalnum():
        raise HTTPException(status_code=400, detail="Only USDT linear symbols are supported")

    cached = _SNAPSHOT_CACHE.get(clean)
    if cached and cached[0] > time.monotonic():
        return dict(cached[1])

    lock = _LOCKS.setdefault(clean, asyncio.Lock())
    async with lock:
        cached = _SNAPSHOT_CACHE.get(clean)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1])

        headers = {"api_key": api_key, "Accept": "application/json"}
        market_symbol, exchange = await _resolve_market(client, clean[:-4], headers)
        oi_rows, funding_rows = await asyncio.gather(
            _request_json(
                client, "open-interest", headers=headers,
                params={"symbols": market_symbol, "convert_to_usd": "true"},
            ),
            _request_json(
                client, "funding-rate", headers=headers,
                params={"symbols": market_symbol},
            ),
        )
        oi = next((row for row in oi_rows if isinstance(row, dict) and row.get("symbol") == market_symbol), None)
        funding = next((row for row in funding_rows if isinstance(row, dict) and row.get("symbol") == market_symbol), None)
        oi_value = _finite(oi.get("value")) if oi else None
        funding_rate = _finite(funding.get("value")) if funding else None
        if oi_value is None or oi_value <= 0 or funding_rate is None:
            raise HTTPException(status_code=502, detail="Coinalyze OI/funding snapshot is incomplete")

        updated = [
            _timestamp_seconds(oi.get("update")) if oi else None,
            _timestamp_seconds(funding.get("update")) if funding else None,
        ]
        valid_updates = [stamp for stamp in updated if stamp is not None]
        now = int(datetime.now(timezone.utc).timestamp())
        if not valid_updates or now - max(valid_updates) > 900 or max(valid_updates) > now + 60:
            raise HTTPException(status_code=502, detail="Coinalyze derivatives snapshot is stale or has no valid update timestamp")

        # Long/short ratio is a historical series, not a true current account-position feed.
        # It is optional: failure must not discard a valid OI/funding snapshot.
        ratio = None
        ratio_samples = 0
        try:
            ratio_payload = await _request_json(
                client, "long-short-ratio-history", headers=headers,
                params={
                    "symbols": market_symbol,
                    "interval": "1hour",
                    "from": now - 6 * 3600,
                    "to": now,
                },
            )
            series = next(
                (row.get("history", []) for row in ratio_payload
                 if isinstance(row, dict) and row.get("symbol") == market_symbol),
                [],
            )
            series = [row for row in series if isinstance(row, dict)]
            ratio_samples = len(series)
            if series:
                latest = max(series, key=lambda row: _timestamp_seconds(row.get("t")) or 0)
                ratio = _finite(latest.get("r"))
                if ratio is None:
                    long_value, short_value = _finite(latest.get("l")), _finite(latest.get("s"))
                    if long_value is not None and short_value is not None and short_value > 0:
                        ratio = long_value / short_value
        except Exception:
            ratio = None

        snapshot = {
            "open_interest": oi_value,
            "open_interest_unit": "USD",
            "open_interest_change_pct": None,
            "funding_rate": funding_rate,
            "funding_bias": (
                "LONG_CROWDED" if funding_rate >= 0.001 else
                "SHORT_CROWDED" if funding_rate <= -0.001 else "BALANCED"
            ),
            "long_short_ratio": ratio,
            "samples": {
                "open_interest": 1,
                "funding": 1,
                "long_short_ratio": ratio_samples,
            },
            "provider": "Coinalyze",
            "provider_exchange": exchange,
            "provider_market_symbol": market_symbol,
            "data_quality": "provider_snapshot",
            "updated_at": datetime.fromtimestamp(max(valid_updates), timezone.utc).isoformat(),
            "liquidations": {"events": 0, "provider": None},
            "disclaimer": (
                "Coinalyze OI is converted to USD. Long/short ratio, when available, "
                "is a historical aggregate series; no account-level exposure or liquidation events are inferred."
            ),
        }
        _SNAPSHOT_CACHE[clean] = (time.monotonic() + 20, dict(snapshot))
        return snapshot
