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
PAPER_TRADES = []
PAPER_BALANCE = 10000.0
PAPER_LOCK = asyncio.Lock()
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
        raise HTTPException(status_code=504, detail="Market provider timed out; retry shortly") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Market provider returned HTTP {exc.response.status_code}") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Market provider connection or response error") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Market provider returned an invalid response")
    if payload.get("retCode") != 0:
        raise HTTPException(status_code=502, detail=f"Market provider: {payload.get('retMsg','unknown error')}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Market provider returned an invalid result payload")
    return result

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
        return 100.0
    return 100 - 100 / (1 + gains / losses)

def analyze_klines(rows):
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
    recent_high, recent_low = max(highs[-20:]), min(lows[-20:])
    score = 50
    if e20 is not None and last > e20: score += 12
    elif e20 is not None: score -= 12
    if e50 is not None and e20 is not None and e20 > e50: score += 13
    elif e50 is not None and e20 is not None: score -= 13
    if strength is not None:
        score += 8 if 52 <= strength <= 68 else (-8 if strength < 42 or strength > 75 else 0)
    if vol_ratio is not None and vol_ratio >= 1.5: score += 10
    score = max(0, min(100, score))
    direction = "LONG" if score >= 62 else ("SHORT" if score <= 38 else "NEUTRAL")
    risk = max((recent_high - recent_low) * 0.35, last * 0.006)
    if direction == "LONG":
        stop, target1, target2 = last-risk, last+risk*1.5, last+risk*2.5
    elif direction == "SHORT":
        stop, target1, target2 = last+risk, last-risk*1.5, last-risk*2.5
    else:
        stop = target1 = target2 = None
    return {"price":last,"change24h":None,"rsi":round(strength,2) if strength is not None else None,
            "ema20":e20,"ema50":e50,"volumeRatio":round(vol_ratio,2) if vol_ratio is not None else None,
            "support":recent_low,"resistance":recent_high,"score":score,"direction":direction,
            "entry":last if direction != "NEUTRAL" else None,"stopLoss":stop,
            "target1":target1,"target2":target2,"candles":candles[-100:]}

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
    data = await bybit_get("/v5/market/tickers", {"category":category})
    items = data.get("list", [])
    if not isinstance(items, list):
        raise HTTPException(status_code=502, detail="Market provider returned an invalid ticker list")
    items = [x for x in items if isinstance(x, dict)]
    items.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    return {"provider":"Bybit public market data","category":category,"count":len(items),
            "items":[{"symbol":x.get("symbol"),"lastPrice":safe_float(x.get("lastPrice")),
            "change24h":safe_float(x.get("price24hPcnt"))*100,
            "high24h":safe_float(x.get("highPrice24h")),"low24h":safe_float(x.get("lowPrice24h")),
            "turnover24h":safe_float(x.get("turnover24h")),"volume24h":safe_float(x.get("volume24h"))}
            for x in items[:limit]]}

@app.get("/api/klines/{symbol}")
async def klines(symbol: str, category: str = "spot", interval: str = "15m", limit: int = 200):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid category or interval")
    result = await bybit_get("/v5/market/kline", {"category":category,"symbol":symbol.upper(),
                         "interval":INTERVALS[interval],"limit":max(60,min(limit,1000))})
    rows = result.get("list", [])
    if len(rows) < 20:
        raise HTTPException(status_code=404, detail="Not enough candle data for analysis")
    analysis = analyze_klines(rows)
    analysis["symbol"] = symbol.upper()
    analysis["category"] = category
    analysis["interval"] = interval
    analysis["provider"] = "Bybit"
    return analysis

