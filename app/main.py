import asyncio
import math
import os
import logging
import json
import re
import uuid
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .paper_store import PaperStore
from .quant_engine import ema_crossover_backtest, enrich_analysis
from .engine_registry import engine_registry
from .engine_catalog import engine_catalog
from .engine_suite import run_engine_suite, early_opportunity_assessment, catalogue_runtime_coverage
from .command_engine import COMMANDS, matches_command, evaluate_entry
from .derivatives_engine import summarize_derivatives, normalize_liquidations
from .advanced_engines import market_regime, market_structure, opportunity_assessment, learning_monitoring

BASE = Path(__file__).resolve().parent
app = FastAPI(title="QUANT NEXUS", version="1.0.0",
              description="Multi-market intelligence and paper trading only")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

logger = logging.getLogger("quant_nexus")

@app.middleware("http")
async def safe_error_middleware(request, call_next):
    request_id = uuid.uuid4().hex[:12]
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": "Internal server error. Check service logs with the request id.",
            "request_id": request_id
        }, headers={"X-Request-ID": request_id})

def safe_float(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default

BYBIT = "https://api.bybit.com"
BYBIT_LINEAR_WS = "wss://stream.bybit.com/v5/public/linear"
TIMEOUT = httpx.Timeout(12.0, connect=5.0)
HTTP_CLIENT: httpx.AsyncClient | None = None

def shared_http_client() -> httpx.AsyncClient:
    """Reuse pooled connections across market-data requests."""
    global HTTP_CLIENT
    if HTTP_CLIENT is None or HTTP_CLIENT.is_closed:
        HTTP_CLIENT = httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={"User-Agent":"QUANT-NEXUS/1.0"},
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
        )
    return HTTP_CLIENT

@app.on_event("shutdown")
async def close_shared_http_client():
    global HTTP_CLIENT
    if HTTP_CLIENT is not None and not HTTP_CLIENT.is_closed:
        await HTTP_CLIENT.aclose()
    HTTP_CLIENT = None
PAPER_STORE = PaperStore()
PAPER_BALANCE, PAPER_TRADES = PAPER_STORE.load()
PAPER_LOCK = asyncio.Lock()
AUTO_ENTRY_LOCK = asyncio.Lock()
LIQUIDATION_LOCK = asyncio.Lock()
LIQUIDATION_EVENTS: dict[str, list[dict]] = {}
PAPER_FEE_RATE = min(0.01, max(0.0, safe_float(os.getenv("PAPER_FEE_RATE"), 0.0006)))

def persist_paper_state():
    PAPER_STORE.save(PAPER_BALANCE, PAPER_TRADES)

def reset_paper_state(balance: float = 10000.0):
    global PAPER_BALANCE, PAPER_TRADES
    PAPER_BALANCE = float(balance)
    PAPER_TRADES = []
    PAPER_STORE.reset(PAPER_BALANCE)
LIVE_TRADING_ENABLED = False
INTERVALS = {"1m":"1", "3m":"3", "5m":"5", "15m":"15", "30m":"30",
             "1h":"60", "2h":"120", "4h":"240", "1d":"D", "1w":"W"}
TWELVE_DATA_INTERVALS = {
    "1m":"1min","5m":"5min","15m":"15min","30m":"30min",
    "1h":"1h","2h":"2h","4h":"4h","1d":"1day","1w":"1week",
}
TWELVE_DATA_MARKETS = {"forex","stocks","indices","commodities"}

async def bybit_get(path: str, params: dict):
    try:
        response = await shared_http_client().get(BYBIT + path, params=params)
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Bybit timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Bybit returned HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Bybit connection or response error") from exc
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise HTTPException(status_code=502, detail="Bybit returned an invalid response")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Bybit returned an invalid result payload")
    return result

async def okx_get(path: str, params: dict):
    try:
        response = await shared_http_client().get("https://www.okx.com" + path, params=params)
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="OKX timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"OKX returned HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="OKX connection or response error") from exc
    if not isinstance(payload, dict) or payload.get("code") != "0" or not isinstance(payload.get("data"), list):
        raise HTTPException(status_code=502, detail="OKX returned an invalid response")
    return payload["data"]

def okx_instrument(symbol: str, category: str) -> str:
    base = symbol.upper().replace("-", "")
    if category == "linear":
        if base.endswith("USDT"):
            return base[:-4] + "-USDT-SWAP"
        raise HTTPException(status_code=400, detail="Only USDT linear swaps are supported")
    if base.endswith("USDT"):
        return base[:-4] + "-USDT"
    raise HTTPException(status_code=400, detail="Only USDT spot pairs are supported")


async def _binance_get(category: str, path: str, params: dict):
    """Read public Binance market data; this client never signs or submits orders."""
    if category == "linear":
        bases = ("https://fapi.binance.com",)
    elif category == "spot":
        # Binance documents this market-data-only host as a no-API-key endpoint.
        bases = ("https://data-api.binance.vision", "https://api.binance.com")
    else:
        raise HTTPException(status_code=400, detail="Unsupported Binance market category")
    last_error = None
    for base in bases:
        try:
            response = await shared_http_client().get(base + path, params=params)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("code"), int) and payload["code"] < 0:
                raise HTTPException(status_code=502, detail="Binance returned a market-data error")
            return payload
        except httpx.TimeoutException as exc:
            last_error = HTTPException(status_code=504, detail="Binance market-data request timed out")
        except httpx.HTTPStatusError as exc:
            last_error = HTTPException(status_code=502, detail=f"Binance returned HTTP {exc.response.status_code}")
        except (httpx.RequestError, ValueError) as exc:
            last_error = HTTPException(status_code=502, detail="Binance connection or response error")
        except HTTPException as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise HTTPException(status_code=502, detail="Binance market data unavailable")


async def get_derivatives_snapshot(symbol: str) -> dict:
    """Return verified public OI/funding/long-short data with Bybit then Binance failover."""
    symbol = symbol.upper()
    if not symbol.endswith("USDT") or not symbol.replace("USDT", "").isalnum():
        raise HTTPException(status_code=400, detail="Only USDT linear symbols are supported")

    bybit_calls = await asyncio.gather(
        bybit_get("/v5/market/open-interest", {
            "category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 50
        }),
        bybit_get("/v5/market/funding/history", {
            "category": "linear", "symbol": symbol, "limit": 20
        }),
        bybit_get("/v5/market/account-ratio", {
            "category": "linear", "symbol": symbol, "period": "5min", "limit": 1
        }),
        return_exceptions=True,
    )
    oi_result, funding_result, ratio_result = bybit_calls
    if not isinstance(oi_result, Exception) and not isinstance(funding_result, Exception):
        summary = summarize_derivatives(
            oi_result.get("list", []), funding_result.get("list", [])
        )
        if summary.get("open_interest") is not None and summary.get("funding_rate") is not None:
            ratio_rows = ratio_result.get("list", []) if isinstance(ratio_result, dict) else []
            ratio = None
            if ratio_rows:
                buy_ratio = safe_float(ratio_rows[0].get("buyRatio"))
                sell_ratio = safe_float(ratio_rows[0].get("sellRatio"))
                ratio = buy_ratio / sell_ratio if sell_ratio > 0 else None
            return {
                **summary, "long_short_ratio": ratio, "provider": "Bybit",
                "data_quality": "provider_snapshot",
            }
        logger.warning("Bybit derivatives returned incomplete data for %s; falling back to Binance", symbol)
    else:
        logger.warning("Bybit derivatives unavailable for %s; falling back to Binance", symbol)
    binance_calls = await asyncio.gather(
        _binance_get("linear", "/fapi/v1/openInterest", {"symbol": symbol}),
        _binance_get("linear", "/futures/data/openInterestHist", {
            "symbol": symbol, "period": "5m", "limit": 30
        }),
        _binance_get("linear", "/fapi/v1/fundingRate", {"symbol": symbol, "limit": 10}),
        _binance_get("linear", "/futures/data/globalLongShortAccountRatio", {
            "symbol": symbol, "period": "5m", "limit": 1
        }),
        return_exceptions=True,
    )
    current_oi, oi_history, funding_history, ratio_history = binance_calls
    if isinstance(current_oi, Exception) or isinstance(funding_history, Exception):
        raise HTTPException(status_code=502, detail="Bybit and Binance derivatives feeds are unavailable")
    oi_value = safe_float(current_oi.get("openInterest")) if isinstance(current_oi, dict) else 0.0
    if oi_value <= 0:
        raise HTTPException(status_code=502, detail="Binance returned invalid open interest")
    oi_rows = oi_history if isinstance(oi_history, list) else []
    oi_values = [safe_float(x.get("sumOpenInterest")) for x in oi_rows if isinstance(x, dict)]
    oi_values = [x for x in oi_values if x > 0]
    oi_change = ((oi_values[-1] / oi_values[0]) - 1.0) * 100 if len(oi_values) >= 2 else None
    funding_rows = funding_history if isinstance(funding_history, list) else []
    funding_rows = [x for x in funding_rows if isinstance(x, dict) and x.get("fundingRate") is not None]
    funding_rate = safe_float(funding_rows[-1].get("fundingRate")) if funding_rows else None
    ratio_rows = ratio_history if isinstance(ratio_history, list) else []
    long_short_ratio = safe_float(ratio_rows[-1].get("longShortRatio")) if ratio_rows else None
    return {
        "open_interest": oi_value,
        "open_interest_change_pct": round(oi_change, 4) if oi_change is not None else None,
        "funding_rate": funding_rate,
        "funding_bias": "UNKNOWN" if funding_rate is None else (
            "LONG_CROWDED" if funding_rate >= 0.001 else
            "SHORT_CROWDED" if funding_rate <= -0.001 else "BALANCED"
        ),
        "long_short_ratio": long_short_ratio,
        "samples": {"open_interest": len(oi_values), "funding": len(funding_rows)},
        "provider": "Binance USD-M Futures",
        "data_quality": "provider_snapshot",
        "liquidations": {"events": 0, "provider": None},
        "disclaimer": "OI/funding/ratio are public aggregate metrics; liquidation positioning and account-level exposure are not inferred.",
    }


async def get_market_tickers(category: str):
    try:
        result = await bybit_get("/v5/market/tickers", {"category": category})
        items = result.get("list", [])
        if not isinstance(items, list) or not items:
            raise HTTPException(status_code=502, detail="Bybit ticker list is empty or invalid")
        return items, "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit ticker request failed (%s); falling back to OKX", bybit_error.detail)

    try:
        inst_type = "SWAP" if category == "linear" else "SPOT"
        items = await okx_get("/api/v5/market/tickers", {"instType": inst_type})
        normalized = []
        for x in items:
            inst_id = str(x.get("instId", ""))
            if category == "linear" and not inst_id.endswith("-USDT-SWAP"):
                continue
            if category == "spot" and not inst_id.endswith("-USDT"):
                continue
            symbol = inst_id.replace("-", "").replace("SWAP", "")
            last = safe_float(x.get("last"))
            open24 = safe_float(x.get("open24h"))
            change = ((last / open24) - 1) * 100 if open24 > 0 else 0
            quote_volume = safe_float(x.get("volCcy24h")) * last
            normalized.append({
                "symbol": symbol, "lastPrice": last, "price24hPcnt": change / 100,
                "highPrice24h": safe_float(x.get("high24h")),
                "lowPrice24h": safe_float(x.get("low24h")),
                "turnover24h": quote_volume, "volume24h": safe_float(x.get("vol24h")),
            })
        if normalized:
            return normalized, "OKX"
    except HTTPException as okx_error:
        logger.warning("OKX ticker request failed (%s); falling back to Binance", okx_error.detail)

    path = "/fapi/v1/ticker/24hr" if category == "linear" else "/api/v3/ticker/24hr"
    items = await _binance_get(category, path, {})
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Binance ticker response is invalid")
    normalized = []
    for item in items:
        symbol = str(item.get("symbol", "")).upper()
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():
            continue
        last = safe_float(item.get("lastPrice"))
        open_price = safe_float(item.get("openPrice"))
        if last <= 0:
            continue
        change_pct = safe_float(item.get("priceChangePercent"))
        normalized.append({
            "symbol": symbol, "lastPrice": last, "price24hPcnt": change_pct / 100,
            "highPrice24h": safe_float(item.get("highPrice")),
            "lowPrice24h": safe_float(item.get("lowPrice")),
            "turnover24h": safe_float(item.get("quoteVolume")),
            "volume24h": safe_float(item.get("volume")),
        })
    if not normalized:
        raise HTTPException(status_code=502, detail="No USDT ticker rows from configured market providers")
    return normalized, "Binance"


