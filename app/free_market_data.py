"""No-key daily market-data fallbacks.

Stooq supplies daily OHLCV for supported symbols. Frankfurter supplies daily
reference FX rates (close-only observations, not executable quotes or OHLC).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, timedelta


async def fetch_stooq_daily(client, symbol: str, limit: int = 300):
    clean = str(symbol).strip().lower()
    if not re.fullmatch(r"[a-z0-9.^_-]{1,24}", clean):
        raise ValueError("invalid_stooq_symbol")
    end = date.today()
    start = end - timedelta(days=max(180, min(limit * 3, 1500)))
    response = await client.get(
        "https://stooq.com/q/d/l/",
        params={"s": clean, "d1": start.strftime("%Y%m%d"),
                "d2": end.strftime("%Y%m%d"), "i": "d"},
        headers={"Accept": "text/csv"},
    )
    response.raise_for_status()
    reader = csv.DictReader(io.StringIO(response.text))
    rows = []
    for item in reader:
        try:
            stamp = int(__import__("datetime").datetime.strptime(item["Date"], "%Y-%m-%d").replace(
                tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
            values = [float(item[k]) for k in ("Open", "High", "Low", "Close")]
            volume = float(item.get("Volume") or 0)
            if min(values) <= 0 or values[2] > min(values[0], values[3]) or values[1] < max(values[0], values[3]):
                continue
            rows.append([str(stamp), *(str(x) for x in values), str(max(0, volume))])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    rows.sort(key=lambda x: int(x[0]))
    return rows[-max(60, min(limit, 500)):]


async def fetch_frankfurter_daily(client, symbol: str, limit: int = 300):
    clean = str(symbol).upper().replace("/", "").replace("_", "").replace("-", "")
    if not re.fullmatch(r"[A-Z]{6}", clean):
        raise ValueError("fx_symbol_must_be_six_letter_pair")
    base, quote = clean[:3], clean[3:]
    end = date.today()
    start = end - timedelta(days=max(180, min(limit * 3, 1500)))
    response = await client.get(
        f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}",
        params={"from": base, "to": quote},
    )
    response.raise_for_status()
    payload = response.json()
    rates = payload.get("rates") if isinstance(payload, dict) else None
    rows = []
    if isinstance(rates, dict):
        for day, values in rates.items():
            try:
                close = float(values[quote])
                stamp = int(__import__("datetime").datetime.strptime(day, "%Y-%m-%d").replace(
                    tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
                if close > 0:
                    rows.append([str(stamp), str(close), str(close), str(close), str(close), "0"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
    rows.sort(key=lambda x: int(x[0]))
    return rows[-max(60, min(limit, 500)):]


async def fetch_free_daily(client, market: str, symbol: str, limit: int = 300):
    market = market.lower()
    if market == "forex":
        rows = await fetch_frankfurter_daily(client, symbol, limit)
        provider = "Frankfurter"
        quality = "daily_reference_close_only"
    elif market in {"stocks", "indices", "commodities"}:
        raw = str(symbol).strip().lower()
        # Stooq symbols are intentionally explicit: e.g. aapl.us, ^spx, xauusd.
        rows = await fetch_stooq_daily(client, raw, limit)
        provider = "Stooq"
        quality = "daily_ohlcv"
    else:
        raise ValueError("unsupported_market")
    if len(rows) < 60:
        raise ValueError("fewer_than_60_daily_observations")
    return rows, {"provider": provider, "interval": "1d", "data_quality": quality,
                  "freshness": "daily", "auth_required": False,
                  "limitations": ("reference rates; OHLC and volume are not available"
                                  if market == "forex" else
                                  "coverage depends on the exact Stooq symbol")}
