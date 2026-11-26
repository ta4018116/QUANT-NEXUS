import asyncio
import math
import os
import logging
import json
import sqlite3
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
PAPER_LOCK = asyncio.Lock()
LIVE_TRADING_ENABLED = False
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_MODE = "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"
DB_PATH = Path(os.getenv("QUANT_NEXUS_DB_PATH", str(BASE.parent / "data" / "quant_nexus.sqlite3")))

def _load_paper_state():
    if DB_MODE == "postgres":
        try:
            import psycopg
            from psycopg.types.json import Json
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed") from exc
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        with psycopg.connect(url, connect_timeout=8) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS quant_paper_state (
                id SMALLINT PRIMARY KEY CHECK (id = 1),
                balance DOUBLE PRECISION NOT NULL,
                trades JSONB NOT NULL
            )""")
            row = conn.execute("SELECT balance, trades FROM quant_paper_state WHERE id=1").fetchone()
            if row is None:
                conn.execute("INSERT INTO quant_paper_state(id,balance,trades) VALUES(1,%s,%s)",
                             (10000.0, Json([])))
                return 10000.0, []
            trades = row[1] if isinstance(row[1], list) else json.loads(row[1])
            return float(row[0]), trades
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=8) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS quant_paper_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL NOT NULL,
            trades TEXT NOT NULL
        )""")
        row = conn.execute("SELECT balance,trades FROM quant_paper_state WHERE id=1").fetchone()
        if row is None:
            conn.execute("INSERT INTO quant_paper_state(id,balance,trades) VALUES(1,?,?)",
                         (10000.0, "[]"))
            return 10000.0, []
        return float(row[0]), json.loads(row[1])