async def get_market_klines(symbol: str, category: str, interval: str, limit: int):
    try:
        result = await bybit_get("/v5/market/kline", {
            "category": category, "symbol": symbol.upper(),
            "interval": INTERVALS[interval], "limit": max(60, min(limit, 1000))
        })
        rows = result.get("list", [])
        if not isinstance(rows, list) or len(rows) < 20:
            raise HTTPException(status_code=502, detail="Bybit returned insufficient candles")
        return rows, "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit candles failed for %s (%s); falling back to OKX", symbol, bybit_error.detail)

    bars = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m",
            "1h":"1H","2h":"2H","4h":"4H","1d":"1D","1w":"1W"}
    try:
        rows = await okx_get("/api/v5/market/candles", {
            "instId": okx_instrument(symbol, category), "bar": bars[interval],
            "limit": str(max(60, min(limit, 300)))
        })
        if len(rows) < 20:
            raise HTTPException(status_code=502, detail="OKX returned insufficient candles")
        return [[row[0], row[1], row[2], row[3], row[4], row[5]] for row in rows], "OKX"
    except HTTPException as okx_error:
        logger.warning("OKX candles failed for %s (%s); falling back to Binance", symbol, okx_error.detail)

    path = "/fapi/v1/klines" if category == "linear" else "/api/v3/klines"
    rows = await _binance_get(category, path, {
        "symbol": symbol.upper(), "interval": interval, "limit": max(60, min(limit, 1000))
    })
    if not isinstance(rows, list) or len(rows) < 20:
        raise HTTPException(status_code=502, detail="Binance returned insufficient candles")
    return rows, "Binance"


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)
    return result

def rsi(values, period=14):
    if len(values) <= period:
        return None
    changes = [values[i] - values[i-1] for i in range(1, len(values))]
    gains = sum(max(x, 0) for x in changes[:period]) / period
    losses = sum(max(-x, 0) for x in changes[:period]) / period
    for change in changes[period:]:
        gains = (gains * (period - 1) + max(change, 0)) / period
        losses = (losses * (period - 1) + max(-change, 0)) / period
    if losses == 0:
        return 50.0 if gains == 0 else 100.0
    return 100 - 100 / (1 + gains / losses)

def macd(values, fast=12, slow=26, signal=9):
    if len(values) < slow + signal: return None, None, None
    line=[]
    for i in range(len(values)):
        a,b=ema(values[:i+1],fast),ema(values[:i+1],slow)
        if a is not None and b is not None: line.append(a-b)
    sig=ema(line,signal) if len(line)>=signal else None
    return (line[-1],sig,line[-1]-sig) if sig is not None else (None,None,None)

def analyze_klines(rows, include_all_candles=False):
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="Market provider returned invalid candle data")
    candles = []
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        try:
            timestamp = int(float(row[0]))
            values = [float(row[i]) for i in range(1, 6)]
        except (TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(v) for v in values):
            continue
        open_price, high_price, low_price, close_price, volume = values
        if min(open_price, high_price, low_price, close_price) <= 0 or volume < 0:
            continue
        if high_price < max(open_price, close_price, low_price) or low_price > min(open_price, close_price, high_price):
            continue
        candles.append({"time":timestamp//1000,"open":open_price,"high":high_price,
                        "low":low_price,"close":close_price,"volume":volume})
    candles.sort(key=lambda x:x["time"])
    if len(candles) < 20:
        raise HTTPException(status_code=502, detail="Not enough valid candle data from market provider")
    closes = [x["close"] for x in candles]
    highs = [x["high"] for x in candles]
    lows = [x["low"] for x in candles]
    volumes = [x["volume"] for x in candles]
    last = closes[-1]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    strength = rsi(closes)
    recent_volumes = volumes[-21:-1]
    avg_vol = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else None
    # Confirm breakouts with the last completed candle, excluding the still-forming candle.
    signal_candle = candles[-2] if len(candles) >= 2 else candles[-1]
    reference_candles = candles[-22:-2] if len(candles) >= 22 else candles[:-2]
    if not reference_candles:
        reference_candles = candles[:-1] or candles
    recent_high = max(x["high"] for x in reference_candles)
    recent_low = min(x["low"] for x in reference_candles)
    breakout = "UP" if signal_candle["close"] > recent_high else ("DOWN" if signal_candle["close"] < recent_low else "NONE")
    macd_line, macd_signal, macd_hist = macd(closes)
    typical=[(x['high']+x['low']+x['close'])/3 for x in candles]
    total_volume=sum(volumes)
    vwap=sum(p*v for p,v in zip(typical,volumes))/total_volume if total_volume>0 else None
    score = 50
    if e20 is not None and last > e20: score += 12
    elif e20 is not None: score -= 12
    if e50 is not None and e20 is not None and e20 > e50: score += 13
    elif e50 is not None and e20 is not None: score -= 13
    if strength is not None:
        score += 8 if 52 <= strength <= 68 else (-8 if strength < 42 or strength > 75 else 0)
    if vol_ratio is not None and vol_ratio >= 1.5: score += 10
    if macd_hist is not None: score += 7 if macd_hist > 0 else -7
    if vwap is not None: score += 5 if last > vwap else -5
    score = max(0, min(100, score))
    direction = "LONG" if score >= 62 else ("SHORT" if score <= 38 else "NEUTRAL")
    risk = max((recent_high - recent_low) * 0.35, last * 0.006)
    if direction == "LONG":
        stop, target1, target2 = last-risk, last+risk*1.5, last+risk*2.5
    elif direction == "SHORT":
        stop, target1, target2 = last+risk, last-risk*1.5, last-risk*2.5
    else:
        stop = target1 = target2 = None
    return enrich_analysis({"price":last,"change24h":None,"rsi":round(strength,2) if strength is not None else None,
            "ema20":e20,"ema50":e50,"macd":macd_line,"macdSignal":macd_signal,"macdHistogram":macd_hist,"vwap":vwap,"volumeRatio":round(vol_ratio,2) if vol_ratio is not None else None,
            "support":recent_low,"resistance":recent_high,"breakout":breakout,
            "breakoutClose":signal_candle["close"],"score":score,"direction":direction,
            "entry":last if direction != "NEUTRAL" else None,"stopLoss":stop,
            "target1":target1,"target2":target2,"candles":candles if include_all_candles else candles[-100:]})

@app.get("/health")
async def health():
    return {"application":"QUANT NEXUS","status":"ok","version":"1.0.0",
            "trading_mode":"simulation","live_trading_enabled":False,
            "utc":datetime.now(timezone.utc).isoformat()}

@app.get("/api/overview")
async def overview():
    return {"markets":["Crypto","Forex","US Stocks","Indices","Commodities"],
            "products":["Spot","Futures"],"live_markets":["Crypto Spot","Crypto Linear Futures"],
            "unconnected_markets":["Forex","US Stocks","Indices","Commodities"],
            "mode":"PAPER TRADING","live_trading_enabled":False}

@app.get("/api/markets")
async def markets(category: str = Query("spot", pattern="^(spot|linear)$"), limit: int = Query(100, ge=1, le=500)):
    items, provider = await get_market_tickers(category)
    items = [x for x in items if isinstance(x, dict)]
    items.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    return {"provider":provider,"category":category,"count":len(items),
            "items":[{"symbol":x.get("symbol"),"lastPrice":safe_float(x.get("lastPrice")),
            "change24h":safe_float(x.get("price24hPcnt"))*100,
            "high24h":safe_float(x.get("highPrice24h")),"low24h":safe_float(x.get("lowPrice24h")),
            "turnover24h":safe_float(x.get("turnover24h")),"volume24h":safe_float(x.get("volume24h"))}
            for x in items[:limit]]}

@app.get("/api/klines/{symbol}")
async def klines(symbol: str, category: str = "spot", interval: str = "15m", limit: int = 200):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid category or interval")
    rows, provider = await get_market_klines(symbol, category, interval, limit)
    analysis = analyze_klines(rows)
    analysis.update({"symbol":symbol.upper(),"category":category,"interval":interval,"provider":provider})
    return analysis

@app.get("/api/scan")
async def scan(category: str = "spot", interval: str = "15m", limit: int = Query(64, ge=1, le=500),
               min_turnover: float = Query(0, ge=0), direction: str = "all", depth: str = Query("AUTO", pattern="^(AUTO|32|64|128|256)$"), command_ids: str = ""):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid scan configuration")
    if direction.lower() not in ("all", "long", "short", "neutral"):
        raise HTTPException(status_code=400, detail="Invalid scan direction")
    selected_commands = [x.strip() for x in command_ids.split(",") if x.strip()]
    known_commands = {x["id"] for x in COMMANDS}
    unknown = sorted(set(selected_commands) - known_commands)
    if unknown:
        raise HTTPException(status_code=400, detail="Unknown command_ids: " + ", ".join(unknown))
    tickers, ticker_provider = await get_market_tickers(category)
    tickers = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    tickers.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    eligible = [x for x in tickers if safe_float(x.get("turnover24h")) >= min_turnover]
    # AUTO reviews the entire eligible USDT universe up to the bounded provider cap.
    depth_limit = {"32":32,"64":64,"128":128,"256":256}.get(depth, 500)
    effective_limit = min(len(eligible), limit, depth_limit)
    candidates = eligible[:effective_limit]
    semaphore = asyncio.Semaphore(12)
    async def one(ticker):
        async with semaphore:
            try:
                symbol = str(ticker.get("symbol", "")).upper()
                rows, candle_provider = await get_market_klines(symbol, category, interval, 100)
                if len(rows) < 20:
                    return None
                a = analyze_klines(rows)
                a.update({"symbol":symbol,"change24h":safe_float(ticker.get("price24hPcnt"))*100,
                          "turnover24h":safe_float(ticker.get("turnover24h")),
                          "volume24h":safe_float(ticker.get("volume24h")),
                          "high24h":safe_float(ticker.get("highPrice24h")),
                          "low24h":safe_float(ticker.get("lowPrice24h")),"provider":candle_provider})
                return a
            except HTTPException as exc:
                logger.warning("Skipping %s: %s", ticker.get("symbol"), exc.detail)
                return None
            except Exception:
                logger.exception("Skipping failed market analysis for %s", ticker.get("symbol"))
                return None
    results = await asyncio.gather(*(one(t) for t in candidates))
    filtered = []
    for item in results:
        if not item or (direction != "all" and item["direction"].lower() != direction.lower()):
            continue
        entry_state = evaluate_entry(item)
        item["entryConfirmation"] = entry_state
        item["matchedCommands"] = [cid for cid in selected_commands if matches_command(item, cid)]
        if selected_commands and not item["matchedCommands"]:
            continue
        filtered.append(item)
    results = filtered
    results.sort(key=lambda x:safe_float(x.get("score")), reverse=True)
    providers = sorted(set(x["provider"] for x in results))
    return {"provider":ticker_provider if len(providers)<=1 and not providers else (providers[0] if len(providers)==1 else "Mixed"),
            "providers":providers,"category":category,"interval":interval,"depth":depth,
            "universeAvailable":len(tickers),"eligibleCount":len(eligible),
            "effectiveDepth":len(candidates),"scanned":len(candidates),
            "truncated":len(eligible)>len(candidates),
            "returned":len(results),"generatedAt":datetime.now(timezone.utc).isoformat(),
            "trading_mode":"simulation","live_trading_enabled":False,"items":results}

