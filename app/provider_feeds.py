"""Read-only, cached external feeds used by QUANT NEXUS engine enrichment.

No exchange order endpoints or trading credentials are used here. Provider
availability is reported separately from whether a paid credential is present.
"""
from __future__ import annotations

import asyncio
import copy
import os
import time
from datetime import datetime, timezone
from typing import Any

_CACHE: dict[str, tuple[float, Any]] = {}
_LOCKS: dict[str, asyncio.Lock] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coin(symbol: str) -> str:
    value = str(symbol or "").upper().strip()
    for suffix in ("USDT", "USDC", "-USD", "-USDT", "/USD", "/USDT"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value.replace("-", "").replace("/", "")


async def _cached(key: str, ttl_seconds: int, loader):
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and cached[0] > now:
        return copy.deepcopy(cached[1])
    lock = _LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _CACHE.get(key)
        if cached and cached[0] > now:
            return copy.deepcopy(cached[1])
        value = await loader()
        _CACHE[key] = (time.monotonic() + ttl_seconds, copy.deepcopy(value))
        return value


async def fetch_gdelt_news(client, symbol: str) -> dict:
    """Fetch symbol-related headlines from GDELT DOC 2.0 (public, no API key).

    GDELT asks clients to limit request frequency. A five-minute symbol cache
    prevents a 156-engine request from multiplying upstream news requests.
    """
    coin = _coin(symbol)
    aliases = {
        "BTC": '"Bitcoin" OR "BTC"',
        "ETH": '"Ethereum" OR "ETH"',
        "SOL": '"Solana" OR "SOL"',
        "XRP": '"XRP" OR "Ripple"',
        "BNB": '"BNB" OR "Binance Coin"',
    }
    terms = aliases.get(coin, f'"{coin}"')
    query = f'({terms}) AND (crypto OR cryptocurrency OR blockchain)'
    key = f"gdelt:{coin}"

    async def load():
        try:
            response = await client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": query,
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": 40,
                    "timespan": "24h",
                    "sort": "DateDesc",
                },
                headers={"User-Agent": "QUANT-NEXUS/1.0 (+read-only market research)"},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            if "json" not in content_type:
                return {"status": "unavailable", "provider": "GDELT", "reason": "non_json_response", "events": []}
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("articles", []), list):
                return {"status": "unavailable", "provider": "GDELT", "reason": "invalid_payload", "events": []}
            events = []
            for article in payload.get("articles", [])[:40]:
                if not isinstance(article, dict):
                    continue
                title = str(article.get("title") or "").strip()
                url = str(article.get("url") or "").strip()
                if not title or not url.startswith(("https://", "http://")):
                    continue
                events.append({
                    "title": title[:240],
                    "summary": "",
                    "source": "GDELT",
                    "domain": str(article.get("domain") or "")[:120],
                    "published_at": article.get("seendate"),
                    "url": url[:1500],
                    "language": article.get("language"),
                    "source_country": article.get("sourcecountry"),
                    "tone": article.get("tone"),
                    "symbol": coin,
                })
            return {
                "status": "ok" if events else "empty",
                "provider": "GDELT",
                "events": events,
                "event_count": len(events),
                "fetched_at": _utc_now(),
                "cache_ttl_seconds": 300,
                "warning": "Headline discovery only; GDELT tone and keyword matching are not fact verification.",
            }
        except Exception as exc:
            return {"status": "unavailable", "provider": "GDELT", "reason": type(exc).__name__, "events": []}

    return await _cached(key, 300, load)


