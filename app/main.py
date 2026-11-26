import asyncio
import math
import os
import logging
import json
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
PAPER_STATE_PATH = Path(os.getenv("QUANT_NEXUS_STATE_PATH", str(BASE / ".data" / "paper_state.json")))
PAPER_FEE_RATE = min(0.01, max(0.0, safe_float(os.getenv("PAPER_FEE_RATE"), 0.0006)))
PAPER_PERSISTENCE_CONFIGURED = os.getenv("QUANT_NEXUS_PERSISTENT_STORAGE", "false").lower() == "true"

def save_paper_state():
    """Persist the simulated ledger atomically; configure STATE_PATH on durable storage in production."""
    try:
        PAPER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 1, "balance": PAPER_BALANCE, "trades": PAPER_TRADES}
        temp_path = PAPER_STATE_PATH.with_name(PAPER_STATE_PATH.name + ".tmp")
        temp_path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        os.replace(temp_path, PAPER_STATE_PATH)
        return True
    except (OSError, TypeError, ValueError):
        logger.exception("Could not persist paper-trading ledger")
        return False

def load_paper_state():
    global PAPER_BALANCE
    try:
        if not PAPER_STATE_PATH.exists():
            return
        payload = json.loads(PAPER_STATE_PATH.read_text(encoding="utf-8"))
        if payload.get("schema") != 1 or not isinstance(payload.get("trades"), list):
            raise ValueError("Unsupported paper ledger schema")
        balance = safe_float(payload.get("balance"), 10000.0)
        if balance < 0:
            raise ValueError("Invalid paper balance")
        PAPER_BALANCE = balance
        PAPER_TRADES.clear()
        PAPER_TRADES.extend(t for t in payload["trades"] if isinstance(t, dict))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        logger.exception("Could not load paper-trading ledger; starting with a clean simulated account")
        PAPER_TRADES.clear()
        PAPER_BALANCE = 10000.0

def reset_paper_state(balance=10000.0):
    global PAPER_BALANCE
    PAPER_TRADES.clear()
    PAPER_BALANCE = float(balance)
    save_paper_state()

load_paper_state()
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
        return 100.0
    return 100 - 100 / (1 + gains / losses)

def macd(values, fast=12, slow=26, signal=9):
    if len(values) < slow + signal: return None, None, None
    line=[]
    for i in range(len(values)):
        a,b=ema(values[:i+1],fast),ema(values[:i+1],slow)
        if a is not None and b is not None: line.append(a-b)
    sig=ema(line,signal) if len(line)>=signal else None
    return (line[-1],sig,line[-1]-sig) if sig is not None else (None,None,None)

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
    range_pct = (recent_high - recent_low) / last if last > 0 else 0
    momentum5 = ((last / closes[-6]) - 1) * 100 if len(closes) >= 6 and closes[-6] else 0
    pre_move_score = 0
    pre_move_reasons = []
    if vol_ratio is not None and vol_ratio >= 1.3:
        pre_move_score += 30
        pre_move_reasons.append("ارتفاع الحجم مقارنة بمتوسطه")
    if range_pct <= 0.025:
        pre_move_score += 20
        pre_move_reasons.append("تضيق النطاق السعري")
    if abs(momentum5) >= 0.2:
        pre_move_score += 20
        pre_move_reasons.append("تغير الزخم قصير الأجل")
    if recent_high > recent_low and min(abs(last / recent_high - 1), abs(last / recent_low - 1)) <= 0.007:
        pre_move_score += 30
        pre_move_reasons.append("اقتراب السعر من حافة النطاق")
    risk_pct = risk / last if last > 0 else 1
    risk_level = "HIGH" if risk_pct >= 0.03 else ("MEDIUM" if risk_pct >= 0.015 else "LOW")
    if direction == "LONG":
        stop, target1, target2 = last-risk, last+risk*1.5, last+risk*2.5
    elif direction == "SHORT":
        stop, target1, target2 = last+risk, last-risk*1.5, last-risk*2.5
    else:
        stop = target1 = target2 = None
    return {"price":last,"change24h":None,"rsi":round(strength,2) if strength is not None else None,
            "ema20":e20,"ema50":e50,"macd":macd_line,"macdSignal":macd_signal,"macdHistogram":macd_hist,"vwap":vwap,"volumeRatio":round(vol_ratio,2) if vol_ratio is not None else None,
            "support":recent_low,"resistance":recent_high,"score":score,"direction":direction,
            "entry":last if direction != "NEUTRAL" else None,"stopLoss":stop,
            "target1":target1,"target2":target2,"candles":candles[-100:],
            "preMoveScore":pre_move_score,"preMoveLabel":"WATCH" if pre_move_score >= 60 else "LOW",
            "preMoveReasons":pre_move_reasons,"riskLevel":risk_level,"riskPercent":round(risk_pct*100,3)}