@app.get("/api/early-opportunity-scan")
async def early_opportunity_scan(
    category: str = "spot",
    interval: str = "15m",
    depth: str = Query("AUTO", pattern="^(AUTO|32|64|128|256)$"),
    max_candidates: int = Query(256, ge=1, le=500),
    deep_limit: int = Query(24, ge=1, le=64),
    min_turnover: float = Query(0, ge=0),
):
    """Two-stage market-wide early-opportunity scan; deep analysis is bounded."""
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid scan market or interval")
    tickers, ticker_provider = await get_market_tickers(category)
    normalized = []
    for ticker in tickers:
        if not isinstance(ticker, dict):
            continue
        symbol = str(ticker.get("symbol", "")).upper()
        if not symbol.endswith("USDT") or not symbol[:-4].isalnum():
            continue
        turnover = safe_float(ticker.get("turnover24h"))
        if turnover < min_turnover:
            continue
        normalized.append(ticker)
    normalized.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    depth_cap = {"32": 32, "64": 64, "128": 128, "256": 256}.get(depth, max_candidates)
    candidates = normalized[:min(len(normalized), max_candidates, depth_cap)]
    semaphore = asyncio.Semaphore(12)

    async def light_pass(ticker):
        symbol = str(ticker.get("symbol", "")).upper()
        async with semaphore:
            try:
                raw, provider = await get_market_klines(symbol, category, interval, 120)
                analysis = analyze_klines(raw, include_all_candles=True)
                candles = analysis["candles"][:-1]
                if len(candles) < 60:
                    return None
                regime = market_regime(candles)
                structure = market_structure(candles)
                context = {
                    "symbol": symbol, "category": category, "interval": interval,
                    "candles": candles, "closes": [x["close"] for x in candles],
                    "regime": regime, "structure": structure,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
                result = early_opportunity_assessment(context)
                if result.get("status") != "computed":
                    return None
                result.update({
                    "provider": provider,
                    "last_price": candles[-1]["close"],
                    "turnover24h": safe_float(ticker.get("turnover24h")),
                    "change24h_pct": safe_float(ticker.get("price24hPcnt")) * 100,
                    "analysis_stage": "LIGHT",
                })
                return result
            except HTTPException as exc:
                logger.warning("Early scan skipped %s: %s", symbol, exc.detail)
                return None
            except Exception:
                logger.exception("Early scan failed for %s", symbol)
                return None

    light_results = await asyncio.gather(*(light_pass(t) for t in candidates))
    light_results = [x for x in light_results if x]
    light_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    deep_symbols = {x["symbol"] for x in light_results[:deep_limit]}

    async def deep_pass(item):
        if item["symbol"] not in deep_symbols:
            return item
        symbol = item["symbol"]
        async with semaphore:
            book_result, trades_result = await asyncio.gather(
                get_orderbook(symbol, category),
                get_recent_trades(symbol, category),
                return_exceptions=True,
            )
            try:
                raw, provider = await get_market_klines(symbol, category, interval, 160)
                analysis = analyze_klines(raw, include_all_candles=True)
                candles = analysis["candles"][:-1]
                if len(candles) < 60:
                    item["deep_analysis_error"] = "insufficient_completed_candles"
                    return item
                context = {
                    "symbol": symbol, "category": category, "interval": interval,
                    "candles": candles, "closes": [x["close"] for x in candles],
                    "regime": market_regime(candles),
                    "structure": market_structure(candles),
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
                if not isinstance(book_result, Exception):
                    bids, asks, _ = book_result
                    context["orderbook"] = {"bids": bids, "asks": asks}
                if not isinstance(trades_result, Exception):
                    trades, _ = trades_result
                    context["trades"] = trades
                if category == "linear":
                    try:
                        derivative_snapshot = await get_derivatives_snapshot(symbol)
                        context["derivatives"] = {
                            "open_interest": derivative_snapshot.get("open_interest"),
                            "open_interest_change_pct": derivative_snapshot.get("open_interest_change_pct"),
                            "funding_rate": derivative_snapshot.get("funding_rate"),
                            "long_short_ratio": derivative_snapshot.get("long_short_ratio"),
                            "provider": derivative_snapshot.get("provider"),
                        }
                    except Exception as exc:
                        logger.warning("Deep scan derivatives unavailable for %s: %s", symbol, type(exc).__name__)
                updated = early_opportunity_assessment(context)
                if updated.get("status") == "computed":
                    updated.update({
                        "provider": provider,
                        "last_price": candles[-1]["close"],
                        "turnover24h": item.get("turnover24h"),
                        "change24h_pct": item.get("change24h_pct"),
                        "analysis_stage": "DEEP",
                    })
                    return updated
                item["deep_analysis_error"] = updated.get("reason", "deep_analysis_unavailable")
                return item
            except Exception as exc:
                logger.warning("Deep early scan failed for %s: %s", symbol, type(exc).__name__)
                item["deep_analysis_error"] = type(exc).__name__
                return item

    deep_results = await asyncio.gather(*(deep_pass(x) for x in light_results))
    deep_results = [x for x in deep_results if x]
    deep_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "provider": ticker_provider,
        "category": category,
        "interval": interval,
        "depth": depth,
        "universe_available": len(normalized),
        "eligible_count": len(normalized),
        "scanned": len(candidates),
        "light_analyzed": len(light_results),
        "deep_analyzed": sum(x.get("analysis_stage") == "DEEP" for x in deep_results),
        "returned": len(deep_results),
        "truncated": len(normalized) > len(candidates),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": deep_results,
        "trading_mode": "simulation",
        "live_trading_enabled": False,
        "note": "Scores are heuristic research ranks, not calibrated win probabilities. Deep analysis is limited to the highest-ranked light-pass candidates.",
    }


@app.get("/api/multi-timeframe/{symbol}")
async def multi_timeframe(symbol: str, category: str = "spot"):
    if category not in ("spot", "linear"):
        raise HTTPException(status_code=400, detail="Invalid category")
    frames = ("5m", "15m", "1h", "4h")
    async def analyze_frame(frame):
        rows, provider = await get_market_klines(symbol, category, frame, 120)
        result = analyze_klines(rows)
        return {"interval": frame, "direction": result["direction"],
                "score": result["score"], "rsi": result["rsi"],
                "macdHistogram": result.get("macdHistogram"), "provider": provider}
    results = await asyncio.gather(*(analyze_frame(frame) for frame in frames), return_exceptions=True)
    items = []
    for frame, result in zip(frames, results):
        items.append({"interval": frame, "error": "بيانات هذا الإطار غير متاحة"}
                     if isinstance(result, Exception) else result)
    valid = [x for x in items if "score" in x]
    directions = {x["direction"] for x in valid if x["direction"] != "NEUTRAL"}
    average = round(sum(x["score"] for x in valid)/len(valid), 1) if valid else None
    aligned = len(valid) >= 2 and len(directions) == 1 and all(x["direction"] != "NEUTRAL" for x in valid)
    return {"symbol": symbol.upper(), "frames": items, "averageScore": average,
            "aligned": aligned, "validFrames": len(valid),
            "consensus": next(iter(directions)) if aligned else "MIXED_OR_INSUFFICIENT",
            "live_trading_enabled": False}

@app.get("/api/commands")
async def commands():
    return {"commands": COMMANDS, "count": len(COMMANDS),
            "scanner_mode": "selected_commands_only",
            "trading_mode": "simulation", "live_trading_enabled": False}


@app.get("/api/entry-monitor/{symbol}")
async def entry_monitor(symbol: str, category: str = "spot", interval: str = "15m"):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid market or interval")
    rows, provider = await get_market_klines(symbol, category, interval, 120)
    analysis = analyze_klines(rows)
    state = evaluate_entry(analysis)
    price = analysis.get("price")
    entry = analysis.get("entry")
    stop = analysis.get("stopLoss")
    target1, target2 = analysis.get("target1"), analysis.get("target2")
    progress = state["progress"]
    if state["confirmed"] and entry and price and target1 and target2:
        if analysis["direction"] == "LONG":
            progress = max(0, min(100, round((price-entry)/(target2-entry)*100))) if target2 != entry else 100
        else:
            progress = max(0, min(100, round((entry-price)/(entry-target2)*100))) if target2 != entry else 100
    return {"symbol": symbol.upper(), "category": category, "interval": interval,
            "provider": provider, "state": state["state"], "confirmed": state["confirmed"],
            "progress": progress, "reason": state["reason"], "direction": analysis["direction"],
            "price": price, "entry": entry, "stopLoss": stop, "target1": target1,
            "target2": target2, "score": analysis["score"], "rsi": analysis["rsi"],
            "volumeRatio": analysis["volumeRatio"], "breakout": analysis["breakout"],
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "trading_mode": "simulation", "live_trading_enabled": False}



async def _auto_paper_entry_locked(symbol: str, category: str = "spot", interval: str = "15m"):
    """Open a paper position only for a manually watched symbol with a fresh confirmed setup."""
    global PAPER_BALANCE
    symbol = symbol.upper()
    if not symbol.endswith("USDT") or not symbol.replace("USDT", "").isalnum():
        raise HTTPException(status_code=400, detail="Only USDT symbols are supported")
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid market or interval")
    rows, provider = await get_market_klines(symbol, category, interval, 120)
    analysis = analyze_klines(rows)
    confirmation = evaluate_entry(analysis)
    side = str(analysis.get("direction", "NEUTRAL")).upper()
    entry = safe_float(analysis.get("entry"))
    stop = safe_float(analysis.get("stopLoss"))
    target = safe_float(analysis.get("target2"))
    score = safe_float(analysis.get("score"))
    if not confirmation.get("confirmed") or score < 85:
        return {"opened": False, "state": confirmation.get("state", "WAITING"),
                "reason": confirmation.get("reason", "شروط الدخول غير مكتملة"),
                "score": score, "symbol": symbol, "trading_mode": "simulation",
                "live_trading_enabled": False}
    if side not in ("LONG", "SHORT") or (category == "spot" and side != "LONG"):
        return {"opened": False, "state": "CONFIRMED_NOT_ELIGIBLE",
                "reason": "اتجاه الصفقة غير مدعوم لهذا السوق", "score": score,
                "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False}
    if not all(math.isfinite(v) and v > 0 for v in (entry, stop, target)):
        return {"opened": False, "state": "INVALID_PLAN",
                "reason": "خطة الدخول أو الوقف أو الهدف غير مكتملة", "score": score,
                "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False}
    if (side == "LONG" and not stop < entry < target) or (side == "SHORT" and not target < entry < stop):
        return {"opened": False, "state": "INVALID_PLAN",
                "reason": "ترتيب الدخول والوقف والهدف غير صالح", "score": score,
                "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False}
    async with PAPER_LOCK:
        existing = next((t for t in PAPER_TRADES if t["status"] == "OPEN" and
                         t["symbol"] == symbol and t.get("category", "spot") == category), None)
        if existing:
            return {"opened": False, "state": "ALREADY_OPEN", "trade": existing,
                    "reason": "يوجد مركز تجريبي مفتوح لهذه العملة", "symbol": symbol,
                    "trading_mode": "simulation", "live_trading_enabled": False}
        open_count = sum(t["status"] == "OPEN" for t in PAPER_TRADES)
        if open_count >= 5:
            return {"opened": False, "state": "POSITION_LIMIT",
                    "reason": "تم بلوغ الحد الأقصى وهو 5 مراكز تجريبية مفتوحة",
                    "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False}
        balance = PAPER_BALANCE
    distance = abs(entry - stop)
    # Size to a maximum 1% account risk, including estimated entry and stop fees.
    risk_budget = balance * 0.01
    risk_per_unit = distance + (entry + stop) * PAPER_FEE_RATE
    quantity = risk_budget / risk_per_unit if risk_per_unit > 0 else 0
    if quantity <= 0:
        return {"opened": False, "state": "INVALID_SIZE", "reason": "تعذر حساب حجم المركز",
                "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False}
    try:
        result = await open_paper_trade(PaperTrade(
            symbol=symbol, side=side, category=category, leverage=1,
            entry=entry, quantity=quantity, stop_loss=stop, take_profit=target))
    except HTTPException as exc:
        return {"opened": False, "state": "RISK_REJECTED", "reason": exc.detail,
                "symbol": symbol, "score": score, "trading_mode": "simulation",
                "live_trading_enabled": False}
    return {"opened": True, "state": "PAPER_OPEN", "trade": result["trade"],
            "score": score, "provider": provider, "confirmation": confirmation,
            "riskBudget": round(risk_budget, 8), "trading_mode": "simulation",
            "live_trading_enabled": False}


@app.post("/api/paper/auto-entry/{symbol}")
async def auto_paper_entry(symbol: str, category: str = "spot", interval: str = "15m"):
    # Serialize automatic entry attempts so simultaneous polling cycles cannot race each other.
    async with AUTO_ENTRY_LOCK:
        return await _auto_paper_entry_locked(symbol, category, interval)


@app.get("/api/engine/status")
async def engine_status():
    return {"engine": "QUANT INTELLIGENCE",
            "engine_version": "2.0",
            "capabilities": ["technical_analysis", "multi_timeframe", "adaptive_scanner", "signal_explanations", "historical_backtest", "paper_risk_controls", "orderbook_liquidity", "large_trade_flow", "paper_auto_monitor", "position_sizing"],
            "indicators": ["EMA20", "EMA50", "RSI14", "MACD12-26-9", "VWAP", "VolumeRatio", "ATR14"],
            "scan_depths": [32, 64, 128, 256, "AUTO"],
            "markets": {"spot": True, "linear_futures": True, "forex": False,
                        "us_stocks": False, "indices": False, "commodities": False},
            "market_data": {"connected": ["crypto_spot", "crypto_linear_futures"],
                            "not_configured": ["forex", "us_stocks", "indices", "commodities"]},
            "paper_storage": "sqlite",
            "durable_storage_configured": PAPER_STORE.durable_configured,
            "paper_fee_rate_per_side": PAPER_FEE_RATE,
            "trading_mode": "simulation", "live_trading_enabled": False}

@app.get("/api/regime/{symbol}")
async def regime_endpoint(symbol: str, category: str = "spot", interval: str = "1h", limit: int = Query(200, ge=60, le=500)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid category or interval")
    rows, provider = await get_market_klines(symbol.upper(), category, interval, limit)
    analysis = analyze_klines(rows, include_all_candles=True)
    result = market_regime(analysis["candles"])
    return {"symbol":symbol.upper(),"category":category,"interval":interval,"provider":provider,**result,
            "trading_mode":"simulation","live_trading_enabled":False}


@app.get("/api/structure/{symbol}")
async def structure_endpoint(symbol: str, category: str = "spot", interval: str = "1h", limit: int = Query(200, ge=40, le=500)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid category or interval")
    rows, provider = await get_market_klines(symbol.upper(), category, interval, limit)
    analysis = analyze_klines(rows, include_all_candles=True)
    result = market_structure(analysis["candles"])
    return {"symbol":symbol.upper(),"category":category,"interval":interval,"provider":provider,**result,
            "trading_mode":"simulation","live_trading_enabled":False}


@app.get("/api/opportunity/{symbol}")
async def opportunity_endpoint(symbol: str, category: str = "spot", interval: str = "15m", limit: int = Query(200, ge=60, le=500)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid category or interval")
    rows, provider = await get_market_klines(symbol.upper(), category, interval, limit)
    analysis = analyze_klines(rows, include_all_candles=True)
    analysis["symbol"] = symbol.upper()
    regime = market_regime(analysis["candles"])
    structure = market_structure(analysis["candles"])
    result = opportunity_assessment(analysis, regime, structure)
    return {"provider":provider,"regime":regime,"structure":structure,**result}


@app.get("/api/learning/monitoring")
async def learning_monitoring_endpoint():
    async with PAPER_LOCK:
        closed = [dict(t) for t in PAPER_TRADES if t.get("status") == "CLOSED"]
        opened = [dict(t) for t in PAPER_TRADES if t.get("status") == "OPEN"]
    return {**learning_monitoring(closed, opened),"trading_mode":"simulation","live_trading_enabled":False}


@app.get("/api/engines")
async def engines():
    """Return implementation status for the 15 logical QUANT NEXUS engines."""
    return engine_registry()


@app.get("/api/engine-catalog")
async def engine_catalog_endpoint():
    """Return the auditable 156-engine catalogue and honest implementation states."""
    return engine_catalog()

@app.get("/api/engine-suite/coverage")
async def engine_suite_coverage():
    """Show how many catalogue entries have callable runtime adapters."""
    return catalogue_runtime_coverage()


async def _public_json(url: str, params: dict | None = None) -> dict:
    """Fetch a read-only public JSON endpoint without ever using trading credentials."""
    response = await shared_http_client().get(url, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("invalid_json_object")
    if payload.get("error"):
        raise ValueError("provider_error")
    return payload


async def _rss_news_events() -> tuple[list[dict], dict]:
    """Read public crypto RSS headlines; keyword triage is not factual verification."""
    feeds = {
        "Cointelegraph": "https://cointelegraph.com/rss",
        "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    }

    async def fetch_one(name: str, url: str):
        try:
            response = await shared_http_client().get(url, headers={"Accept":"application/rss+xml, application/xml, text/xml"})
            response.raise_for_status()
            root = ET.fromstring(response.text)
            items = root.findall(".//item")
            events = []
            for item in items[:30]:
                title = unescape(re.sub(r"<[^>]+>", " ", item.findtext("title") or "")).strip()
                summary = unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()
                if not title:
                    continue
                events.append({
                    "title": title[:200], "summary": summary[:700],
                    "source": name, "published_at": item.findtext("pubDate"),
                    "url": item.findtext("link"),
                })
            return events, {"status":"ok", "items":len(events)}
        except Exception as exc:
            logger.warning("RSS source %s unavailable: %s", name, type(exc).__name__)
            return [], {"status":"unavailable", "reason":type(exc).__name__}

    results = await asyncio.gather(*(fetch_one(name, url) for name, url in feeds.items()))
    events = [event for batch, _ in results for event in batch]
    status = {name: result for name, result in zip(feeds, [x[1] for x in results])}
    return events[:50], status


async def _deribit_options_snapshot(symbol: str) -> tuple[list[dict] | None, float | None, dict]:
    """Read BTC/ETH option instruments and summaries from Deribit's public market API."""
    base = symbol.upper().replace("USDT", "")
    if base not in ("BTC", "ETH"):
        return None, None, {"status":"unsupported_asset", "provider":"Deribit", "supported_assets":["BTC","ETH"]}
    root = "https://www.deribit.com/api/v2/public"
    try:
        instruments_payload, summary_payload = await asyncio.gather(
            _public_json(root + "/get_instruments", {"currency":base,"kind":"option","expired":"false"}),
            _public_json(root + "/get_book_summary_by_currency", {"currency":base,"kind":"option"}),
        )
        instruments = instruments_payload.get("result")
        summaries = summary_payload.get("result")
        if not isinstance(instruments, list) or not isinstance(summaries, list):
            raise ValueError("invalid_options_payload")
        by_name = {str(x.get("instrument_name")):x for x in instruments if isinstance(x,dict)}
        now_ms = int(datetime.now(timezone.utc).timestamp()*1000)
        chain = []
        underlying = None
        for summary in summaries:
            if not isinstance(summary,dict):
                continue
            name = str(summary.get("instrument_name",""))
            instrument = by_name.get(name)
            if not instrument or instrument.get("is_active") is False:
                continue
            underlying = underlying or safe_float(summary.get("underlying_price")) or None
            expiry = safe_float(instrument.get("expiration_timestamp"))
            strike = safe_float(instrument.get("strike"))
            days = (expiry-now_ms)/86400000 if expiry>now_ms else 0
            option_type = str(instrument.get("option_type","")).upper()
            mark_iv = safe_float(summary.get("mark_iv"))
            iv = mark_iv/100 if mark_iv>5 else mark_iv
            oi = safe_float(summary.get("open_interest"))
            if days<=0 or strike<=0 or iv<=0 or option_type not in ("CALL","PUT"):
                continue
            if underlying and abs(strike/underlying-1)>0.35:
                continue
            chain.append({
                "symbol":name, "type":option_type, "strike":strike,
                "days_to_expiry":days, "implied_volatility":iv,
                "open_interest":oi,
                "contract_multiplier":safe_float(instrument.get("contract_size"),1.0) or 1.0,
                "risk_free_rate":safe_float(summary.get("interest_rate")),
            })
        chain.sort(key=lambda x:(x["days_to_expiry"],abs(x["strike"]-(underlying or x["strike"]))))
        chain = chain[:160]
        if not chain or not underlying or underlying<=0:
            return None, None, {"status":"unavailable", "provider":"Deribit", "reason":"no_valid_option_chain"}
        return chain, underlying, {
            "status":"ok", "provider":"Deribit", "contracts":len(chain),
            "underlying":base, "dealer_positioning":"not_provided",
            "warning":"Public option-chain snapshot. Dealer-side positioning is unavailable; net dealer gamma must remain unset.",
        }
    except Exception as exc:
        logger.warning("Deribit options unavailable for %s: %s", symbol, type(exc).__name__)
        return None, None, {"status":"unavailable", "provider":"Deribit", "reason":type(exc).__name__}


async def _cross_exchange_marks(symbol: str, category: str) -> tuple[dict, dict]:
    """Collect independently sourced venue marks for spread observation, not execution."""
    marks: dict[str,float] = {}
    failures: dict[str,str] = {}

    async def bybit_mark():
        data = await bybit_get("/v5/market/tickers", {"category":category,"symbol":symbol})
        rows = data.get("list",[])
        if not rows:
            raise ValueError("empty_ticker")
        value = safe_float(rows[0].get("lastPrice"))
        if value<=0:
            raise ValueError("invalid_price")
        return value

    async def okx_mark():
        rows = await okx_get("/api/v5/market/ticker", {"instId":okx_instrument(symbol,category)})
        value = safe_float(rows[0].get("last")) if rows else 0
        if value<=0:
            raise ValueError("invalid_price")
        return value

    async def binance_mark():
        path = "/fapi/v1/ticker/price" if category=="linear" else "/api/v3/ticker/price"
        row = await _binance_get(category,path,{"symbol":symbol})
        value = safe_float(row.get("price")) if isinstance(row,dict) else 0
        if value<=0:
            raise ValueError("invalid_price")
        return value

    names = ("Bybit","OKX","Binance")
    results = await asyncio.gather(bybit_mark(),okx_mark(),binance_mark(),return_exceptions=True)
    for name, result in zip(names,results):
        if isinstance(result,Exception):
            failures[name] = type(result).__name__
        else:
            marks[name] = result
    return marks, {"available_venues":sorted(marks),"unavailable_venues":failures}


async def _spot_and_linear_marks(symbol: str) -> tuple[dict,dict]:
    async def one(category: str):
        try:
            rows, provider = await get_market_tickers(category)
            item = next((x for x in rows if str(x.get("symbol","")).upper()==symbol),None)
            price = safe_float(item.get("lastPrice")) if item else 0
            return price if price>0 else None, provider if price>0 else None
        except Exception as exc:
            return None, type(exc).__name__
    spot, linear = await asyncio.gather(one("spot"),one("linear"))
    values = {}
    if spot[0]:
        values["spot_price"] = spot[0]
        values["spot_price_provider"] = spot[1]
    if linear[0]:
        values["futures_price"] = linear[0]
        values["futures_price_provider"] = linear[1]
    return values, {
        "spot": {"status":"ok" if spot[0] else "unavailable", "provider":spot[1]},
        "linear": {"status":"ok" if linear[0] else "unavailable", "provider":linear[1]},
    }


async def _aligned_peer_closes(symbol: str, category: str, interval: str, base_candles: list[dict]) -> tuple[list[float],dict,dict]:
    """Build strictly timestamp-aligned returns against a small liquid crypto peer basket."""
    peers = [x for x in ("BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT") if x!=symbol][:3]
    base = {int(x.get("time",0)):safe_float(x.get("close")) for x in base_candles if int(x.get("time",0))>0}
    batches = await asyncio.gather(
        *(get_market_klines(peer,category,interval,180) for peer in peers),
        return_exceptions=True,
    )
    related = {}
    status = {}
    aligned_times = set(base)
    for peer, batch in zip(peers,batches):
        if isinstance(batch,Exception):
            status[peer] = {"status":"unavailable","reason":type(batch).__name__}
            continue
        raw, provider = batch
        try:
            parsed = analyze_klines(raw,include_all_candles=True)["candles"][:-1]
            values = {int(x["time"]):safe_float(x["close"]) for x in parsed if safe_float(x["close"])>0}
            aligned_times &= set(values)
            related[peer] = values
            status[peer] = {"status":"ok","provider":provider,"candles":len(values)}
        except Exception as exc:
            status[peer] = {"status":"unavailable","reason":type(exc).__name__}
    times = sorted(aligned_times)
    if len(times)<60:
        return [],{},{"aligned_samples":len(times),"peers":status,"status":"insufficient_overlap"}
    base_values = [base[t] for t in times]
    peer_values = {peer:[values[t] for t in times] for peer,values in related.items() if all(t in values for t in times)}
    if not peer_values:
        return [],{},{"aligned_samples":len(times),"peers":status,"status":"unavailable"}
    return base_values,peer_values,{"aligned_samples":len(times),"peers":status,"status":"ok"}


async def collect_engine_enrichment(symbol: str, category: str, interval: str, base_candles: list[dict]) -> tuple[dict,dict]:
    """Connect read-only optional evidence feeds for all compatible engine adapters."""
    context: dict = {}
    providers: dict = {}
    jobs = await asyncio.gather(
        get_derivatives_snapshot(symbol),
        _aligned_peer_closes(symbol,category,interval,base_candles),
        _cross_exchange_marks(symbol,category),
        _spot_and_linear_marks(symbol),
        _rss_news_events(),
        _deribit_options_snapshot(symbol),
        return_exceptions=True,
    )
    derivatives, peers, exchange, basis, news, options = jobs

    if not isinstance(derivatives,Exception):
        context["derivatives"] = {
            "open_interest":derivatives.get("open_interest"),
            "open_interest_change_pct":derivatives.get("open_interest_change_pct"),
            "funding_rate":derivatives.get("funding_rate"),
            "long_short_ratio":derivatives.get("long_short_ratio"),
            "provider":derivatives.get("provider"),
        }
        providers["derivatives"] = {"status":"ok","provider":derivatives.get("provider")}
    else:
        providers["derivatives"] = {"status":"unavailable","reason":type(derivatives).__name__}

    if not isinstance(peers,Exception):
        base_values, related_values, peer_status = peers
        if base_values and related_values:
            context["correlation_base_closes"] = base_values
            context["related_closes"] = related_values
        providers["cross_market"] = peer_status
    else:
        providers["cross_market"] = {"status":"unavailable","reason":type(peers).__name__}

    if not isinstance(exchange,Exception):
        marks, mark_status = exchange
        if marks:
            context["exchange_prices"] = marks
            context["exchange_price_providers"] = mark_status
        providers["cross_exchange"] = {"status":"ok" if len(marks)>=2 else "partial",**mark_status}
    else:
        providers["cross_exchange"] = {"status":"unavailable","reason":type(exchange).__name__}

    if not isinstance(basis,Exception):
        values, basis_status = basis
        context.update(values)
        providers["spot_futures_basis"] = basis_status
    else:
        providers["spot_futures_basis"] = {"status":"unavailable","reason":type(basis).__name__}

    if not isinstance(news,Exception):
        events, news_status = news
        context["news_events"] = events
        providers["news"] = {"status":"ok" if events else "unavailable","sources":news_status,"event_count":len(events)}
    else:
        providers["news"] = {"status":"unavailable","reason":type(news).__name__}

    if not isinstance(options,Exception):
        chain, underlying, option_status = options
        if chain and underlying:
            context["options_chain"] = chain
            context["underlying_price"] = underlying
        providers["options"] = option_status
    else:
        providers["options"] = {"status":"unavailable","reason":type(options).__name__}

    return context, providers


def _runtime_memory_snapshot() -> dict:
    """Read process/container memory from Linux procfs; CPU is intentionally not guessed."""
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        rss = pages * os.sysconf("SC_PAGE_SIZE")
        total = 0
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                total = int(line.split()[1]) * 1024
                break
        return {
            "memory_rss_bytes":rss,
            "memory_pct":round(rss/total*100,3) if total>0 else None,
            "cpu_pct":None,
            "source":"linux_procfs",
        }
    except Exception:
        return {"memory_rss_bytes":None,"memory_pct":None,"cpu_pct":None,"source":"unavailable"}



@app.get("/api/engine-suite/{symbol}")
@app.get("/api/early-opportunity/{symbol}")
async def market_engine_suite(symbol: str, category: str = "spot", interval: str = "15m",
                              limit: int = Query(300, ge=60, le=500),
                              engine_ids: str | None = None):
    """Run the 156-engine catalogue against one validated, read-only market snapshot."""
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid market category or interval")
    symbol = symbol.upper()
    if not symbol.endswith("USDT") or not symbol.replace("USDT", "").isalnum():
        raise HTTPException(status_code=400, detail="Only USDT crypto symbols are supported")
    raw_rows, provider = await get_market_klines(symbol, category, interval, limit)
    analysis = analyze_klines(raw_rows, include_all_candles=True)
    # Exchange kline endpoints commonly include a still-forming final candle.
    # Exclude it from all signal calculations to prevent intrabar repainting.
    completed = analysis["candles"][:-1]
    if len(completed) < 60:
        raise HTTPException(status_code=502, detail="At least 60 completed candles are required")
    analysis["candles"] = completed
    closes = [x["close"] for x in completed]
    regime = market_regime(completed)
    structure = market_structure(completed)

    book_result, trade_result = await asyncio.gather(
        get_orderbook(symbol, category), get_recent_trades(symbol, category),
        return_exceptions=True
    )
    async with PAPER_LOCK:
        paper_equity = PAPER_BALANCE
        paper_positions = [dict(x) for x in PAPER_TRADES]
    # Use the same completed-candle entry gate as the monitoring room. The
    # analysis object still contains the provider's last (possibly forming) bar
    # here; evaluate_entry deliberately discards it before confirmation.
    entry_confirmation = evaluate_entry(analysis)
    analysis["candles"] = completed

    closed_trades = [x for x in paper_positions if x.get("status") == "CLOSED"]
    today_utc = datetime.now(timezone.utc).date().isoformat()
    daily_pnl = sum(
        safe_float(x.get("pnl")) for x in closed_trades
        if str(x.get("closedAt", "")).startswith(today_utc)
    )
    daily_loss_limit_pct = min(10.0, max(
        0.1, safe_float(os.getenv("PAPER_DAILY_LOSS_LIMIT_PCT"), 3.0)
    ))
    volatility_ranges = []
    previous_close = completed[0]["close"]
    for candle in completed[1:]:
        volatility_ranges.append(max(
            candle["high"] - candle["low"],
            abs(candle["high"] - previous_close),
            abs(candle["low"] - previous_close),
        ))
        previous_close = candle["close"]
    atr14 = sum(volatility_ranges[-14:]) / min(14, len(volatility_ranges)) if volatility_ranges else 0.0
    last_completed_price = completed[-1]["close"]
    volatility_pct = atr14 / last_completed_price * 100 if last_completed_price > 0 else 0.0

    direction = str(analysis.get("direction", "NEUTRAL")).upper()
    entry = safe_float(analysis.get("entry"))
    stop = safe_float(analysis.get("stopLoss"))
    plan = {}
    if (
        direction in ("LONG", "SHORT") and entry > 0 and stop > 0 and entry != stop
        and not (category == "spot" and direction == "SHORT")
    ):
        plan = {"side": direction, "entry": entry, "stop": stop}
    daily_loss_breached = (
        paper_equity > 0 and max(0.0, -daily_pnl) / paper_equity * 100 >= daily_loss_limit_pct
    )
    risk_checks = {
        "paper_equity_positive": paper_equity > 0,
        "fresh_completed_candle_confirmation": entry_confirmation.get("confirmed") is True,
        "valid_entry_and_stop_plan": bool(plan),
        "daily_loss_limit_not_breached": not daily_loss_breached,
        "visible_orderbook_available": False,
        "recent_trade_flow_available": False,
        "spot_direction_supported": not (category == "spot" and direction == "SHORT"),
        "live_trading_disabled": LIVE_TRADING_ENABLED is False,
    }
    risk_approval = {
        "approved": all(risk_checks.values()),
        "failed_checks": [key for key, passed in risk_checks.items() if not passed],
    }
    strategy_returns = []
    for trade in closed_trades:
        pnl = safe_float(trade.get("pnl"), float("nan"))
        denominator = safe_float(trade.get("margin")) or (
            safe_float(trade.get("entry")) * safe_float(trade.get("quantity"))
        )
        if math.isfinite(pnl) and denominator > 0:
            strategy_returns.append(pnl / denominator)

    context = {
        "symbol": symbol, "category": category, "interval": interval,
        "candles": completed, "closes": closes,
        "analysis": analysis, "regime": regime, "structure": structure,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "account": {"equity": paper_equity},
        "positions": paper_positions,
        "closed_trades": closed_trades,
        "current_prices": {symbol: last_completed_price},
        "plan": plan,
        "risk_pct": 1.0,
        "volatility_pct": volatility_pct,
        "daily_pnl": daily_pnl,
        "daily_loss_limit_pct": daily_loss_limit_pct,
        "strategy_returns": strategy_returns,
        "entry_confirmation": entry_confirmation,
        "risk_checks": risk_checks,
        "risk_approval": risk_approval,
        "reward_risk_targets": [1.5, 2.0, 3.0],
    }
    auxiliary = {"orderbook": False, "trade_flow": False, "derivatives": False}
    if not isinstance(book_result, Exception):
        bids, asks, book_provider = book_result
        context["orderbook"] = {"bids": bids, "asks": asks}
        auxiliary["orderbook"] = True
        risk_checks["visible_orderbook_available"] = True
    else:
        logger.warning("Engine suite orderbook unavailable for %s: %s", symbol, type(book_result).__name__)
    if not isinstance(trade_result, Exception):
        trades, trade_provider = trade_result
        context["trades"] = trades
        auxiliary["trade_flow"] = True
        risk_checks["recent_trade_flow_available"] = True
    else:
        logger.warning("Engine suite trade flow unavailable for %s: %s", symbol, type(trade_result).__name__)
    # Populate independent 5m/1h/4h snapshots for timeframe-specific adapters.
    frames = {}
    frame_names = ("5m", "1h", "4h")
    frame_results = await asyncio.gather(
        *(get_market_klines(symbol, category, frame, 120) for frame in frame_names),
        return_exceptions=True
    )
    for frame, frame_result in zip(frame_names, frame_results):
        if isinstance(frame_result, Exception):
            logger.warning("Engine suite timeframe %s unavailable for %s: %s", frame, symbol, type(frame_result).__name__)
            continue
        frame_rows, frame_provider = frame_result
        try:
            frame_analysis = analyze_klines(frame_rows, include_all_candles=True)
            frame_candles = frame_analysis["candles"][:-1]
            if frame_candles:
                frames[frame] = {
                    "timeframe": frame, "direction": frame_analysis["direction"],
                    "score": frame_analysis["score"], "provider": frame_provider,
                    "completed_bars": len(frame_candles),
                }
        except HTTPException:
            continue
    context["timeframes"] = frames
    context["risk_approval"] = {
        "approved": all(risk_checks.values()),
        "failed_checks": [key for key, passed in risk_checks.items() if not passed],
    }

    enrichment, provider_health = await collect_engine_enrichment(symbol, category, interval, completed)
    context.update(enrichment)
    auxiliary["derivatives"] = isinstance(context.get("derivatives"),dict) and (
        context["derivatives"].get("open_interest") is not None and
        context["derivatives"].get("funding_rate") is not None
    )
    async with LIQUIDATION_LOCK:
        context["liquidations"] = list(LIQUIDATION_EVENTS.get(symbol, []))

    context["cache"] = {"status":"ok","backend":"process-local","persistent":False}
    context["database"] = {
        "status":"ok" if bool(getattr(PAPER_STORE,"durable_configured",False)) else "degraded",
        "backend":"sqlite",
        "persistent":bool(getattr(PAPER_STORE,"durable_configured",False)),
        "path_configured":bool(os.getenv("PAPER_DB_PATH")),
    }
    context["websocket"] = {
        "status":"ok",
        "liquidation_capture":"in-memory only while a client is connected",
        "independent_connection_monitoring":False,
        "captured_events":len(context["liquidations"]),
    }
    context["scheduled_jobs"] = []
    context["scheduler_backend_configured"] = False
    context["recent_failures"] = []
    context["notification_events"] = []
    context["model_versions"] = [
        {"name":name,"version":"research-per-request","artifact_persisted":False}
        for name in ("logistic_regression","random_forest","mlp","lstm_reservoir","transformer_reservoir","xgboost_style_booster")
    ]
    context["audit_events"] = [
        {"event_id":f"paper-trade-{x.get('id')}"} for x in paper_positions if x.get("id") is not None
    ]
    context["resource_snapshot"] = _runtime_memory_snapshot()
    context["heartbeats"] = {"api":{"age_seconds":0,"scope":"current_request_only"}}
    context["heartbeat_scope"] = "current API request only; no independent worker heartbeat backend is configured"
    context["security_policy"] = {
        "trading_mode":"simulation",
        "live_trading_enabled":False,
        "exchange_trade_credentials_present":any(os.getenv(k) for k in (
            "BYBIT_API_KEY","BYBIT_API_SECRET","BINANCE_API_KEY","BINANCE_API_SECRET",
            "BYBIT_TRADE_API_KEY","BYBIT_TRADE_API_SECRET","BINANCE_TRADE_API_KEY","BINANCE_TRADE_API_SECRET",
        )),
        "https_enabled":str(os.getenv("RENDER_EXTERNAL_URL","")).startswith("https://"),
        "secrets_redacted":True,
        "admin_auth_enabled":False,
    }
    context["system_health"] = {
        "api": "ok", "candles": "ok", "orderbook": "ok" if auxiliary["orderbook"] else "degraded",
        "trade_flow": "ok" if auxiliary["trade_flow"] else "degraded",
        "timeframes": "ok" if len(frames) >= 2 else "degraded",
        "paper_ledger": "ok",
        "database":"ok" if context["database"]["persistent"] else "degraded",
        "cache":"ok",
        "websocket":"ok",
    }
    early = early_opportunity_assessment(context)
    if early.get("status")=="computed" and early.get("score",0)>=65:
        context["notification_events"] = [{
            "type":"OPPORTUNITY",
            "title":f"{symbol} opportunity watch",
            "message":f"Research score {early['score']}/100; tier {early.get('tier')}. Confirmation and risk checks remain required.",
            "dedupe_key":f"{symbol}:{interval}:{early.get('tier')}",
        }]
    selected = [x.strip().upper() for x in engine_ids.split(",") if x.strip()] if engine_ids else None
    suite = run_engine_suite(context, selected)
    return {
        "symbol": symbol, "category": category, "interval": interval,
        "provider": provider, "completed_candles": len(completed),
        "auxiliary_data": auxiliary, "market_regime": regime,
        "market_structure": structure, "early_opportunity": early,
        "engine_suite": suite, "engine_coverage": catalogue_runtime_coverage(),
        "provider_health": provider_health,
        "trading_mode": "simulation", "live_trading_enabled": False,
    }




async def get_twelve_data_klines(symbol: str, interval: str, limit: int = 300) -> tuple[list[list],dict]:
    """Fetch OHLCV from Twelve Data using a server-side environment key only."""
    api_key = os.getenv("TWELVE_DATA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Twelve Data provider is not configured; add TWELVE_DATA_API_KEY in the Render environment")
    if interval not in TWELVE_DATA_INTERVALS:
        raise HTTPException(status_code=400, detail="Unsupported Twelve Data interval")
    clean_symbol = str(symbol).strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9./:_-]{1,31}",clean_symbol):
        raise HTTPException(status_code=400, detail="Invalid market symbol")
    try:
        response = await shared_http_client().get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol":clean_symbol,
                "interval":TWELVE_DATA_INTERVALS[interval],
                "outputsize":max(60,min(int(limit),500)),
                "format":"JSON",
            },
            headers={"Authorization":f"apikey {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504,detail="Twelve Data timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502,detail=f"Twelve Data returned HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError,ValueError) as exc:
        raise HTTPException(status_code=502,detail="Twelve Data connection or response error") from exc
    if not isinstance(payload,dict) or payload.get("status")=="error":
        message=str(payload.get("message","invalid provider response")) if isinstance(payload,dict) else "invalid provider response"
        raise HTTPException(status_code=502,detail=f"Twelve Data error: {message[:160]}")
    values=payload.get("values")
    if not isinstance(values,list) or len(values)<60:
        raise HTTPException(status_code=502,detail="Twelve Data returned fewer than 60 candles")
    tz_name=(payload.get("meta") or {}).get("exchange_timezone") or (payload.get("meta") or {}).get("timezone") or "UTC"
    try:
        from zoneinfo import ZoneInfo
        market_tz=ZoneInfo(str(tz_name))
    except Exception:
        market_tz=timezone.utc
        tz_name="UTC (fallback)"
    rows=[]
    for item in values:
        if not isinstance(item,dict):
            continue
        raw_time=str(item.get("datetime",""))
        try:
            parsed=datetime.fromisoformat(raw_time)
            if parsed.tzinfo is None:
                parsed=parsed.replace(tzinfo=market_tz)
            stamp=int(parsed.timestamp()*1000)
            rows.append([
                str(stamp),str(item.get("open")),str(item.get("high")),
                str(item.get("low")),str(item.get("close")),str(item.get("volume") or 0),
            ])
        except (TypeError,ValueError,OverflowError):
            continue
    if len(rows)<60:
        raise HTTPException(status_code=502,detail="Twelve Data returned invalid candle timestamps")
    return rows,{"provider":"Twelve Data","timezone":str(tz_name),"market":(payload.get("meta") or {}).get("type"),
                 "exchange":(payload.get("meta") or {}).get("exchange")}


@app.get("/api/multi-market-engine-suite")
async def multi_market_engine_suite(
    market: str = Query(..., description="forex, stocks, indices or commodities"),
    symbol: str = Query(..., min_length=2, max_length=32),
    interval: str = "15m",
    limit: int = Query(300, ge=60, le=500),
    engine_ids: str | None = None,
):
    """Run the same read-only 156-engine analysis over Twelve Data market feeds."""
    market=market.lower().strip()
    if market not in TWELVE_DATA_MARKETS:
        raise HTTPException(status_code=400,detail="Market must be forex, stocks, indices or commodities")
    rows, provider_info=await get_twelve_data_klines(symbol,interval,limit)
    analysis=analyze_klines(rows,include_all_candles=True)
    completed=analysis["candles"][:-1]
    if len(completed)<60:
        raise HTTPException(status_code=502,detail="At least 60 completed candles are required")
    analysis["candles"]=completed
    closes=[x["close"] for x in completed]
    async with PAPER_LOCK:
        paper_equity=PAPER_BALANCE
        paper_positions=[dict(x) for x in PAPER_TRADES]
    closed_trades=[x for x in paper_positions if x.get("status")=="CLOSED"]
    regime=market_regime(completed)
    structure=market_structure(completed)
    entry_confirmation=evaluate_entry(analysis)
    analysis["candles"]=completed
    last_price=completed[-1]["close"]
    context={
        "symbol":symbol.upper(),"category":market,"market_type":market,"interval":interval,
        "candles":completed,"closes":closes,"analysis":analysis,"regime":regime,"structure":structure,
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "account":{"equity":paper_equity},"positions":paper_positions,"closed_trades":closed_trades,
        "current_prices":{symbol.upper():last_price},
        "timeframes":{},
        "entry_confirmation":entry_confirmation,
        "plan":{},"risk_pct":1.0,"risk_approval":{"approved":False,"failed_checks":["multi_market_plan_not_configured"]},
        "reward_risk_targets":[1.5,2.0,3.0],
        "system_health":{"api":"ok","candles":"ok","paper_ledger":"ok","orderbook":"degraded","trade_flow":"degraded"},
        "cache":{"status":"ok","backend":"process-local","persistent":False},
        "database":{"status":"ok" if getattr(PAPER_STORE,"durable_configured",False) else "degraded",
                    "backend":"sqlite","persistent":bool(getattr(PAPER_STORE,"durable_configured",False))},
        "security_policy":{
            "trading_mode":"simulation","live_trading_enabled":False,
            "exchange_trade_credentials_present":False,"https_enabled":str(os.getenv("RENDER_EXTERNAL_URL","")).startswith("https://"),
            "secrets_redacted":True,"admin_auth_enabled":False,
        },
    }
    early=early_opportunity_assessment(context)
    if early.get("status")=="computed" and early.get("score",0)>=65:
        context["notification_events"]=[{
            "type":"OPPORTUNITY","title":f"{symbol.upper()} {market} opportunity watch",
            "message":f"Research score {early['score']}/100; confirm manually. No order was sent.",
            "dedupe_key":f"{market}:{symbol.upper()}:{interval}:{early.get('tier')}",
        }]
    else:
        context["notification_events"]=[]
    selected=[x.strip().upper() for x in engine_ids.split(",") if x.strip()] if engine_ids else None
    suite=run_engine_suite(context,selected)
    return {
        "symbol":symbol.upper(),"market":market,"interval":interval,
        "provider":provider_info,"completed_candles":len(completed),
        "early_opportunity":early,"engine_suite":suite,
        "engine_coverage":catalogue_runtime_coverage(),
        "provider_health":{"twelve_data":{"status":"ok",**provider_info}},
        "trading_mode":"simulation","live_trading_enabled":False,
    }


@app.get("/api/derivatives/{symbol}")
async def derivatives(symbol: str):
    """Read-only public OI, funding and long/short context with provider failover."""
    snapshot = await get_derivatives_snapshot(symbol)
    return {
        "symbol": symbol.upper(), **snapshot,
        "trading_mode": "simulation", "live_trading_enabled": False,
    }


@app.websocket("/ws/derivatives/{symbol}/liquidations")
async def derivatives_liquidation_stream(websocket: WebSocket, symbol: str):
    """Proxy Bybit's public all-liquidation stream for one USDT linear symbol."""
    symbol = symbol.upper()
    if not symbol.endswith("USDT") or not symbol.replace("USDT", "").isalnum():
        await websocket.close(code=1008, reason="Only USDT linear symbols are supported")
        return
    await websocket.accept()
    try:
        async with websockets.connect(BYBIT_LINEAR_WS, ping_interval=20, ping_timeout=20, open_timeout=8) as upstream:
            await upstream.send(json.dumps({"op": "subscribe", "args": [f"allLiquidation.{symbol}"]}))
            await websocket.send_json({"type": "status", "status": "connected", "provider": "Bybit", "feed": "allLiquidation", "symbol": symbol, "trading_mode": "simulation", "live_trading_enabled": False})
            async for raw in upstream:
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if payload.get("topic") != f"allLiquidation.{symbol}":
                    continue
                events = normalize_liquidations(payload.get("data", []))
                if events:
                    async with LIQUIDATION_LOCK:
                        cache = LIQUIDATION_EVENTS.setdefault(symbol, [])
                        cache.extend(events)
                        LIQUIDATION_EVENTS[symbol] = cache[-200:]
                    await websocket.send_json({"type": "liquidations", "events": events, "trading_mode": "simulation", "live_trading_enabled": False})
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.warning("Bybit liquidation stream ended for %s: %s", symbol, exc)
        try:
            await websocket.send_json({"type": "status", "status": "disconnected", "provider": "Bybit", "reason": "upstream_unavailable", "live_trading_enabled": False})
            await websocket.close(code=1011)
        except Exception:
            pass


@app.get("/api/strategies")
async def strategies():
    return {"strategies": [{"id": "ema_crossover", "name": "EMA Crossover", "mode": "long_only",
                            "description": "Enter after a completed fast/slow EMA bullish crossover; exit on bearish crossover.",
                            "default_fast": 10, "default_slow": 30,
                            "fees_and_slippage": "Included in backtest parameters"}],
            "live_trading_enabled": False}

@app.get("/api/backtest/{symbol}")
async def backtest(symbol: str, category: str = "spot", interval: str = "1h",
                   limit: int = Query(500, ge=60, le=1000),
                   starting_balance: float = Query(10000, gt=0, le=100000000),
                   position_fraction: float = Query(0.2, gt=0, le=1),
                   fast_period: int = Query(10, ge=2, le=50),
                   slow_period: int = Query(30, ge=5, le=200),
                   fee_bps: float = Query(10, ge=0, le=100),
                   slippage_bps: float = Query(5, ge=0, le=100)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid backtest market or interval")
    if slow_period <= fast_period:
        raise HTTPException(status_code=400, detail="slow_period must be greater than fast_period")
    rows, provider = await get_market_klines(symbol, category, interval, limit)
    candles = analyze_klines(rows, include_all_candles=True)["candles"]
    try:
        result = ema_crossover_backtest(candles, starting_balance=starting_balance,
            position_fraction=position_fraction, fast_period=fast_period,
            slow_period=slow_period, fee_bps=fee_bps, slippage_bps=slippage_bps)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result.update({"symbol": symbol.upper(), "category": category, "interval": interval,
                   "provider": provider, "generatedAt": datetime.now(timezone.utc).isoformat(),
                   "trading_mode": "simulation", "live_trading_enabled": False})
    return result

class PositionSizeRequest(BaseModel):
    equity: float = Field(gt=0, le=1000000000)
    risk_pct: float = Field(gt=0, le=2.0)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)

@app.post("/api/risk/position-size")
async def position_size(request: PositionSizeRequest):
    distance = abs(request.entry - request.stop_loss)
    if distance <= 0:
        raise HTTPException(status_code=400, detail="Entry and stop loss must differ")
    risk_amount = request.equity * request.risk_pct / 100.0
    quantity = risk_amount / distance
    return {"riskAmount": round(risk_amount, 8), "quantity": round(quantity, 10),
            "notional": round(quantity * request.entry, 8), "riskPct": request.risk_pct,
            "live_trading_enabled": False}


async def get_orderbook(symbol: str, category: str):
    try:
        result = await bybit_get("/v5/market/orderbook", {
            "category": category, "symbol": symbol.upper(), "limit": 50
        })
        bids, asks = result.get("b", []), result.get("a", [])
        if bids and asks:
            return bids, asks, "Bybit"
        raise HTTPException(status_code=502, detail="Bybit orderbook is empty")
    except HTTPException as bybit_error:
        logger.warning("Bybit orderbook unavailable for %s: %s", symbol, bybit_error.detail)

    try:
        data = await okx_get("/api/v5/market/books", {
            "instId": okx_instrument(symbol, category), "sz": "50"
        })
        if data and data[0].get("bids") and data[0].get("asks"):
            return data[0]["bids"], data[0]["asks"], "OKX"
        raise HTTPException(status_code=502, detail="OKX orderbook is empty")
    except HTTPException as okx_error:
        logger.warning("OKX orderbook unavailable for %s: %s", symbol, okx_error.detail)

    path = "/fapi/v1/depth" if category == "linear" else "/api/v3/depth"
    data = await _binance_get(category, path, {"symbol": symbol.upper(), "limit": 50})
    if not isinstance(data, dict) or not data.get("bids") or not data.get("asks"):
        raise HTTPException(status_code=502, detail="Binance orderbook is empty or invalid")
    return data["bids"], data["asks"], "Binance"


@app.get("/api/liquidity/{symbol}")
async def liquidity(symbol: str, category: str = "spot"):
    if category not in ("spot", "linear"):
        raise HTTPException(status_code=400, detail="Invalid category")
    bids, asks, provider = await get_orderbook(symbol, category)
    if not bids or not asks:
        raise HTTPException(status_code=502, detail="Orderbook is empty")
    best_bid = safe_float(bids[0][0])
    best_ask = safe_float(asks[0][0])
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        raise HTTPException(status_code=502, detail="Orderbook prices are invalid")
    bid_depth = sum(safe_float(row[0]) * safe_float(row[1]) for row in bids[:20] if len(row) >= 2)
    ask_depth = sum(safe_float(row[0]) * safe_float(row[1]) for row in asks[:20] if len(row) >= 2)
    total_depth = bid_depth + ask_depth
    imbalance = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0.0
    return {"symbol": symbol.upper(), "category": category, "provider": provider,
            "bestBid": best_bid, "bestAsk": best_ask,
            "spreadPct": round((best_ask - best_bid) / ((best_ask + best_bid) / 2) * 100, 5),
            "bidDepthNotional20": round(bid_depth, 2), "askDepthNotional20": round(ask_depth, 2),
            "depthImbalance": round(imbalance, 4),
            "bias": "BUY_SIDE" if imbalance >= 0.15 else ("SELL_SIDE" if imbalance <= -0.15 else "BALANCED"),
            "interpretation": "Top-of-book depth snapshot only; it can change or be cancelled.",
            "live_trading_enabled": False}


async def get_recent_trades(symbol: str, category: str):
    try:
        result = await bybit_get("/v5/market/recent-trade", {
            "category": category, "symbol": symbol.upper(), "limit": 100
        })
        rows = result.get("list", [])
        normalized = [{
            "price": safe_float(x.get("price")), "size": safe_float(x.get("size")),
            "side": str(x.get("side", "")).upper(), "time": safe_float(x.get("time"))
        } for x in rows if isinstance(x, dict)]
        if normalized:
            return normalized, "Bybit"
        raise HTTPException(status_code=502, detail="Bybit recent trades are empty")
    except HTTPException as bybit_error:
        logger.warning("Bybit recent trades unavailable for %s: %s", symbol, bybit_error.detail)

    try:
        rows = await okx_get("/api/v5/market/trades", {
            "instId": okx_instrument(symbol, category), "limit": "100"
        })
        normalized = [{
            "price": safe_float(x.get("px")), "size": safe_float(x.get("sz")),
            "side": str(x.get("side", "")).upper(), "time": safe_float(x.get("ts"))
        } for x in rows if isinstance(x, dict)]
        if normalized:
            return normalized, "OKX"
        raise HTTPException(status_code=502, detail="OKX recent trades are empty")
    except HTTPException as okx_error:
        logger.warning("OKX recent trades unavailable for %s: %s", symbol, okx_error.detail)

    path = "/fapi/v1/trades" if category == "linear" else "/api/v3/trades"
    rows = await _binance_get(category, path, {"symbol": symbol.upper(), "limit": 100})
    if not isinstance(rows, list):
        raise HTTPException(status_code=502, detail="Binance recent-trades response is invalid")
    normalized = [{
        "price": safe_float(x.get("price")), "size": safe_float(x.get("qty")),
        "side": "SELL" if x.get("isBuyerMaker") is True else "BUY",
        "time": safe_float(x.get("time")),
    } for x in rows if isinstance(x, dict)]
    if not normalized:
        raise HTTPException(status_code=502, detail="No recent trades from configured market providers")
    return normalized, "Binance"


@app.get("/api/flow/{symbol}")
async def market_flow(symbol: str, category: str = "spot"):
    if category not in ("spot", "linear"):
        raise HTTPException(status_code=400, detail="Invalid category")
    rows, provider = await get_recent_trades(symbol, category)
    notionals = [x["price"] * x["size"] for x in rows if x["price"] > 0 and x["size"] > 0]
    if not notionals:
        raise HTTPException(status_code=502, detail="No valid recent trade data")
    ordered = sorted(notionals)
    median_notional = ordered[len(ordered) // 2]
    threshold = max(median_notional * 5, 25000.0)
    buys = sum(x["price"] * x["size"] for x in rows if x["side"] == "BUY")
    sells = sum(x["price"] * x["size"] for x in rows if x["side"] == "SELL")
    large = [{"price": x["price"], "size": x["size"], "side": x["side"],
              "notional": round(x["price"] * x["size"], 2), "time": x["time"]}
             for x in rows if x["price"] * x["size"] >= threshold]
    return {"symbol": symbol.upper(), "category": category, "provider": provider,
            "sampleTrades": len(rows), "buyNotional": round(buys, 2), "sellNotional": round(sells, 2),
            "buySellRatio": round(buys / sells, 4) if sells > 0 else None,
            "largeTradeThreshold": round(threshold, 2), "largeTradePrints": large[:20],
            "interpretation": "Large prints are size outliers in the fetched trade sample, not proof of whale identity or intent.",
            "live_trading_enabled": False}


class PaperTrade(BaseModel):
    symbol: str = Field(min_length=2, max_length=30, pattern="^[A-Za-z0-9]{2,30}$")
    side: str
    category: str = "spot"
    leverage: int = Field(default=1, ge=1, le=10)
    entry: float = Field(gt=0)
    quantity: float = Field(gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)

@app.get("/api/paper")
async def paper_account():
    async with PAPER_LOCK:
        open_trades = [t for t in PAPER_TRADES if t["status"] == "OPEN"]
        closed_trades = [t for t in PAPER_TRADES if t["status"] == "CLOSED"]
        realized = sum(safe_float(t.get("pnl")) for t in closed_trades)
        reserved = sum(safe_float(t.get("margin"), safe_float(t.get("entry")) * safe_float(t.get("quantity"))) for t in open_trades)
        return {"balance": PAPER_BALANCE, "availableBalance": PAPER_BALANCE, "equity": PAPER_BALANCE + reserved,
                "trades": PAPER_TRADES, "openCount": len(open_trades),
                "closedCount": len(closed_trades), "realizedPnl": round(realized, 8),
                "reservedCapital": round(reserved, 8), "feeRatePerSide": PAPER_FEE_RATE,
                "storage": {"backend": "sqlite", "durableConfigured": PAPER_STORE.durable_configured},
                "live_trading_enabled": False}

@app.get("/api/paper/summary")
async def paper_summary():
    async with PAPER_LOCK:
        open_trades = [dict(t) for t in PAPER_TRADES if t["status"] == "OPEN"]
        cash = PAPER_BALANCE
        closed_trades = [dict(t) for t in PAPER_TRADES if t["status"] == "CLOSED"]
    marks = {}
    providers = set()
    for category in ("spot", "linear"):
        symbols = {t["symbol"] for t in open_trades if t.get("category", "spot") == category}
        if not symbols:
            continue
        try:
            tickers, provider = await get_market_tickers(category)
            providers.add(provider)
            for ticker in tickers:
                symbol = str(ticker.get("symbol", "")).upper()
                price = safe_float(ticker.get("lastPrice"))
                if symbol in symbols and price > 0:
                    marks[(category, symbol)] = price
        except HTTPException as exc:
            logger.warning("Paper summary mark refresh failed for %s: %s", category, exc.detail)
    reserved = 0.0
    gross_unrealized = 0.0
    estimated_close_fees = 0.0
    positions = []
    for trade in open_trades:
        category = trade.get("category", "spot")
        mark = marks.get((category, trade["symbol"]), trade["entry"])
        quantity = safe_float(trade["quantity"])
        margin = safe_float(trade.get("margin"), trade["entry"] * quantity)
        gross = (mark - trade["entry"]) * quantity * (1 if trade["side"] == "LONG" else -1)
        close_fee = mark * quantity * PAPER_FEE_RATE
        net = gross - safe_float(trade.get("entryFee")) - close_fee
        reserved += margin
        gross_unrealized += gross
        estimated_close_fees += close_fee
        positions.append({"id": trade["id"], "symbol": trade["symbol"], "side": trade["side"],
                          "entry": trade["entry"], "markPrice": mark, "quantity": quantity,
                          "unrealizedPnlAfterFees": round(net, 8),
                          "leverage": trade.get("leverage", 1)})
    realized = sum(safe_float(t.get("pnl")) for t in closed_trades)
    return {"balance": round(cash, 8), "reservedMargin": round(reserved, 8),
            "equity": round(cash + reserved + gross_unrealized - estimated_close_fees, 8),
            "realizedPnl": round(realized, 8),
            "unrealizedPnlAfterFees": round(gross_unrealized - sum(safe_float(t.get("entryFee")) for t in open_trades) - estimated_close_fees, 8),
            "positions": positions, "providers": sorted(providers),
            "feeRatePerSide": PAPER_FEE_RATE, "live_trading_enabled": False}

@app.get("/api/paper/performance")
async def paper_performance():
    async with PAPER_LOCK:
        closed = [t for t in PAPER_TRADES if t["status"] == "CLOSED"]
        pnls = [safe_float(t.get("pnl")) for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_loss = abs(sum(losses))
        return {"closedTrades": len(closed), "winRatePct": round(len(wins) / len(closed) * 100, 2) if closed else 0,
                "netPnl": round(sum(pnls), 8), "profitFactor": round(sum(wins) / gross_loss, 4) if gross_loss else None,
                "averagePnl": round(sum(pnls) / len(pnls), 8) if pnls else 0,
                "live_trading_enabled": False}

@app.post("/api/paper")
async def open_paper_trade(trade: PaperTrade):
    global PAPER_BALANCE
    if trade.side.upper() not in ("LONG","SHORT"):
        raise HTTPException(status_code=400, detail="side must be LONG or SHORT")
    if trade.category not in ("spot", "linear"):
        raise HTTPException(status_code=400, detail="category must be spot or linear")
    if trade.category == "spot" and trade.side.upper() == "SHORT":
        raise HTTPException(status_code=400, detail="Spot short positions are not supported by this simulator")
    if trade.category == "spot" and trade.leverage != 1:
        raise HTTPException(status_code=400, detail="Spot simulation is limited to 1x")
    if trade.stop_loss is None:
        raise HTTPException(status_code=400, detail="A stop loss is required for every simulated trade")
    async with PAPER_LOCK:
        notional = trade.quantity * trade.entry
        margin = notional / trade.leverage
        entry_fee = notional * PAPER_FEE_RATE
        if margin + entry_fee > PAPER_BALANCE:
            raise HTTPException(status_code=400, detail="Insufficient simulated margin and entry fee")
        if trade.stop_loss is not None:
            invalid_stop = (trade.side.upper() == "LONG" and trade.stop_loss >= trade.entry) or (trade.side.upper() == "SHORT" and trade.stop_loss <= trade.entry)
            if invalid_stop:
                raise HTTPException(status_code=400, detail="Stop loss is on the wrong side of the entry")
            stop_exit_fee = trade.stop_loss * trade.quantity * PAPER_FEE_RATE
            risk_amount = abs(trade.entry - trade.stop_loss) * trade.quantity + entry_fee + stop_exit_fee
            if risk_amount > PAPER_BALANCE * 0.02:
                raise HTTPException(status_code=400, detail="Trade risk including estimated fees exceeds the 2% simulated-account limit")
        if trade.take_profit is not None:
            invalid_target = (trade.side.upper() == "LONG" and trade.take_profit <= trade.entry) or (trade.side.upper() == "SHORT" and trade.take_profit >= trade.entry)
            if invalid_target:
                raise HTTPException(status_code=400, detail="Take profit is on the wrong side of the entry")
        item = {"id":(max((t["id"] for t in PAPER_TRADES), default=0)+1),"symbol":trade.symbol.upper(),"side":trade.side.upper(),
                "category":trade.category, "leverage": trade.leverage, "notional": notional, "margin": margin,
                "entry":trade.entry,"quantity":trade.quantity,"stopLoss":trade.stop_loss,
                "takeProfit":trade.take_profit,"entryFee":round(entry_fee, 8),
                "feeRate":PAPER_FEE_RATE, "status":"OPEN","openedAt":datetime.now(timezone.utc).isoformat()}
        previous_balance = PAPER_BALANCE
        PAPER_TRADES.append(item)
        PAPER_BALANCE -= margin + entry_fee
        try:
            persist_paper_state()
        except Exception as exc:
            PAPER_TRADES.pop()
            PAPER_BALANCE = previous_balance
            logger.exception("Unable to save paper trade")
            raise HTTPException(status_code=503, detail="Could not persist simulated trade") from exc
    return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.post("/api/paper/{trade_id}/close")
async def close_paper_trade(trade_id: int, exit_price: float = Query(gt=0)):
    global PAPER_BALANCE
    async with PAPER_LOCK:
        item = next((t for t in PAPER_TRADES if t["id"]==trade_id and t["status"]=="OPEN"),None)
        if not item: raise HTTPException(status_code=404,detail="Open paper trade not found")
        gross_pnl = (exit_price-item["entry"])*item["quantity"]*(1 if item["side"]=="LONG" else -1)
        exit_fee = exit_price * item["quantity"] * PAPER_FEE_RATE
        pnl = gross_pnl - safe_float(item.get("entryFee")) - exit_fee
        margin = safe_float(item.get("margin"), item["quantity"] * item["entry"])
        previous_balance = PAPER_BALANCE
        previous_item = dict(item)
        PAPER_BALANCE += margin + gross_pnl - exit_fee
        item.update({"status":"CLOSED","exitPrice":exit_price,"grossPnl":round(gross_pnl,8),
                     "exitFee":round(exit_fee,8),"pnl":round(pnl,8),
                     "closedAt":datetime.now(timezone.utc).isoformat()})
        try:
            persist_paper_state()
        except Exception as exc:
            PAPER_BALANCE = previous_balance
            item.clear()
            item.update(previous_item)
            logger.exception("Unable to persist paper close")
            raise HTTPException(status_code=503, detail="Could not persist simulated trade close") from exc
        return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.post("/api/paper/monitor")
async def monitor_paper_trades():
    """Mark open simulations against current exchange tickers and close hit SL/TP."""
    global PAPER_BALANCE
    async with PAPER_LOCK:
        open_trades = [t for t in PAPER_TRADES if t["status"] == "OPEN"]
    if not open_trades:
        return {"checked": 0, "closed": [], "live_trading_enabled": False}
    categories = {t.get("category", "spot") for t in open_trades}
    prices: dict[tuple[str, str], float] = {}
    for category in categories:
        try:
            tickers, _provider = await get_market_tickers(category)
            for ticker in tickers:
                symbol = str(ticker.get("symbol", "")).upper()
                mark = safe_float(ticker.get("lastPrice"))
                if symbol and mark > 0:
                    prices[(category, symbol)] = mark
        except HTTPException as exc:
            logger.warning("Paper monitor cannot fetch %s marks: %s", category, exc.detail)
    closed = []
    async with PAPER_LOCK:
        previous_balance = PAPER_BALANCE
        previous_trades = [dict(t) for t in PAPER_TRADES]
        for item in PAPER_TRADES:
            if item["status"] != "OPEN":
                continue
            category = item.get("category", "spot")
            mark = prices.get((category, item["symbol"]))
            if not mark:
                continue
            stop = item.get("stopLoss")
            target = item.get("takeProfit")
            side = item["side"]
            stop_hit = stop is not None and ((side == "LONG" and mark <= stop) or (side == "SHORT" and mark >= stop))
            target_hit = target is not None and ((side == "LONG" and mark >= target) or (side == "SHORT" and mark <= target))
            if not (stop_hit or target_hit):
                continue
            gross_pnl = (mark - item["entry"]) * item["quantity"] * (1 if side == "LONG" else -1)
            exit_fee = mark * item["quantity"] * PAPER_FEE_RATE
            pnl = gross_pnl - safe_float(item.get("entryFee")) - exit_fee
            margin = safe_float(item.get("margin"), item["quantity"] * item["entry"])
            PAPER_BALANCE += margin + gross_pnl - exit_fee
            item.update({"status": "CLOSED", "exitPrice": mark, "grossPnl": round(gross_pnl, 8),
                         "exitFee": round(exit_fee, 8), "pnl": round(pnl, 8),
                         "closeReason": "STOP_LOSS" if stop_hit else "TAKE_PROFIT",
                         "closedAt": datetime.now(timezone.utc).isoformat()})
            closed.append({"id": item["id"], "symbol": item["symbol"],
                           "reason": item["closeReason"], "exitPrice": mark, "pnl": item["pnl"]})
        if closed:
            try:
                persist_paper_state()
            except Exception as exc:
                PAPER_BALANCE = previous_balance
                PAPER_TRADES[:] = previous_trades
                logger.exception("Unable to persist paper monitor batch")
                raise HTTPException(status_code=503, detail="Could not persist monitored paper trade exits") from exc
    return {"checked": len(open_trades), "closed": closed,
            "live_trading_enabled": False}


@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")