async def fetch_cryptopanic_news(client, symbol: str, api_token: str | None = None) -> dict:
    """Use CryptoPanic only when the operator has supplied an API token."""
    token = api_token or os.getenv("CRYPTOPANIC_API_TOKEN", "")
    coin = _coin(symbol)
    if not token:
        return {
            "status": "missing_credentials",
            "provider": "CryptoPanic",
            "reason": "CRYPTOPANIC_API_TOKEN_not_configured",
            "events": [],
        }

    key = f"cryptopanic:{coin}"

    async def load():
        try:
            response = await client.get(
                "https://cryptopanic.com/api/developer/v2/posts/",
                params={"auth_token": token, "public": "true", "currencies": coin},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("results", []) if isinstance(payload, dict) else []
            events = []
            for item in rows[:40]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                url = str(item.get("url") or "").strip()
                if not title or not url.startswith(("https://", "http://")):
                    continue
                source = item.get("source") if isinstance(item.get("source"), dict) else {}
                events.append({
                    "title": title[:240],
                    "summary": "",
                    "source": "CryptoPanic",
                    "publisher": str(source.get("title") or "")[:120],
                    "published_at": item.get("created_at"),
                    "url": url[:1500],
                    "kind": item.get("kind"),
                    "symbol": coin,
                })
            return {
                "status": "ok" if events else "empty",
                "provider": "CryptoPanic",
                "events": events,
                "event_count": len(events),
                "fetched_at": _utc_now(),
                "cache_ttl_seconds": 120,
            }
        except Exception as exc:
            return {"status": "unavailable", "provider": "CryptoPanic", "reason": type(exc).__name__, "events": []}

    return await _cached(key, 120, load)


async def fetch_coinglass_liquidations(client, symbol: str, api_key: str | None = None) -> dict:
    """Fetch cross-exchange 1h liquidation totals from CoinGlass API v4.

    The Exchange List endpoint is available on all API plans, but still needs
    an API key. It provides aggregate USD totals, not individual liquidation
    prices; it must not be misrepresented as a liquidation heatmap.
    """
    key_value = api_key or os.getenv("COINGLASS_API_KEY", "")
    coin = _coin(symbol)
    if not key_value:
        return {
            "status": "missing_credentials",
            "provider": "CoinGlass",
            "reason": "COINGLASS_API_KEY_not_configured",
            "data_kind": "aggregate_liquidation_totals",
        }
    if not coin or len(coin) > 16 or not coin.isalnum():
        return {"status": "invalid_symbol", "provider": "CoinGlass"}

    key = f"coinglass_liquidations:{coin}"

    async def load():
        try:
            response = await client.get(
                "https://open-api-v4.coinglass.com/api/futures/liquidation/exchange-list",
                params={"symbol": coin, "range": "1h"},
                headers={"CG-API-KEY": key_value, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or str(payload.get("code")) != "0":
                return {"status": "unavailable", "provider": "CoinGlass", "reason": "provider_business_error"}
            rows = payload.get("data")
            if not isinstance(rows, list):
                return {"status": "unavailable", "provider": "CoinGlass", "reason": "invalid_payload"}
            total = next((row for row in rows if isinstance(row, dict) and str(row.get("exchange", "")).lower() == "all"), None)
            if total is None and rows and isinstance(rows[0], dict):
                total = rows[0]
            if total is None:
                return {"status": "empty", "provider": "CoinGlass", "data_kind": "aggregate_liquidation_totals"}
            return {
                "status": "ok",
                "provider": "CoinGlass",
                "symbol": coin,
                "range": "1h",
                "exchange_count": max(0, len(rows) - (1 if str(rows[0].get("exchange", "")).lower() == "all" else 0)),
                "total_liquidation_usd": _number(total.get("liquidation_usd")),
                "long_liquidation_usd": _number(total.get("longLiquidation_usd")),
                "short_liquidation_usd": _number(total.get("shortLiquidation_usd")),
                "fetched_at": _utc_now(),
                "data_kind": "aggregate_liquidation_totals_not_price_heatmap",
            }
        except Exception as exc:
            return {"status": "unavailable", "provider": "CoinGlass", "reason": type(exc).__name__}

    return await _cached(key, 10, load)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result >= 0 and result < float("inf") else None
    except (TypeError, ValueError, OverflowError):
        return None


def provider_configuration() -> dict:
    """Describe real provider readiness without exposing secret values."""
    coinglass = bool(os.getenv("COINGLASS_API_KEY"))
    coinalyze = bool(os.getenv("COINALYZE_API_KEY"))
    cryptopanic = bool(os.getenv("CRYPTOPANIC_API_TOKEN"))
    twelve = bool(os.getenv("TWELVE_DATA_API_KEY"))
    telegram = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    webhook = bool(os.getenv("ALERT_WEBHOOK_URL"))
    durable_db = os.getenv("PAPER_STORAGE_DURABLE", "false").lower() == "true"
    return {
        "read_only": True,
        "providers": {
            "bybit": {"status": "public_feed_configured", "auth_required": False, "markets": ["crypto spot", "crypto linear"]},
            "binance": {"status": "public_feed_configured", "auth_required": False, "markets": ["crypto spot", "crypto USD-M futures"], "regional_access_may_vary": True},
            "okx": {"status": "public_feed_configured", "auth_required": False, "markets": ["crypto spot", "swaps"]},
            "deribit": {"status": "public_feed_configured", "auth_required": False, "markets": ["BTC options", "ETH options"]},
            "gdelt": {"status": "public_feed_configured", "auth_required": False, "rate_limited": True, "cache_seconds": 300},
            "public_rss": {"status": "public_feed_configured", "auth_required": False, "feeds": ["Cointelegraph", "CoinDesk"]},
            "stooq": {"status": "public_feed_available", "auth_required": False, "markets": ["stocks", "indices", "commodities"], "frequency": "daily", "symbol_coverage_varies": True},
            "frankfurter": {"status": "public_feed_available", "auth_required": False, "markets": ["forex"], "frequency": "daily_reference_rates", "not_executable_quotes": True},
            "cryptopanic": {"status": "configured" if cryptopanic else "credential_required", "auth_required": True},
            "coinglass_liquidations": {"status": "configured" if coinglass else "credential_required", "auth_required": True, "minimum_plan": "Hobbyist for aggregate 1h exchange totals"},
            "coinalyze_derivatives": {"status": "configured" if coinalyze else "credential_required", "auth_required": True, "markets": ["USDT perpetual open interest", "funding rates", "historical long/short ratio"], "rate_limit_per_minute": 40},
            "twelve_data": {"status": "configured" if twelve else "optional_not_configured", "auth_required": True, "markets": ["forex", "stocks", "indices", "commodities"], "fallbacks": ["Frankfurter (daily FX reference rates)", "Stooq (daily OHLCV where symbol exists)"]},
        },
        "operations": {
            "telegram_delivery": "configured" if telegram else "credential_required",
            "generic_webhook_delivery": "configured" if webhook else "credential_required",
            "durable_sqlite_volume": "configured" if durable_db else "not_verified",
            "event_store": "sqlite_append_only_event_log",
            "event_store_durable": os.getenv("ENGINE_EVENT_STORAGE_DURABLE", os.getenv("PAPER_STORAGE_DURABLE", "false")).lower() == "true",
        },
        "missing_environment": [
            name for name, enabled in (
                ("TWELVE_DATA_API_KEY (optional; Stooq/Frankfurter daily fallback available)", twelve),
                ("COINGLASS_API_KEY", coinglass),
                ("COINALYZE_API_KEY", coinalyze),
                ("CRYPTOPANIC_API_TOKEN", cryptopanic),
                ("TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID", telegram),
                ("ALERT_WEBHOOK_URL", webhook),
                ("PAPER_STORAGE_DURABLE=true with persistent disk", durable_db),
            ) if not enabled
        ],
    }