@app.get("/health")
async def health():
    return {"application":"QUANT NEXUS","status":"ok","version":"1.0.0",
            "trading_mode":"simulation","live_trading_enabled":False,
            "paper_storage":"json_file",
            "paper_persistence_configured":PAPER_PERSISTENCE_CONFIGURED,
            "paper_fee_rate":PAPER_FEE_RATE,
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
               min_turnover: float = Query(0, ge=0), direction: str = "all", depth: str = Query("AUTO", pattern="^(AUTO|32|64|128|256)$")):
    if category not in ("spot","linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid scan configuration")
    if direction.lower() not in ("all", "long", "short", "neutral"):
        raise HTTPException(status_code=400, detail="Invalid scan direction")
    tickers, ticker_provider = await get_market_tickers(category)
    tickers = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    tickers.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    eligible = [x for x in tickers if safe_float(x.get("turnover24h")) >= min_turnover]
    depth_limit = {"32":32,"64":64,"128":128,"256":256}.get(depth, min(256,max(64,len(eligible))))
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
    results = [x for x in results if x and (direction == "all" or x["direction"].lower() == direction.lower())]
    results.sort(key=lambda x:safe_float(x.get("score")), reverse=True)
    providers = sorted(set(x["provider"] for x in results))
    return {"provider":ticker_provider if len(providers)<=1 and not providers else (providers[0] if len(providers)==1 else "Mixed"),
            "providers":providers,"category":category,"interval":interval,"depth":depth,"effectiveDepth":len(candidates),"scanned":len(candidates),
            "returned":len(results),"generatedAt":datetime.now(timezone.utc).isoformat(),"items":results}

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
    return {"symbol": symbol.upper(), "frames": items, "averageScore": average,
            "aligned": bool(directions) and len(directions) == 1,
            "validFrames": len(valid), "live_trading_enabled": False}

@app.get("/api/engine/status")
async def engine_status():
    return {"engine": "QUANT INTELLIGENCE",
            "indicators": ["EMA20", "EMA50", "RSI14", "MACD12-26-9", "VWAP", "VolumeRatio"],
            "scan_depths": [32, 64, 128, 256, "AUTO"],
            "markets": {"spot": True, "linear_futures": True, "forex": False,
                        "us_stocks": False, "indices": False, "commodities": False},
            "features": ["multi_timeframe", "pre_move_watchlist", "ema_cross_backtest", "paper_ledger"],
            "paper_storage": "json_file",
            "paper_persistence_configured": PAPER_PERSISTENCE_CONFIGURED,
            "paper_fee_rate": PAPER_FEE_RATE,
            "trading_mode": "simulation", "live_trading_enabled": False}