@app.get("/api/scan")
async def scan(category: str = "spot", interval: str = "15m", limit: int = Query(30, ge=1, le=256),
               min_turnover: float = Query(0, ge=0), direction: str = "all"):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid scan configuration")
    tickers = (await bybit_get("/v5/market/tickers", {"category":category})).get("list", [])
    if not isinstance(tickers, list):
        raise HTTPException(status_code=502, detail="Market provider returned an invalid ticker list")
    tickers = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    tickers.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    candidates = [x for x in tickers if safe_float(x.get("turnover24h")) >= min_turnover][:limit]
    semaphore = asyncio.Semaphore(8)
    async def one(ticker):
        async with semaphore:
            try:
                symbol = str(ticker.get("symbol", "")).upper()
                result = await bybit_get("/v5/market/kline", {"category":category,
                    "symbol":symbol,"interval":INTERVALS[interval],"limit":100})
                rows = result.get("list", [])
                if not isinstance(rows, list) or len(rows) < 60:
                    return None
                a = analyze_klines(rows)
                a.update({"symbol":symbol,"change24h":safe_float(ticker.get("price24hPcnt"))*100,
                          "turnover24h":safe_float(ticker.get("turnover24h")),
                          "volume24h":safe_float(ticker.get("volume24h")),
                          "high24h":safe_float(ticker.get("highPrice24h")),
                          "low24h":safe_float(ticker.get("lowPrice24h"))})
                return a
            except HTTPException:
                return None
            except (TypeError, ValueError, KeyError, IndexError, OverflowError):
                logger.exception("Skipping malformed ticker %s", ticker.get("symbol"))
                return None
            except Exception:
                logger.exception("Skipping failed market analysis for %s", ticker.get("symbol"))
                return None
    results = await asyncio.gather(*(one(t) for t in candidates))
    results = [x for x in results if x and (direction == "all" or x["direction"].lower() == direction.lower())]
    results.sort(key=lambda x:safe_float(x.get("score")), reverse=True)
    return {"provider":"Bybit","category":category,"interval":interval,"scanned":len(candidates),
            "returned":len(results),"generatedAt":datetime.now(timezone.utc).isoformat(),"items":results}

class PaperTrade(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    side: str
    entry: float = Field(gt=0)
    quantity: float = Field(gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)

@app.get("/api/paper")
async def paper_account():
    async with PAPER_LOCK:
        return {"balance":PAPER_BALANCE,"trades":PAPER_TRADES,
                "openCount":sum(1 for t in PAPER_TRADES if t["status"]=="OPEN"),
                "live_trading_enabled":False}

@app.post("/api/paper")
async def open_paper_trade(trade: PaperTrade):
    global PAPER_BALANCE
    if trade.side.upper() not in ("LONG","SHORT"):
        raise HTTPException(status_code=400, detail="side must be LONG or SHORT")
    async with PAPER_LOCK:
        if trade.quantity * trade.entry > PAPER_BALANCE:
            raise HTTPException(status_code=400, detail="Insufficient simulated balance")
        item = {"id":(max((t["id"] for t in PAPER_TRADES), default=0)+1),"symbol":trade.symbol.upper(),"side":trade.side.upper(),
                "entry":trade.entry,"quantity":trade.quantity,"stopLoss":trade.stop_loss,
                "takeProfit":trade.take_profit,"status":"OPEN","openedAt":datetime.now(timezone.utc).isoformat()}
        PAPER_TRADES.append(item)
        PAPER_BALANCE -= trade.quantity * trade.entry
    return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.post("/api/paper/{trade_id}/close")
async def close_paper_trade(trade_id: int, exit_price: float = Query(gt=0)):
    global PAPER_BALANCE
    async with PAPER_LOCK:
        item = next((t for t in PAPER_TRADES if t["id"]==trade_id and t["status"]=="OPEN"),None)
        if not item: raise HTTPException(status_code=404,detail="Open paper trade not found")
        pnl = (exit_price-item["entry"])*item["quantity"]*(1 if item["side"]=="LONG" else -1)
        PAPER_BALANCE += item["quantity"]*exit_price
        item.update({"status":"CLOSED","exitPrice":exit_price,"pnl":round(pnl,8),
                     "closedAt":datetime.now(timezone.utc).isoformat()})
        return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")