def _save_paper_state(balance, trades):
    if DB_MODE == "postgres":
        import psycopg
        from psycopg.types.json import Json
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        with psycopg.connect(url, connect_timeout=8) as conn:
            conn.execute("""INSERT INTO quant_paper_state(id,balance,trades) VALUES(1,%s,%s)
                ON CONFLICT(id) DO UPDATE SET balance=EXCLUDED.balance,trades=EXCLUDED.trades""",
                (float(balance), Json(trades)))
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=8) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""INSERT INTO quant_paper_state(id,balance,trades) VALUES(1,?,?)
            ON CONFLICT(id) DO UPDATE SET balance=excluded.balance,trades=excluded.trades""",
            (float(balance), json.dumps(trades, ensure_ascii=False)))

PAPER_BALANCE, PAPER_TRADES = _load_paper_state()
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
    reference_highs = highs[-21:-1] or highs[:-1]
    reference_lows = lows[-21:-1] or lows[:-1]
    recent_high, recent_low = max(reference_highs), min(reference_lows)
    breakout = "UP" if last > recent_high else ("DOWN" if last < recent_low else "NONE")
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
    return {"price":last,"change24h":None,"rsi":round(strength,2) if strength is not None else None,
            "ema20":e20,"ema50":e50,"macd":macd_line,"macdSignal":macd_signal,"macdHistogram":macd_hist,"vwap":vwap,"volumeRatio":round(vol_ratio,2) if vol_ratio is not None else None,
            "support":recent_low,"resistance":recent_high,"breakout":breakout,"score":score,"direction":direction,
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
    tickers, ticker_provider = await get_market_tickers(category)
    tickers = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    tickers.sort(key=lambda x: safe_float(x.get("turnover24h")), reverse=True)
    eligible = [x for x in tickers if safe_float(x.get("turnover24h")) >= min_turnover]
    depth_limit = {"32":32,"64":64,"128":256}.get(depth)
    if depth == "256":
        depth_limit = 256
    elif depth == "AUTO":
        depth_limit = min(256, max(64, len(eligible)))
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
            "aligned": len(directions) <= 1, "live_trading_enabled": False}


class CommandRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=30)
    category: str = Field(default="spot")
    interval: str = Field(default="15m")
    command: str = Field(min_length=2, max_length=120)

@app.post("/api/commands/execute")
async def execute_command(request: CommandRequest):
    if request.category not in ("spot", "linear") or request.interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid market or interval")
    symbol = request.symbol.upper().replace("/", "")
    if not symbol.endswith("USDT"):
        raise HTTPException(status_code=400, detail="Only USDT pairs are currently supported")
    command = request.command.strip().lower()
    if "أفضل 3" in command:
        result = await scan(category=request.category, interval=request.interval,
                            limit=64, min_turnover=1_000_000, direction="all", depth="AUTO")
        return {"command": request.command, "kind": "top_opportunities",
                "summary": "أفضل الفرص حسب التقييم الكمي الحالي",
                "items": result["items"][:3], "scanned": result["scanned"],
                "live_trading_enabled": False}
    if "spot و futures" in command or "مقارنة spot" in command:
        async def one(cat):
            rows, provider = await get_market_klines(symbol, cat, request.interval, 120)
            a = analyze_klines(rows)
            return {"category": cat, "direction": a["direction"], "score": a["score"],
                    "price": a["price"], "provider": provider}
        spot, futures = await asyncio.gather(one("spot"), one("linear"), return_exceptions=True)
        items = [x for x in (spot, futures) if not isinstance(x, Exception)]
        return {"command": request.command, "kind": "market_comparison", "items": items,
                "summary": "مقارنة التحليل الفعلي بين السوق الفوري والعقود",
                "live_trading_enabled": False}
    if "متعدد الأطر" in command or "الأطر الزمنية" in command:
        result = await multi_timeframe(symbol=symbol, category=request.category)
        return {"command": request.command, "kind": "multi_timeframe",
                "summary": "تحليل متزامن لأطر 5m و15m و1h و4h",
                "data": result, "live_trading_enabled": False}
    rows, provider = await get_market_klines(symbol, request.category, request.interval, 200)
    a = analyze_klines(rows)
    candles = a["candles"]
    closes = [x["close"] for x in candles]
    summary = ""
    kind = "analysis"
    data = {"price": a["price"], "score": a["score"], "direction": a["direction"]}
    if "الاتجاه" in command:
        kind = "trend"
        aligned = a["ema20"] is not None and a["ema50"] is not None and a["ema20"] > a["ema50"]
        summary = ("الاتجاه يميل للصعود" if aligned else "الاتجاه يميل للهبوط" if a["ema20"] and a["ema50"] and a["ema20"] < a["ema50"] else "الاتجاه غير محسوم")
        data.update({"ema20": a["ema20"], "ema50": a["ema50"], "rsi": a["rsi"]})
    elif "الدعم" in command or "المقاومة" in command:
        kind = "levels"
        summary = "مستويات الدعم والمقاومة محسوبة من آخر 20 شمعة مكتملة قبل الشمعة الحالية"
        data.update({"support": a["support"], "resistance": a["resistance"],
                     "distanceToSupportPct": round((a["price"]/a["support"]-1)*100, 3) if a["support"] else None,
                     "distanceToResistancePct": round((a["resistance"]/a["price"]-1)*100, 3) if a["price"] else None})
    elif "السيولة" in command:
        kind = "liquidity_proxy"
        ratio = a.get("volumeRatio")
        summary = "نشاط الحجم مرتفع" if ratio is not None and ratio >= 1.5 else "لا يوجد ارتفاع حجم مؤكد"
        summary += ". هذا تقدير من أحجام الشموع وليس قراءة دفتر الأوامر أو تدفق الحيتان."
        data.update({"volumeRatio": ratio, "vwap": a["vwap"],
                     "limitation": "volume-based proxy; order-book and whale-flow data are not connected"})
    elif "اختراق" in command:
        kind = "breakout"
        summary = {"UP": "اختراق صاعد فوق أعلى مستوى للشموع المرجعية",
                   "DOWN": "كسر هابط أسفل أدنى مستوى للشموع المرجعية",
                   "NONE": "لا يوجد اختراق مؤكد حالياً"}[a["breakout"]]
        data.update({"breakout": a["breakout"], "referenceHigh": a["resistance"],
                     "referenceLow": a["support"]})
    elif "النماذج" in command:
        kind = "candle_pattern"
        last = candles[-1]
        prev = candles[-2]
        bullish_engulf = prev["close"] < prev["open"] and last["close"] > last["open"] and last["close"] >= prev["open"] and last["open"] <= prev["close"]
        bearish_engulf = prev["close"] > prev["open"] and last["close"] < last["open"] and last["open"] >= prev["close"] and last["close"] <= prev["open"]
        body = abs(last["close"]-last["open"])
        span = max(last["high"]-last["low"], 1e-12)
        pattern = "ابتلاع شرائي" if bullish_engulf else ("ابتلاع بيعي" if bearish_engulf else ("شمعة صغيرة/تردد" if body/span < 0.12 else "لا يوجد نموذج بسيط مؤكد"))
        summary = pattern
        data.update({"pattern": pattern, "bodyToRange": round(body/span, 3)})
    elif "تباعد" in command:
        kind = "momentum_divergence"
        prev_rsi = rsi(closes[-29:-14]) if len(closes) >= 29 else None
        curr_rsi = rsi(closes[-15:]) if len(closes) >= 15 else None
        price_up = closes[-1] > closes[-15] if len(closes) >= 15 else False
        price_down = closes[-1] < closes[-15] if len(closes) >= 15 else False
        bullish = price_down and prev_rsi is not None and curr_rsi is not None and curr_rsi > prev_rsi + 3
        bearish = price_up and prev_rsi is not None and curr_rsi is not None and curr_rsi < prev_rsi - 3
        summary = "احتمال تباعد إيجابي يحتاج تأكيداً" if bullish else ("احتمال تباعد سلبي يحتاج تأكيداً" if bearish else "لا يظهر تباعد مبسط واضح")
        data.update({"previousRsi": prev_rsi, "currentRsi": curr_rsi,
                     "bullishDivergence": bullish, "bearishDivergence": bearish})
    elif "الحجم" in command:
        kind = "volume"
        summary = "حجم غير معتاد" if a.get("volumeRatio") is not None and a["volumeRatio"] >= 2 else "الحجم ضمن النطاق المعتاد نسبياً"
        data.update({"volumeRatio": a["volumeRatio"], "vwap": a["vwap"]})
    else:
        kind = "risk_plan"
        summary = "خطة مستويات افتراضية مبنية على تذبذب النطاق؛ ليست أمراً تنفيذياً"
        data.update({"entry": a["entry"], "stopLoss": a["stopLoss"],
                     "target1": a["target1"], "target2": a["target2"],
                     "riskReward1": 1.5 if a["entry"] is not None else None,
                     "riskReward2": 2.5 if a["entry"] is not None else None})
    return {"command": request.command, "kind": kind, "symbol": symbol,
            "interval": request.interval, "provider": provider,
            "summary": summary, "data": data, "live_trading_enabled": False}

def calculate_backtest(candles, fee_bps=10, initial_balance=10000.0):
    closes = [x["close"] for x in candles]
    trades = []
    balance = initial_balance
    peak = initial_balance
    max_drawdown = 0.0
    position = None
    fee_pct = fee_bps / 100.0
    for i in range(50, len(candles)):
        history = closes[:i]
        fast, slow = ema(history, 20), ema(history, 50)
        previous_close = closes[i-1]
        enter_signal = fast is not None and slow is not None and previous_close > fast > slow
        exit_signal = fast is not None and slow is not None and (previous_close < fast or fast < slow)
        fill = candles[i]["open"]
        if position and exit_signal:
            gross_pct = ((fill / position["entry"]) - 1) * 100
            net_pct = gross_pct - 2 * fee_pct
            pnl = balance * net_pct / 100
            balance += pnl
            trades.append({"entry": position["entry"], "exit": fill,
                           "returnPct": round(net_pct, 4), "pnl": round(pnl, 4)})
            position = None
        elif not position and enter_signal:
            position = {"entry": fill}
        peak = max(peak, balance)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak-balance)/peak*100)
    if position:
        fill = candles[-1]["close"]
        gross_pct = ((fill / position["entry"]) - 1) * 100
        net_pct = gross_pct - 2 * fee_pct
        pnl = balance * net_pct / 100
        balance += pnl
        trades.append({"entry": position["entry"], "exit": fill,
                       "returnPct": round(net_pct, 4), "pnl": round(pnl, 4)})
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] < 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {"strategy": "EMA20/EMA50 trend-following (long-only)",
            "initialBalance": initial_balance, "finalBalance": round(balance, 4),
            "netPnl": round(balance-initial_balance, 4),
            "winRate": round(len(wins)/len(trades)*100, 2) if trades else 0,
            "profitFactor": round(gross_win/gross_loss, 3) if gross_loss else (None if not wins else "infinite"),
            "expectancy": round(sum(t["pnl"] for t in trades)/len(trades), 4) if trades else 0,
            "maxDrawdownPct": round(max_drawdown, 3), "tradeCount": len(trades),
            "trades": trades, "feesBpsPerSide": fee_bps}

@app.get("/api/backtest/{symbol}")
async def backtest(symbol: str, category: str = "spot", interval: str = "1h",
                   limit: int = Query(500, ge=100, le=1000),
                   fee_bps: float = Query(10, ge=0, le=100)):
    if category not in ("spot", "linear") or interval not in INTERVALS:
        raise HTTPException(status_code=400, detail="Invalid backtest configuration")
    rows, provider = await get_market_klines(symbol.upper(), category, interval, limit)
    candles = []
    for row in rows:
        try:
            vals = [float(row[i]) for i in range(1, 6)]
            if not all(math.isfinite(v) for v in vals) or min(vals[:4]) <= 0:
                continue
            candles.append({"time": int(float(row[0]))//1000, "open": vals[0],
                            "high": vals[1], "low": vals[2], "close": vals[3],
                            "volume": vals[4]})
        except (TypeError, ValueError, IndexError, OverflowError):
            continue
    candles.sort(key=lambda x: x["time"])
    if len(candles) < 60:
        raise HTTPException(status_code=502, detail="Not enough valid candles for backtest")
    result = calculate_backtest(candles, fee_bps=fee_bps)
    result.update({"symbol": symbol.upper(), "category": category,
                   "interval": interval, "candles": len(candles),
                   "provider": provider, "live_trading_enabled": False})
    return result

@app.get("/api/engine/status")
async def engine_status():
    return {"engine": "QUANT INTELLIGENCE",
            "indicators": ["EMA20", "EMA50", "RSI14", "MACD12-26-9", "VWAP", "VolumeRatio"],
            "scan_depths": [32, 64, 128, 256, "AUTO"],
            "markets": {"spot": True, "linear_futures": True, "forex": False,
                        "us_stocks": False, "indices": False, "commodities": False},
            "storage": {"mode": DB_MODE, "durable_across_redeploys": DB_MODE == "postgres"},
            "features": ["multi_timeframe", "command_engine", "ema_backtest", "paper_portfolio"],
            "trading_mode": "simulation", "live_trading_enabled": False}

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
                "closedCount":sum(1 for t in PAPER_TRADES if t["status"]=="CLOSED"),
                "realizedPnl":round(sum(t.get("pnl", 0) for t in PAPER_TRADES if t["status"]=="CLOSED"), 8),
                "storageMode":DB_MODE, "live_trading_enabled":False}

@app.post("/api/paper")
async def open_paper_trade(trade: PaperTrade):
    global PAPER_BALANCE
    side = trade.side.upper()
    if side not in ("LONG","SHORT"):
        raise HTTPException(status_code=400, detail="side must be LONG or SHORT")
    if side == "LONG" and ((trade.stop_loss is not None and trade.stop_loss >= trade.entry) or
                           (trade.take_profit is not None and trade.take_profit <= trade.entry)):
        raise HTTPException(status_code=400, detail="LONG stop-loss must be below entry and take-profit above entry")
    if side == "SHORT" and ((trade.stop_loss is not None and trade.stop_loss <= trade.entry) or
                            (trade.take_profit is not None and trade.take_profit >= trade.entry)):
        raise HTTPException(status_code=400, detail="SHORT stop-loss must be above entry and take-profit below entry")
    async with PAPER_LOCK:
        reserved = trade.quantity * trade.entry
        if reserved > PAPER_BALANCE:
            raise HTTPException(status_code=400, detail="Insufficient simulated balance")
        old_balance = PAPER_BALANCE
        item = {"id":(max((t["id"] for t in PAPER_TRADES), default=0)+1),"symbol":trade.symbol.upper(),"side":side,
                "entry":trade.entry,"quantity":trade.quantity,"reservedNotional":reserved,
                "stopLoss":trade.stop_loss,"takeProfit":trade.take_profit,
                "status":"OPEN","openedAt":datetime.now(timezone.utc).isoformat()}
        PAPER_TRADES.append(item)
        PAPER_BALANCE -= reserved
        try:
            _save_paper_state(PAPER_BALANCE, PAPER_TRADES)
        except Exception as exc:
            PAPER_TRADES.pop()
            PAPER_BALANCE = old_balance
            logger.exception("Could not persist paper trade")
            raise HTTPException(status_code=503, detail="Paper portfolio storage is unavailable") from exc
    return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.post("/api/paper/{trade_id}/close")
async def close_paper_trade(trade_id: int, exit_price: float = Query(gt=0)):
    global PAPER_BALANCE
    async with PAPER_LOCK:
        item = next((t for t in PAPER_TRADES if t["id"]==trade_id and t["status"]=="OPEN"),None)
        if not item: raise HTTPException(status_code=404,detail="Open paper trade not found")
        old_balance = PAPER_BALANCE
        old_item = dict(item)
        pnl = (exit_price-item["entry"])*item["quantity"]*(1 if item["side"]=="LONG" else -1)
        # Return reserved capital plus directional PnL; this treats LONG and SHORT symmetrically.
        PAPER_BALANCE += item.get("reservedNotional", item["entry"]*item["quantity"]) + pnl
        item.update({"status":"CLOSED","exitPrice":exit_price,"pnl":round(pnl,8),
                     "closedAt":datetime.now(timezone.utc).isoformat()})
        try:
            _save_paper_state(PAPER_BALANCE, PAPER_TRADES)
        except Exception as exc:
            PAPER_BALANCE = old_balance
            item.clear()
            item.update(old_item)
            logger.exception("Could not persist closed paper trade")
            raise HTTPException(status_code=503, detail="Paper portfolio storage is unavailable") from exc
        return {"trade":item,"balance":PAPER_BALANCE,"live_trading_enabled":False}

@app.get("/", response_class=HTMLResponse)
async def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")