@app.get("/api/strategy/backtest")
async def strategy_backtest(symbol: str = "BTCUSDT", category: str = "spot",
                            interval: str = "1h", strategy: str = "ema_cross",
                            limit: int = Query(300, ge=80, le=500)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid backtest market configuration")
    if strategy not in ("ema_cross", "breakout_20"):
        raise HTTPException(status_code=400, detail="Unsupported strategy")
    rows, provider = await get_market_klines(symbol, category, interval, limit)
    analysis = analyze_klines(rows)
    candles = analysis["candles"]
    closes = [c["close"] for c in candles]
    trades = []
    position = None
    equity = 10000.0
    peak = equity
    max_drawdown = 0.0
    slippage = 0.0005
    fee_rate = PAPER_FEE_RATE

    for i in range(50, len(candles)):
        price = closes[i]
        should_enter = False
        should_exit = False
        if strategy == "ema_cross":
            fast_now, slow_now = ema(closes[:i+1], 20), ema(closes[:i+1], 50)
            fast_prev, slow_prev = ema(closes[:i], 20), ema(closes[:i], 50)
            should_enter = position is None and fast_now is not None and slow_now is not None and fast_prev is not None and slow_prev is not None and fast_now > slow_now and fast_prev <= slow_prev
            should_exit = position is not None and fast_now is not None and slow_now is not None and fast_now < slow_now
        else:
            prior_high = max(c["high"] for c in candles[max(0, i-20):i])
            fast_now = ema(closes[:i+1], 20)
            should_enter = position is None and price > prior_high
            should_exit = position is not None and fast_now is not None and price < fast_now

        if should_enter:
            entry_price = price * (1 + slippage)
            position = {"entry": entry_price, "time": candles[i]["time"]}
        elif should_exit and position is not None:
            exit_price = price * (1 - slippage)
            gross = exit_price - position["entry"]
            fees = (position["entry"] + exit_price) * fee_rate
            net = gross - fees
            equity += net
            trades.append({"entryTime": position["time"], "exitTime": candles[i]["time"],
                           "entry": round(position["entry"], 8), "exit": round(exit_price, 8),
                           "pnl": round(net, 8), "result": "WIN" if net > 0 else "LOSS"})
            position = None
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0)

    if position is not None:
        exit_price = closes[-1] * (1 - slippage)
        net = (exit_price - position["entry"]) - (position["entry"] + exit_price) * fee_rate
        equity += net
        trades.append({"entryTime": position["time"], "exitTime": candles[-1]["time"],
                       "entry": round(position["entry"], 8), "exit": round(exit_price, 8),
                       "pnl": round(net, 8), "result": "WIN" if net > 0 else "LOSS",
                       "closedAtEnd": True})
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0)

    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [-t["pnl"] for t in trades if t["pnl"] < 0]
    gross_profit, gross_loss = sum(wins), sum(losses)
    return {"symbol": symbol.upper(), "category": category, "interval": interval,
            "strategy": strategy, "provider": provider, "initialEquity": 10000.0,
            "finalEquity": round(equity, 4), "netPnl": round(equity - 10000.0, 4),
            "trades": len(trades), "winRate": round(len(wins) / len(trades) * 100, 2) if trades else 0,
            "profitFactor": round(gross_profit / gross_loss, 3) if gross_loss else (None if not gross_profit else "infinity"),
            "maxDrawdownPct": round(max_drawdown * 100, 3),
            "feeRatePerSide": fee_rate, "slippagePerSide": slippage,
            "tradeLog": trades[-50:], "live_trading_enabled": False}

class PaperTrade(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    side: str
    entry: float = Field(gt=0)
    quantity: float = Field(gt=0)
    category: str = "spot"
    leverage: int = Field(default=1, ge=1, le=10)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)

@app.get("/api/paper")
async def paper_account():
    async with PAPER_LOCK:
        open_trades = [t for t in PAPER_TRADES if t["status"] == "OPEN"]
        return {"balance": round(PAPER_BALANCE, 8), "trades": PAPER_TRADES,
                "openCount": len(open_trades), "feeRate": PAPER_FEE_RATE,
                "live_trading_enabled": False}

@app.get("/api/paper/summary")
async def paper_summary():
    async with PAPER_LOCK:
        open_trades = [dict(t) for t in PAPER_TRADES if t["status"] == "OPEN"]
        all_trades = [dict(t) for t in PAPER_TRADES]
        cash = PAPER_BALANCE
    current_prices = {}
    providers = set()
    for category in ("spot", "linear"):
        symbols = {t["symbol"] for t in open_trades if t.get("category", "spot") == category}
        if not symbols:
            continue
        try:
            tickers, provider = await get_market_tickers(category)
            providers.add(provider)
            for item in tickers:
                symbol = str(item.get("symbol", "")).upper()
                if symbol in symbols:
                    current_prices[symbol] = safe_float(item.get("lastPrice"))
        except Exception as exc:
            logger.warning("Paper summary price refresh failed for %s: %s", category, exc)
    unrealized = 0.0
    reserved = 0.0
    positions = []
    for trade in open_trades:
        current = current_prices.get(trade["symbol"]) or trade["entry"]
        quantity = trade["quantity"]
        side_factor = 1 if trade["side"] == "LONG" else -1
        gross = (current - trade["entry"]) * quantity * side_factor
        estimated_exit_fee = current * quantity * PAPER_FEE_RATE
        net = gross - safe_float(trade.get("entryFee")) - estimated_exit_fee
        margin = safe_float(trade.get("margin"), trade["entry"] * quantity)
        reserved += margin
        unrealized += net
        positions.append({"id": trade["id"], "symbol": trade["symbol"], "side": trade["side"],
                          "entry": trade["entry"], "currentPrice": current,
                          "quantity": quantity, "unrealizedPnl": round(net, 8),
                          "leverage": trade.get("leverage", 1)})
    realized = sum(safe_float(t.get("pnl")) for t in all_trades if t["status"] == "CLOSED")
    return {"balance": round(cash, 8), "reservedMargin": round(reserved, 8),
            "equity": round(cash + reserved + unrealized, 8),
            "realizedPnl": round(realized, 8), "unrealizedPnl": round(unrealized, 8),
            "openCount": len(open_trades), "positions": positions,
            "providers": sorted(providers), "feeRate": PAPER_FEE_RATE,
            "live_trading_enabled": False}

