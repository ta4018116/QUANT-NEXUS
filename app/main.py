import asyncio
import math
import os
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .paper_store import PaperStore
from .quant_engine import ema_crossover_backtest, enrich_analysis
from .engine_registry import engine_registry
from .command_engine import COMMANDS, matches_command, evaluate_entry
from .derivatives_engine import summarize_derivatives
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
TIMEOUT = httpx.Timeout(12.0, connect=5.0)
PAPER_STORE = PaperStore()
PAPER_BALANCE, PAPER_TRADES = PAPER_STORE.load()
PAPER_LOCK = asyncio.Lock()
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

async def bybit_get(path: str, params: dict):
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent":"QUANT-NEXUS/1.0"}) as client:
            response = await client.get(BYBIT + path, params=params)
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
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent":"QUANT-NEXUS/1.0"}) as client:
            response = await client.get("https://www.okx.com" + path, params=params)
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

async def get_market_tickers(category: str):
    try:
        result = await bybit_get("/v5/market/tickers", {"category":category})
        items = result.get("list", [])
        if not isinstance(items, list):
            raise HTTPException(status_code=502, detail="Bybit ticker list is invalid")
        return items, "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit ticker request failed (%s); falling back to OKX", bybit_error.detail)
        inst_type = "SWAP" if category == "linear" else "SPOT"
        items = await okx_get("/api/v5/market/tickers", {"instType":inst_type})
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
            change = ((last/open24)-1)*100 if open24 > 0 else 0
            quote_volume = safe_float(x.get("volCcy24h")) * last
            normalized.append({"symbol":symbol,"lastPrice":last,"price24hPcnt":change/100,
                "highPrice24h":safe_float(x.get("high24h")),"lowPrice24h":safe_float(x.get("low24h")),
                "turnover24h":quote_volume,"volume24h":safe_float(x.get("vol24h"))})
        return normalized, "OKX"

async def get_market_klines(symbol: str, category: str, interval: str, limit: int):
    try:
        result = await bybit_get("/v5/market/kline", {"category":category,"symbol":symbol.upper(),
            "interval":INTERVALS[interval],"limit":max(60,min(limit,1000))})
        rows = result.get("list", [])
        if not isinstance(rows, list) or len(rows) < 20:
            raise HTTPException(status_code=502, detail="Bybit returned insufficient candles")
        return rows, "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit candles failed for %s (%s); falling back to OKX", symbol, bybit_error.detail)
        bars = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m",
                "1h":"1H","2h":"2H","4h":"4H","1d":"1D","1w":"1W"}
        rows = await okx_get("/api/v5/market/candles", {
            "instId":okx_instrument(symbol, category),"bar":bars[interval],
            "limit":str(max(60,min(limit,300)))})
        if len(rows) < 20:
            raise HTTPException(status_code=502, detail="OKX returned insufficient candles")
        return [[row[0],row[1],row[2],row[3],row[4],row[5]] for row in rows], "OKX"

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

@app.get("/api/derivatives/{symbol}")
async def derivatives(symbol: str):
    """Read-only Bybit linear open-interest and funding context."""
    symbol = symbol.upper()
    if not symbol.endswith("USDT") or not symbol.replace("USDT", "").isalnum():
        raise HTTPException(status_code=400, detail="Only USDT linear symbols are supported")
    oi_result, funding_result = await asyncio.gather(
        bybit_get("/v5/market/open-interest", {
            "category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": 50
        }),
        bybit_get("/v5/market/funding/history", {
            "category": "linear", "symbol": symbol, "limit": 20
        })
    )
    summary = summarize_derivatives(
        oi_result.get("list", []), funding_result.get("list", [])
    )
    return {"symbol": symbol, "provider": "Bybit", **summary,
            "trading_mode": "simulation", "live_trading_enabled": False}


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
        result = await bybit_get("/v5/market/orderbook", {"category": category, "symbol": symbol.upper(), "limit": 50})
        return result.get("b", []), result.get("a", []), "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit orderbook unavailable for %s: %s", symbol, bybit_error.detail)
        data = await okx_get("/api/v5/market/books", {"instId": okx_instrument(symbol, category), "sz": "50"})
        if not data:
            raise HTTPException(status_code=502, detail="No orderbook data from configured providers")
        return data[0].get("bids", []), data[0].get("asks", []), "OKX"


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
        result = await bybit_get("/v5/market/recent-trade", {"category": category, "symbol": symbol.upper(), "limit": 100})
        rows = result.get("list", [])
        normalized = [{"price": safe_float(x.get("price")), "size": safe_float(x.get("size")),
                       "side": str(x.get("side", "")).upper(), "time": safe_float(x.get("time"))}
                      for x in rows if isinstance(x, dict)]
        return normalized, "Bybit"
    except HTTPException as bybit_error:
        logger.warning("Bybit recent trades unavailable for %s: %s", symbol, bybit_error.detail)
        rows = await okx_get("/api/v5/market/trades", {"instId": okx_instrument(symbol, category), "limit": "100"})
        normalized = [{"price": safe_float(x.get("px")), "size": safe_float(x.get("sz")),
                       "side": str(x.get("side", "")).upper(), "time": safe_float(x.get("ts"))}
                      for x in rows if isinstance(x, dict)]
        return normalized, "OKX"


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
