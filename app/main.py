from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
app = FastAPI(title="QUANT NEXUS", version="0.1.0",
              description="Multi-market intelligence — simulation only")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

@app.get("/health")
def health():
    return {"application": "QUANT NEXUS", "status": "ok",
            "trading_mode": "simulation", "live_trading_enabled": False,
            "utc": datetime.now(timezone.utc).isoformat()}

@app.get("/api/overview")
def overview():
    return {
        "markets": ["Crypto", "Forex", "US Stocks", "Indices", "Commodities"],
        "products": ["Spot", "Futures"],
        "mode": "PAPER TRADING",
        "live_trading_enabled": False,
        "watchlist": [],
        "notice": "Demo foundation. Connect market data providers before relying on signals."
    }

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")
