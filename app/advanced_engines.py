"""Deterministic, explainable market intelligence engines.

All functions consume validated completed candles and make no predictive
probability claims. Monitoring metrics are derived from the paper ledger only.
"""
from __future__ import annotations
from statistics import mean, pstdev
from typing import Any


def market_regime(candles: list[dict[str, Any]]) -> dict[str, Any]:
    if len(candles) < 60:
        return {"status":"insufficient_data","required_bars":60,"samples":len(candles)}
    closes=[float(c["close"]) for c in candles]
    highs=[float(c["high"]) for c in candles]
    lows=[float(c["low"]) for c in candles]
    returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes)) if closes[i-1]>0]
    fast=mean(closes[-20:]); slow=mean(closes[-50:])
    slope=(closes[-1]/closes[-20]-1)*100 if closes[-20] else 0.0
    vol=pstdev(returns[-20:])*100 if len(returns)>=20 else 0.0
    width=(max(highs[-20:])-min(lows[-20:]))/closes[-1]*100 if closes[-1] else 0.0
    if fast>slow*1.003 and slope>0.5: trend="UPTREND"
    elif fast<slow*0.997 and slope < -0.5: trend="DOWNTREND"
    else: trend="RANGE"
    volatility="HIGH" if vol>=1.5 else ("LOW" if vol<=0.25 else "NORMAL")
    regime="VOLATILE_"+trend if volatility=="HIGH" else trend
    return {"status":"ok","regime":regime,"trend":trend,"volatility":volatility,
            "return_volatility_pct":round(vol,5),"range_20_pct":round(width,5),
            "ema_proxy_fast":round(fast,10),"ema_proxy_slow":round(slow,10),
            "slope_20_pct":round(slope,5),"samples":len(candles),
            "method":"20/50 close means, 20-bar return dispersion; heuristic classification, not forecast"}


def market_structure(candles: list[dict[str, Any]], pivot: int=3) -> dict[str, Any]:
    if len(candles)<2*pivot+10:
        return {"status":"insufficient_data","required_bars":2*pivot+10,"samples":len(candles)}
    highs=[float(c["high"]) for c in candles]; lows=[float(c["low"]) for c in candles]
    swing_highs=[]; swing_lows=[]
    for i in range(pivot,len(candles)-pivot):
        if highs[i]>=max(highs[i-pivot:i+pivot+1]) and highs[i]>max(highs[i-pivot:i]+highs[i+1:i+pivot+1]):
            swing_highs.append({"index":i,"price":highs[i]})
        if lows[i]<=min(lows[i-pivot:i+pivot+1]) and lows[i]<min(lows[i-pivot:i]+lows[i+1:i+pivot+1]):
            swing_lows.append({"index":i,"price":lows[i]})
    last=float(candles[-1]["close"])
    previous_high=swing_highs[-1] if swing_highs else None
    previous_low=swing_lows[-1] if swing_lows else None
    bos="BULLISH" if previous_high and last>previous_high["price"] else ("BEARISH" if previous_low and last<previous_low["price"] else "NONE")
    trend="UNKNOWN"
    if len(swing_highs)>=2 and len(swing_lows)>=2:
        hh=swing_highs[-1]["price"]>swing_highs[-2]["price"]
        hl=swing_lows[-1]["price"]>swing_lows[-2]["price"]
        lh=swing_highs[-1]["price"]<swing_highs[-2]["price"]
        ll=swing_lows[-1]["price"]<swing_lows[-2]["price"]
        trend="UPTREND" if hh and hl else ("DOWNTREND" if lh and ll else "MIXED")
    choch="BULLISH" if trend=="DOWNTREND" and bos=="BULLISH" else ("BEARISH" if trend=="UPTREND" and bos=="BEARISH" else "NONE")
    return {"status":"ok","trend":trend,"break_of_structure":bos,"change_of_character":choch,
            "last_swing_high":previous_high,"last_swing_low":previous_low,
            "swing_high_count":len(swing_highs),"swing_low_count":len(swing_lows),
            "pivot_bars":pivot,"samples":len(candles),
            "method":"confirmed fractal pivots; pivots require right-side candles and are not backdated as live signals"}


def opportunity_assessment(analysis: dict[str, Any], regime: dict[str, Any], structure: dict[str, Any]) -> dict[str, Any]:
    direction=analysis.get("direction","NEUTRAL")
    score=max(0,min(100,int(analysis.get("score") or 0)))
    confirmations=[]
    conflicts=[]
    if regime.get("status")=="ok":
        if (direction=="LONG" and regime.get("trend")=="UPTREND") or (direction=="SHORT" and regime.get("trend")=="DOWNTREND"):
            score=min(100,score+8); confirmations.append("regime_alignment")
        elif direction in ("LONG","SHORT") and regime.get("trend") in ("UPTREND","DOWNTREND"):
            score=max(0,score-8); conflicts.append("regime_conflict")
    if structure.get("status")=="ok":
        bos=structure.get("break_of_structure")
        if (direction=="LONG" and bos=="BULLISH") or (direction=="SHORT" and bos=="BEARISH"):
            score=min(100,score+10); confirmations.append("structure_breakout")
        elif bos!="NONE":
            conflicts.append("opposing_structure_break")
    if analysis.get("volumeRatio") is not None and analysis["volumeRatio"]>=1.5:
        confirmations.append("volume_confirmation")
    if direction=="NEUTRAL": tier="SILVER"; action="WAIT"
    elif score>=85 and len(confirmations)>=2 and not conflicts: tier="GOLD"; action="CONFIRMED_SETUP"
    elif score>=70 and confirmations: tier="GREEN"; action="WATCH_FOR_ENTRY"
    else: tier="SILVER"; action="NEEDS_CONFIRMATION"
    return {"status":"ok","symbol":analysis.get("symbol"),"direction":direction,"score":score,
            "tier":tier,"action":action,"confirmations":confirmations,"conflicts":conflicts,
            "entry":analysis.get("entry"),"stop_loss":analysis.get("stopLoss"),
            "targets":[x for x in (analysis.get("target1"),analysis.get("target2")) if x is not None],
            "classification_note":"Confluence score is a heuristic, not a calibrated win probability.",
            "trading_mode":"simulation","live_trading_enabled":False}


def learning_monitoring(closed_trades: list[dict[str, Any]], open_trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnl=[float(t.get("pnl") or 0) for t in closed_trades]
    wins=[x for x in pnl if x>0]; losses=[x for x in pnl if x<0]
    total=len(pnl); gross_profit=sum(wins); gross_loss=abs(sum(losses))
    return {"status":"ok","source":"paper_ledger","closed_trades":total,"open_trades":len(open_trades),
            "win_rate_pct":round(len(wins)/total*100,2) if total else None,
            "net_pnl":round(sum(pnl),8),"profit_factor":round(gross_profit/gross_loss,4) if gross_loss else (None if not gross_profit else "infinite"),
            "average_win":round(mean(wins),8) if wins else None,
            "average_loss":round(mean(losses),8) if losses else None,
            "monitoring_alerts":[("NO_CLOSED_TRADES" if total==0 else "SAMPLE_SIZE_LOW")] if total<30 else [],
            "learning_mode":"performance_observation_only","automatic_retraining":False,
            "strategy_promotion":"manual_only",
            "disclaimer":"Metrics describe recorded paper trades only; no model training or live strategy promotion is performed."}
