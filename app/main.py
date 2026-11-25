import asyncio
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
app = FastAPI(title="QUANT NEXUS", version="1.0.0",
              description="Multi-market intelligence and paper trading only")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

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
    return payload.get("result", {})

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
    candles = list(reversed(rows))
    closes = [float(x[4]) for x in candles]
    highs = [float(x[2]) for x in candles]
    lows = [float(x[3]) for x in candles]
    volumes = [float(x[5]) for x in candles]
    last = closes[-1]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    strength = rsi(closes)
    avg_vol = sum(volumes[-21:-1]) / max(1, len(volumes[-21:-1]))
    vol_ratio = volumes[-1] / avg_vol if avg_vol else None
    recent_high, recent_low = max(highs[-20:]), min(lows[-20:])
    score = 50
    if e20 and last > e20: score += 12
    elif e20: score -= 12
    if e50 and e20 and e20 > e50: score += 13
    elif e50 and e20: score -= 13
    if strength is not None:
        score += 8 if 52 <= strength <= 68 else (-8 if strength < 42 or strength > 75 else 0)
    if vol_ratio and vol_ratio >= 1.5: score += 10
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
            "ema20":e20,"ema50":e50,"volumeRatio":round(vol_ratio,2) if vol_ratio else None,
            "support":recent_low,"resistance":recent_high,"score":score,"direction":direction,
            "entry":last if direction != "NEUTRAL" else None,"stopLoss":stop,
            "target1":target1,"target2":target2,"candles":[
                {"time":int(x[0])//1000,"open":float(x[1]),"high":float(x[2]),
                 "low":float(x[3]),"close":float(x[4]),"volume":float(x[5])} for x in candles[-100:]]}

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
    items.sort(key=lambda x: float(x.get("turnover24h") or 0), reverse=True)
    return {"provider":"Bybit public market data","category":category,"count":len(items),
            "items":[{"symbol":x.get("symbol"),"lastPrice":float(x.get("lastPrice") or 0),
            "change24h":float(x.get("price24hPcnt") or 0)*100,
            "high24h":float(x.get("highPrice24h") or 0),"low24h":float(x.get("lowPrice24h") or 0),
            "turnover24h":float(x.get("turnover24h") or 0),"volume24h":float(x.get("volume24h") or 0)}
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
               min_turnover: float = 0, direction: str = "all"):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid scan configuration")
    try:
        tickers = (await bybit_get("/v5/market/tickers", {"category":category})).get("list", [])
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Unable to retrieve market tickers") from exc
    tickers.sort(key=lambda x: float(x.get("turnover24h") or 0), reverse=True)
    candidates = [x for x in tickers if x.get("symbol","").endswith("USDT")
                  and float(x.get("turnover24h") or 0) >= min_turnover][:min(max(limit,1),256)]
    semaphore = asyncio.Semaphore(10)
    async def one(ticker):
        async with semaphore:
            try:
                result = await bybit_get("/v5/market/kline", {"category":category,
                    "symbol":ticker["symbol"],"interval":INTERVALS[interval],"limit":100})
                rows = result.get("list", [])
                if len(rows) < 60: return None
                a = analyze_klines(rows)
                a.update({"symbol":ticker["symbol"],"change24h":float(ticker.get("price24hPcnt") or 0)*100,
                          "turnover24h":float(ticker.get("turnover24h") or 0)})
                return a
            except Exception:
                return None
    results = await asyncio.gather(*(one(t) for t in candidates))
    results = [x for x in results if x and (direction == "all" or x["direction"].lower() == direction.lower())]
    results.sort(key=lambda x:x["score"], reverse=True)
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
    if trade.quantity * trade.entry > PAPER_BALANCE:
        raise HTTPException(status_code=400, detail="Insufficient simulated balance")
    item = {"id":len(PAPER_TRADES)+1,"symbol":trade.symbol.upper(),"side":trade.side.upper(),
            "entry":trade.entry,"quantity":trade.quantity,"stopLoss":trade.stop_loss,
            "takeProfit":trade.take_profit,"status":"OPEN","openedAt":datetime.now(timezone.utc).isoformat()}
    async with PAPER_LOCK:
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