@app.post("/api/paper")
async def open_paper_trade(trade: PaperTrade):
    global PAPER_BALANCE
    side = trade.side.upper()
    category = trade.category.lower()
    if side not in ("LONG", "SHORT"):
        raise HTTPException(status_code=400, detail="side must be LONG or SHORT")
    if category not in ("spot", "linear"):
        raise HTTPException(status_code=400, detail="category must be spot or linear")
    if not 1 <= trade.leverage <= 10:
        raise HTTPException(status_code=400, detail="leverage must be between 1x and 10x")
    if category == "spot" and (side == "SHORT" or trade.leverage != 1):
        raise HTTPException(status_code=400, detail="Spot simulation supports LONG only at 1x")
    if trade.stop_loss is not None:
        if (side == "LONG" and trade.stop_loss >= trade.entry) or (side == "SHORT" and trade.stop_loss <= trade.entry):
            raise HTTPException(status_code=400, detail="Stop loss is on the wrong side of entry")
    if trade.take_profit is not None:
        if (side == "LONG" and trade.take_profit <= trade.entry) or (side == "SHORT" and trade.take_profit >= trade.entry):
            raise HTTPException(status_code=400, detail="Take profit is on the wrong side of entry")
    notional = trade.quantity * trade.entry
    margin = notional / trade.leverage
    entry_fee = notional * PAPER_FEE_RATE
    required = margin + entry_fee
    async with PAPER_LOCK:
        if required > PAPER_BALANCE:
            raise HTTPException(status_code=400, detail="Insufficient simulated balance for margin and fees")
        item = {"id": max((t["id"] for t in PAPER_TRADES), default=0) + 1,
                "symbol": trade.symbol.upper(), "category": category, "side": side,
                "entry": trade.entry, "quantity": trade.quantity,
                "leverage": trade.leverage, "margin": round(margin, 8),
                "entryFee": round(entry_fee, 8), "stopLoss": trade.stop_loss,
                "takeProfit": trade.take_profit, "status": "OPEN",
                "openedAt": datetime.now(timezone.utc).isoformat()}
        PAPER_TRADES.append(item)
        PAPER_BALANCE -= required
        if not save_paper_state():
            PAPER_TRADES.pop()
            PAPER_BALANCE += required
            raise HTTPException(status_code=500, detail="Could not save simulated trade")
    return {"trade": item, "balance": round(PAPER_BALANCE, 8),
            "live_trading_enabled": False}

@app.post("/api/paper/{trade_id}/close")
async def close_paper_trade(trade_id: int, exit_price: float = Query(gt=0)):
    global PAPER_BALANCE
    async with PAPER_LOCK:
        item = next((t for t in PAPER_TRADES if t["id"] == trade_id and t["status"] == "OPEN"), None)
        if not item:
            raise HTTPException(status_code=404, detail="Open paper trade not found")
        side_factor = 1 if item["side"] == "LONG" else -1
        notional_exit = item["quantity"] * exit_price
        gross_pnl = (exit_price - item["entry"]) * item["quantity"] * side_factor
        exit_fee = notional_exit * PAPER_FEE_RATE
        net_pnl = gross_pnl - safe_float(item.get("entryFee")) - exit_fee
        margin = safe_float(item.get("margin"), item["entry"] * item["quantity"])
        previous_balance = PAPER_BALANCE
        previous_item = dict(item)
        PAPER_BALANCE += margin + gross_pnl - exit_fee
        item.update({"status": "CLOSED", "exitPrice": exit_price,
                     "grossPnl": round(gross_pnl, 8), "exitFee": round(exit_fee, 8),
                     "pnl": round(net_pnl, 8),
                     "closedAt": datetime.now(timezone.utc).isoformat()})
        if not save_paper_state():
            PAPER_BALANCE = previous_balance
            item.clear()
            item.update(previous_item)
            raise HTTPException(status_code=500, detail="Could not save simulated trade close")
        return {"trade": item, "balance": round(PAPER_BALANCE, 8),
                "live_trading_enabled": False}

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")
