"""Transparent registry for the QUANT NEXUS analytical engine modules."""
from __future__ import annotations

ENGINES = [
 {"id":"data","name":"DATA ENGINE","name_ar":"محرك البيانات","status":"implemented","capabilities":["Bybit market data","OKX fallback","candle validation"],"gaps":["provider freshness telemetry","additional verified markets"]},
 {"id":"market_regime","name":"MARKET REGIME","name_ar":"محرك حالة السوق","status":"partial","capabilities":["directional classification from technical score"],"gaps":["explicit trend/range/volatility regime classifier"]},
 {"id":"technical","name":"TECHNICAL ENGINE","name_ar":"محرك التحليل الفني","status":"implemented","capabilities":["EMA","RSI","MACD","VWAP","ATR","support/resistance"]},
 {"id":"multi_timeframe","name":"MULTI-TIMEFRAME","name_ar":"محرك الأطر الزمنية","status":"implemented","capabilities":["5m","15m","1h","4h consensus"]},
 {"id":"liquidity","name":"LIQUIDITY ENGINE","name_ar":"محرك السيولة","status":"implemented","capabilities":["order book spread","bid/ask depth","depth imbalance"],"gaps":["historical liquidity persistence","spoofing detection is not claimed"]},
 {"id":"order_flow","name":"ORDER FLOW","name_ar":"محرك تدفق الأوامر","status":"implemented","capabilities":["recent trade buy/sell notional","large-print outliers"],"gaps":["full footprint/delta history"]},
 {"id":"derivatives","name":"DERIVATIVES ENGINE","name_ar":"محرك المشتقات","status":"planned","capabilities":[],"gaps":["open interest","funding rate","liquidation feed"]},
 {"id":"market_structure","name":"MARKET STRUCTURE","name_ar":"محرك بنية السوق","status":"partial","capabilities":["completed-candle breakout","support/resistance"],"gaps":["validated BOS/CHoCH and supply/demand zones"]},
 {"id":"volatility","name":"VOLATILITY ENGINE","name_ar":"محرك التقلبات","status":"implemented","capabilities":["ATR14","ATR percentage"]},
 {"id":"opportunity","name":"OPPORTUNITY ENGINE","name_ar":"محرك اكتشاف الفرص","status":"partial","capabilities":["scanner ranking","explainable score","pre-move watch flag"],"gaps":["calibrated out-of-sample probability and unified multi-engine confirmation"]},
 {"id":"risk","name":"RISK ENGINE","name_ar":"محرك إدارة المخاطر","status":"implemented","capabilities":["position sizing","2% per-trade risk guard","stop-loss validation"]},
 {"id":"portfolio","name":"PORTFOLIO ENGINE","name_ar":"محرك المحفظة","status":"implemented","capabilities":["SQLite paper ledger","equity and PnL summary","trade performance"]},
 {"id":"backtest","name":"BACKTEST ENGINE","name_ar":"محرك الاختبار التاريخي","status":"implemented","capabilities":["next-bar fills","fees","slippage","drawdown"]},
 {"id":"paper_execution","name":"PAPER EXECUTION","name_ar":"محرك التنفيذ التجريبي","status":"implemented","capabilities":["simulated entries/exits","stop/target monitoring","no exchange orders"]},
 {"id":"learning_monitoring","name":"LEARNING & MONITORING","name_ar":"محرك التعلم والمراقبة","status":"partial","capabilities":["paper performance metrics","request error logging"],"gaps":["walk-forward model recalibration","drift alerts","automated strategy promotion"]},
]

def engine_registry() -> dict:
    engines = [dict(item, capabilities=list(item.get("capabilities", [])),
                    gaps=list(item.get("gaps", []))) for item in ENGINES]
    counts = {status: sum(1 for item in engines if item["status"] == status)
              for status in ("implemented", "partial", "planned")}
    return {"name":"QUANT NEXUS X","coordinator":"QUANT BRAIN",
            "total":len(engines),"counts":counts,"engines":engines,
            "trading_mode":"simulation","live_trading_enabled":False,
            "disclaimer":"Statuses reflect implemented application paths; planned modules do not produce live signals."}
