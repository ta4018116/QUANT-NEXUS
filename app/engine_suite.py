Warning: truncated output (original token count: 39411)
Total output lines: 2831

"""Runtime adapters for the 156-engine QUANT NEXUS catalogue.

Every catalogue entry has a callable contract. A result is either computed from
provided, validated evidence or explicitly blocked because its required input
(model artifact, provider feed, portfolio data, etc.) is absent. No fabricated
market data, probabilities, or orders are produced.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import exp, isfinite, sqrt
import random
from statistics import NormalDist, mean, median, pstdev
from typing import Any

from .engine_catalog import ENGINE_CATALOG
from .model_lifecycle import predict_direction_model


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _fresh_observation(context: dict, key: str, max_age_seconds: int = 60) -> bool:
    value = context.get(key)
    if not value:
        return False
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        return 0 <= age <= max_age_seconds
    except (TypeError, ValueError, OverflowError):
        return False


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _candles(ctx: dict) -> list[dict]:
    rows = ctx.get("candles") or []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {key: _num(row.get(key)) for key in ("open", "high", "low", "close", "volume")}
        if item["open"] <= 0 or item["close"] <= 0 or item["high"] <= 0 or item["low"] <= 0:
            continue
        if item["high"] < max(item["open"], item["close"], item["low"]) or item["low"] > min(item["open"], item["close"], item["high"]):
            continue
        result.append(item)
    return result


def _raw_candle_records(ctx: dict) -> list:
    """Preserve raw provider rows for normalization and quality adapters."""
    rows = ctx.get("raw_candle_rows")
    if not isinstance(rows, list):
        rows = ctx.get("candles") or []
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append(row)
        elif isinstance(row, (list, tuple)) and len(row) >= 6:
            result.append({"time":row[0],"open":row[1],"high":row[2],
                           "low":row[3],"close":row[4],"volume":row[5]})
        else:
            result.append(row)
    return result


def _ready(value: Any, method: str, **extra) -> dict:
    return {"status": "computed", "method": method, "value": value, **extra}


def _blocked(reason: str, missing: list[str] | None = None) -> dict:
    return {"status": "blocked_missing_input", "reason": reason, "missing_inputs": missing or []}


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period < 1:
        return None
    value = mean(values[:period])
    alpha = 2.0 / (period + 1.0)
    for point in values[period:]:
        value = alpha * point + (1.0 - alpha) * value
    return value


def _atr(rows: list[dict], period: int = 14) -> float | None:
    if len(rows) < period + 1:
        return None
    tr = []
    previous = rows[0]["close"]
    for row in rows[1:]:
        tr.append(max(row["high"] - row["low"], abs(row["high"] - previous), abs(row["low"] - previous)))
        previous = row["close"]
    value = mean(tr[:period])
    for point in tr[period:]:
        value = (value * (period - 1) + point) / period
    return value


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain else 50.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def _base(ctx: dict, minimum: int = 30):
    rows = _candles(ctx)
    if len(rows) < minimum:
        return rows, _blocked("insufficient_valid_completed_candles", ["candles", f"minimum_{minimum}_bars"])
    return rows, None


def _trend(ctx):
    rows, err = _base(ctx, 50)
    if err: return err
    closes = [x["close"] for x in rows]
    fast, slow = _ema(closes, 20), _ema(closes, 50)
    slope = (closes[-1] / closes[-21] - 1.0) * 100 if closes[-21] else 0.0
    direction = "UP" if fast and slow and fast > slow and slope > 0 else "DOWN" if fast and slow and fast < slow and slope < 0 else "RANGE"
    return _ready({"direction": direction, "ema20": fast, "ema50": slow, "slope20_pct": round(slope, 5)}, "EMA20/EMA50 plus 20-bar close slope")


def _support_resistance(ctx):
    rows, err = _base(ctx, 30)
    if err: return err
    window = rows[-50:]
    current = rows[-1]["close"]
    highs = sorted(x["high"] for x in window)
    lows = sorted(x["low"] for x in window)
    support_zone = [lows[0], lows[min(4, len(lows)-1)]]
    resistance_zone = [highs[max(0, len(highs)-5)], highs[-1]]
    return _ready({"support_zone": support_zone,
                   "resistance_zone": resistance_zone,
                   "nearest_support_distance_pct": round((current-support_zone[1])/current*100, 4),
                   "nearest_resistance_distance_pct": round((resistance_zone[0]-current)/current*100, 4)},
                  "lowest/highest five extrema of the trailing 50 completed candles")


def _compression(ctx):
    rows, err = _base(ctx, 50)
    if err: return err
    ranges = [(x["high"]-x["low"])/x["close"] for x in rows if x["close"] > 0]
    recent = mean(ranges[-10:])
    baseline = mean(ranges[-40:-10])
    ratio = recent / baseline if baseline else None
    return _ready({"range_ratio": round(ratio, 4) if ratio is not None else None,
                   "compressed": bool(ratio is not None and ratio < 0.65),
                   "recent_range_pct": round(recent*100, 4), "baseline_range_pct": round(baseline*100, 4)},
                  "10-bar mean high-low percentage versus prior 30-bar baseline")


def _volume(ctx):
    rows, err = _base(ctx, 25)
    if err: return err
    volumes = [x["volume"] for x in rows]
    baseline = mean(volumes[-21:-1])
    if baseline <= 0 or volumes[-1] <= 0:
        return _blocked("positive completed-candle volume and a positive 20-bar baseline are required",["positive_volume_history"])
    ratio = volumes[-1] / baseline if baseline > 0 else None
    dispersion = pstdev(volumes[-21:-1]) if len(volumes) >= 21 else 0
    z = (volumes[-1]-baseline)/dispersion if dispersion else 0
    return _ready({"latest_volume": volumes[-1], "baseline_volume": baseline,
                   "volume_ratio": round(ratio, 4) if ratio is not None else None,
                   "volume_zscore": round(z, 4), "anomaly": z >= 2.5},
                  "latest completed-bar volume against prior 20 completed bars")


def _accumulation(ctx):
    rows, err = _base(ctx, 40)
    if err: return err
    window = rows[-30:]
    closes = [x["close"] for x in window]
    volumes = [x["volume"] for x in window]
    price_change = (closes[-1]/closes[0]-1)*100 if closes[0] else 0
    signed = [((x["close"]-x["open"])/(x["high"]-x["low"]) if x["high"] > x["low"] else 0)*x["volume"] for x in window]
    flow = sum(signed)
    denom = sum(volumes)
    close_location = (closes[-1]-min(x["low"] for x in window))/(max(x["high"] for x in window)-min(x["low"] for x in window)) if max(x["high"] for x in window)>min(x["low"] for x in window) else 0.5
    return _ready({"price_change_30_pct": round(price_change, 4),
                   "signed_volume_pressure": round(flow/denom, 4) if denom else None,
                   "close_location_in_range": round(close_location, 4),
                   "possible_absorption": bool(abs(price_change) < 2.0 and flow > 0 and close_location > 0.55)},
                  "OHLCV signed-volume proxy; cannot identify a specific institutional buyer")


def _sweep(ctx):
    rows, err = _base(ctx, 10)
    if err: return err
    prior = rows[-9:-1]
    last = rows[-1]
    prior_high, prior_low = max(x["high"] for x in prior), min(x["low"] for x in prior)
    bull = last["low"] < prior_low and last["close"] > prior_low
    bear = last["high"] > prior_high and last["close"] < prior_high
    return _ready({"bullish_sweep": bull, "bearish_sweep": bear,
                   "prior_high": prior_high, "prior_low": prior_low},
                  "last completed candle versus previous eight completed candles")


def _breakout(ctx):
    rows, err = _base(ctx, 25)
    if err: return err
    prior = rows[-21:-1]
    last = rows[-1]
    hi, lo = max(x["high"] for x in prior), min(x["low"] for x in prior)
    vol_base = mean(x["volume"] for x in prior)
    if vol_base <= 0 or last["volume"] <= 0:
        return _blocked("positive breakout-candle volume and prior 20-bar volume baseline are required",
                        ["positive_completed_candle_volume", "positive_prior_volume_baseline"])
    vol_ratio = last["volume"]/vol_base if vol_base else 0
    return _ready({"breakout_up": last["close"] > hi, "breakout_down": last["close"] < lo,
                   "prior_20_high": hi, "prior_20_low": lo, "volume_ratio": round(vol_ratio, 4),
                   "volume_confirmed": vol_ratio >= 1.5},
                  "completed-candle close beyond prior 20-bar range")


def _momentum(ctx):
    rows, err = _base(ctx, 20)
    if err: return err
    closes = [x["close"] for x in rows]
    atr = _atr(rows)
    change = (closes[-1]/closes[-6]-1)*100 if closes[-6] else 0
    rsi = _rsi(closes)
    return _ready({"return_5_pct": round(change, 4), "rsi14": round(rsi, 4) if rsi is not None else None,
                   "atr14": atr, "direction": "UP" if change > 0 else "DOWN" if change < 0 else "FLAT"},
                  "5-bar return, Wilder RSI14 and ATR14")


def _fvg(ctx):
    rows, err = _base(ctx, 3)
    if err: return err
    gaps = []
    for i in range(2, len(rows)):
        a, c = rows[i-2], rows[i]
        if c["low"] > a["high"]:
            gaps.append({"side":"BULLISH", "low":a["high"], "high":c["low"], "bar_index":i})
        elif c["high"] < a["low"]:
            gaps.append({"side":"BEARISH", "low":c["high"], "high":a["low"], "bar_index":i})
    return _ready({"recent_gaps": gaps[-10:], "count": len(gaps)},
                  "three-candle non-overlap heuristic; not proof of resting institutional orders")


def _candlestick(ctx):
    rows, err = _base(ctx, 3)
    if err: return err
    x = rows[-1]
    body = abs(x["close"]-x["open"])
    span = x["high"]-x["low"]
    upper = x["high"]-max(x["open"],x["close"])
    lower = min(x["open"],x["close"])-x["low"]
    patterns = []
    if span and body/span <= 0.1: patterns.append("DOJI")
    if body and lower >= body*2 and upper <= body*0.7: patterns.append("HAMMER_OR_HANGING_MAN")
    if body and upper >= body*2 and lower <= body*0.7: patterns.append("SHOOTING_STAR_OR_INVERTED_HAMMER")
    prev = rows[-2]
    if x["close"] > x["open"] and prev["close"] < prev["open"] and x["close"] >= prev["open"] and x["open"] <= prev["close"]:
        patterns.append("BULLISH_ENGULFING")
    if x["close"] < x["open"] and prev["close"] > prev["open"] and x["open"] >= prev["close"] and x["close"] <= prev["open"]:
        patterns.append("BEARISH_ENGULFING")
    return _ready({"patterns":patterns, "body_pct_of_range":round(body/span*100,2) if span else 0},
                  "OHLC candle geometry; context confirmation required")


def _fibonacci(ctx):
    rows, err = _base(ctx, 20)
    if err: return err
    window = rows[-100:]
    high = max(x["high"] for x in window); low = min(x["low"] for x in window)
    diff = high-low
    levels = {str(k): round(high-diff*k, 10) for k in (0.236,0.382,0.5,0.618,0.786)}
    return _ready({"swing_high":high,"swing_low":low,"retracement_levels":levels},
                  "retracements of last 100-bar high-low range")


def _volume_profile(ctx):
    rows, err = _base(ctx, 20)
    if err: return err
    bins = max(5, min(40, int(ctx.get("profile_bins") or 20)))
    lo=min(x["low"] for x in rows[-100:]); hi=max(x["high"] for x in rows[-100:])
    if hi <= lo: return _blocked("zero_price_range", ["nonzero_candle_range"])
    step=(hi-lo)/bins; buckets=[0.0]*bins
    for x in rows[-100:]:
        idx=min(bins-1,max(0,int(((x["high"]+x["low"])/2-lo)/step)))
        buckets[idx]+=x["volume"]
    max_idx=max(range(bins),key=lambda i:buckets[i])
    return _ready({"poc_approx":lo+(max_idx+0.5)*step,"bins":bins,
                   "total_volume":sum(buckets),"method_note":"Approximate close-location volume bins; not tick-level volume-at-price"},
                  "OHLCV volume-by-midrange approximation")


def _divergence(ctx):
    rows, err = _base(ctx, 35)
    if err: return err
    closes=[x["close"] for x in rows]
    rsi_values=[]
    for i in range(15,len(closes)+1):
        val=_rsi(closes[:i])
        if val is not None: rsi_values.append(val)
    if len(rsi_values)<12: return _blocked("insufficient_rsi_history",["at_least_12_rsi_observations"])
    price_old=min(closes[-12:-6]); price_new=min(closes[-6:])
    rsi_old=min(rsi_values[-12:-6]); rsi_new=min(rsi_values[-6:])
    bull=price_new<price_old and rsi_new>rsi_old
    high_old=max(closes[-12:-6]); high_new=max(closes[-6:])
    rsi_high_old=max(rsi_values[-12:-6]); rsi_high_new=max(rsi_values[-6:])
    bear=high_new>high_old and rsi_high_new<rsi_high_old
    return _ready({"bullish_rsi_divergence_candidate":bull,"bearish_rsi_divergence_candidate":bear,
                   "price_lows":[price_old,price_new],"rsi_lows":[rsi_old,rsi_new]},
                  "two-window RSI divergence candidate; pivots not yet confirmed")


def _market_phase(ctx):
    rows, err = _base(ctx, 60)
    if err: return err
    comp=_compression(ctx); acc=_accumulation(ctx); br=_breakout(ctx)
    if br.get("status")=="computed" and (br["value"]["breakout_up"] or br["value"]["breakout_down"]):
        phase="MARKUP_OR_MARKDOWN"
    elif comp.get("status")=="computed" and comp["value"]["compressed"] and acc.get("status")=="computed" and acc["value"]["possible_absorption"]:
        phase="POSSIBLE_ACCUMULATION"
    else: phase="RANGE_OR_TRANSITION"
    return _ready({"phase":phase},"compression, signed-volume and completed breakout evidence")


def _timing(ctx):
    rows, err = _base(ctx, 5)
    if err: return err
    ts = ctx.get("timestamp_utc")
    if not ts: return _blocked("UTC timestamp required for session classification",["timestamp_utc"])
    try:
        hour=int(str(ts)[11:13])
    except (ValueError, TypeError):
        return _blocked("timestamp_utc must be ISO-8601",["valid_timestamp_utc"])
    session="ASIA" if 0<=hour<8 else "LONDON" if 7<=hour<16 else "NEW_YORK" if 12<=hour<21 else "QUIET"
    return _ready({"utc_hour":hour,"session":session},"UTC clock windows; overlaps are simplified and do not encode exchange holidays")


def _derivatives(ctx):
    data=ctx.get("derivatives")
    if not isinstance(data,dict): return _blocked("verified derivatives snapshot required",["derivatives.open_interest","derivatives.funding_rate"])
    oi=_num(data.get("open_interest"),-1); funding=_num(data.get("funding_rate"),float("nan"))
    if oi<0 or not isfinite(funding): return _blocked("open interest and funding rate missing",["open_interest","funding_rate"])
    return _ready({"open_interest":oi,"funding_rate":funding,
                   "crowding":"LONG_CROWDED" if funding>0.001 else "SHORT_CROWDED" if funding<-0.001 else "NEUTRAL"},
                  "provider-supplied derivatives fields; thresholds are heuristics")


def _orderbook(ctx):
    book=ctx.get("orderbook")
    if not isinstance(book,dict): return _blocked("orderbook snapshot required",["orderbook.bids","orderbook.asks"])
    bids=book.get("bids") or []; asks=book.get("asks") or []
    try:
        bid=sum(_num(x[0])*_num(x[1]) for x in bids[:20] if len(x)>=2)
        ask=sum(_num(x[0])*_num(x[1]) for x in asks[:20] if len(x)>=2)
    except (TypeError,IndexError): return _blocked("invalid orderbook rows",["normalized price-size levels"])
    total=bid+ask
    if total<=0: return _blocked("empty orderbook depth",["nonzero bid and ask depth"])
    return _ready({"bid_notional":bid,"ask_notional":ask,"imbalance":(bid-ask)/total,
                   "bias":"BID" if bid/total>=0.6 else "ASK" if ask/total>=0.6 else "BALANCED"},
                  "top-20 level notional snapshot; orders may be cancelled")


def _trades(ctx):
    trades=ctx.get("trades")
    if not isinstance(trades,list) or not trades: return _blocked("recent trade prints required",["trades"])
    valid=[x for x in trades if isinstance(x,dict) and _num(x.get("price"))>0 and _num(x.get("size"))>0]
    if not valid: return _blocked("no valid trade prints",["normalized trades"])
    buy=sum(_num(x["price"])*_num(x["size"]) for x in valid if str(x.get("side","")).upper()=="BUY")
    sell=sum(_num(x["price"])*_num(x["size"]) for x in valid if str(x.get("side","")).upper()=="SELL")
    return _ready({"buy_notional":buy,"sell_notional":sell,"delta_notional":buy-sell,
                   "buy_sell_ratio":buy/sell if sell else None},
                  "aggressor side notional from provider trade prints; not whale identity")


def _risk(ctx):
    account=ctx.get("account")
    if not isinstance(account,dict): return _blocked("paper account and position plan required",["account.equity","plan.entry","plan.stop"])
    equity=_num(account.get("equity")); plan=ctx.get("plan") or {}
    entry=_num(plan.get("entry")); stop=_num(plan.get("stop"))
    if equity<=0 or entry<=0 or stop<=0 or entry==stop: return _blocked("valid paper equity, entry and stop required",["positive_equity","entry","stop"])
    risk_pct=min(2.0,max(0.0,_num(ctx.get("risk_pct"),1.0)))
    risk_amount=equity*risk_pct/100
    qty=risk_amount/abs(entry-stop)
    return _ready({"risk_pct":risk_pct,"risk_amount":risk_amount,"quantity":qty,
                   "notional":qty*entry,"trading_mode":"simulation"},
                  "fixed-fraction sizing before fees and slippage; simulation only")


def _risk_reward(ctx):
    plan=ctx.get("plan") or {}
    entry=_num(plan.get("entry"));stop=_num(plan.get("stop"));target=_num(plan.get("target"))
    side=str(plan.get("side","")).upper()
    if entry<=0 or stop<=0 or target<=0 or side not in ("LONG","SHORT") or entry==stop:
        return _blocked("valid entry, stop, target and side required",["plan.entry","plan.stop","plan.target","plan.side"])
    risk=abs(entry-stop)
    reward=(target-entry) if side=="LONG" else (entry-target)
    if reward<=0:
        return _blocked("target is on the wrong side of the entry",["target_beyond_entry_in_trade_direction"])
    minimum=max(0.1,_num(ctx.get("minimum_reward_risk"),1.5))
    ratio=reward/risk
    return _ready({"entry":entry,"stop":stop,"target":target,"side":side,
                   "risk_distance":risk,"reward_distance":reward,
                   "reward_risk_ratio":round(ratio,5),"minimum_ratio":minimum,
                   "meets_minimum":ratio>=minimum},
                  "paper-plan reward/risk arithmetic; excludes fees, funding, slippage and fill probability")


def _portfolio(ctx):
    positions=ctx.get("positions")
    if not isinstance(positions,list): return _blocked("paper positions required",["positions"])
    open_positions=[x for x in positions if isinstance(x,dict) and x.get("status")=="OPEN"]
    exposure=sum(abs(_num(x.get("entry"))*_num(x.get("quantity"))) for x in open_positions)
    return _ready({"open_positions":len(open_positions),"gross_exposure":exposure},
                  "paper ledger aggregation only")


def _backtest(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list): return _blocked("closed paper/backtest trades required",["closed_trades"])
    pnls=[_num(x.get("pnl")) for x in trades if isinstance(x,dict)]
    wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
    return _ready({"trade_count":len(pnls),"win_rate_pct":len(wins)/len(pnls)*100 if pnls else None,
                   "net_pnl":sum(pnls),"profit_factor":sum(wins)/abs(sum(losses)) if sum(losses) else None},
                  "historical or paper closed-trade metrics; not forward performance")


def _agents(ctx):
    agents=ctx.get("agent_results")
    if not isinstance(agents,list) or not agents:
        # Build transparent deterministic sub-agents from one shared market snapshot.
        agents=[]
        trend=_trend(ctx)
        if trend.get("status")=="computed":
            d=trend["value"]["direction"]
            agents.append({"name":"technical_trend","direction":"LONG" if d=="UP" else "SHORT" if d=="DOWN" else "NEUTRAL"})
        momentum=_momentum(ctx)
        if momentum.get("status")=="computed":
            d=str(momentum["value"].get("direction","")).upper()
            agents.append({"name":"momentum","direction":"LONG" if d in ("UP","BULLISH","POSITIVE") else "SHORT" if d in ("DOWN","BEARISH","NEGATIVE") else "NEUTRAL"})
        book=_orderbook(ctx)
        if book.get("status")=="computed":
            d=book["value"].get("bias")
            agents.append({"name":"orderbook_imbalance","direction":"LONG" if d=="BID" else "SHORT" if d=="ASK" else "NEUTRAL"})
        ai=_ai_analyst(ctx)
        if ai.get("status")=="computed":
            d=ai["value"].get("directional_context")
            agents.append({"name":"explainable_market_analyst","direction":"LONG" if d=="UP" else "SHORT" if d=="DOWN" else "NEUTRAL"})
    valid=[x for x in agents if isinstance(x,dict) and x.get("direction") in ("LONG","SHORT","NEUTRAL")]
    if not valid: return _blocked("no directional agent could compute from the market snapshot",["completed_candles","orderbook"])
    long=sum(x["direction"]=="LONG" for x in valid); short=sum(x["direction"]=="SHORT" for x in valid)
    direction="LONG" if long>short else "SHORT" if short>long else "NEUTRAL"
    return _ready({"agents":len(valid),"agent_assessments":valid,"long_votes":long,"short_votes":short,"consensus":direction,
                   "agreement_pct":max(long,short)/len(valid)*100,
                   "independence":"shared snapshot; agents are rule-based and not statistically independent"},
                  "deterministic technical, momentum, order-book and explainable-agent consensus; not an independent prediction")


def _external(ctx):
    return _blocked("specialized external feed, trained artifact, or verified service is not configured",
                    ["verified_provider_or_model_artifact"])


def _early_breakout(ctx):
    rows, err = _base(ctx, 50)
    if err: return err
    comp=_compression(ctx); vol=_volume(ctx)
    last=rows[-1]["close"]; high=max(x["high"] for x in rows[-21:-1]); low=min(x["low"] for x in rows[-21:-1])
    width=(high-low)/last if last else 0
    proximity=min(abs(high-last),abs(last-low))/last if last else 1
    compressed=comp.get("status")=="computed" and comp["value"]["compressed"]
    volume_ratio=vol.get("value",{}).get("volume_ratio") if vol.get("status")=="computed" else None
    near_edge=proximity<=0.004
    candidate=bool(compressed and near_edge and (volume_ratio is None or volume_ratio>=1.1))
    return _ready({"early_breakout_candidate":candidate,"compressed":compressed,
                   "near_range_edge":near_edge,"distance_to_edge_pct":round(proximity*100,4),
                   "range_high":high,"range_low":low,"volume_ratio":volume_ratio},
                  "pre-breakout proximity and compression heuristic; candidate is not a confirmed breakout")


def _momentum_explosion(ctx):
    rows, err = _base(ctx, 25)
    if err: return err
    v=_volume(ctx); atr=_atr(rows)
    last=rows[-1]
    body=abs(last["close"]-last["open"])
    body_atr=body/atr if atr else None
    z=v.get("value",{}).get("volume_zscore") if v.get("status")=="computed" else None
    return _ready({"volume_zscore":z,"body_atr":round(body_atr,4) if body_atr is not None else None,
                   "explosion_candidate":bool(z is not None and z>=2.5 and body_atr is not None and body_atr>=0.8)},
                  "completed-candle volume z-score plus body-to-ATR expansion")


def _whale_activity(ctx):
    trades=ctx.get("trades")
    if not isinstance(trades,list) or len(trades)<5:
        return _blocked("recent normalized trade prints required",["at_least_5_trades"])
    sizes=[_num(x.get("price"))*_num(x.get("size")) for x in trades if isinstance(x,dict) and _num(x.get("price"))>0 and _num(x.get("size"))>0]
    if len(sizes)<5: return _blocked("not enough valid trade notionals",["valid_trade_prints"])
    med=median(sizes); threshold=max(med*5, _num(ctx.get("large_trade_min_notional"),0))
    large=[{"notional":x,"index":i} for i,x in enumerate(sizes) if x>=threshold]
    return _ready({"median_print_notional":med,"large_print_threshold":threshold,
                   "large_print_count":len(large),"large_prints":large[-20:]},
                  "statistical print-size outliers; cannot attribute wallet identity or intent")


def _higher_timeframe(ctx):
    frames=ctx.get("timeframes")
    item=frames.get("4h") if isinstance(frames,dict) else None
    if not _valid_timeframe_snapshot(item): return _blocked("fresh completed 4h snapshot required",["timeframes.4h"])
    return _ready({"timeframe":"4h","direction":item.get("direction"),"score":item.get("score")},
                  "higher timeframe snapshot supplied by multi-timeframe provider")


def _lower_timeframe(ctx):
    frames=ctx.get("timeframes")
    candidates=(frames.get("5m"),frames.get("15m")) if isinstance(frames,dict) else ()
    item=next((candidate for candidate in candidates if _valid_timeframe_snapshot(candidate)),None)
    if not isinstance(item,dict): return _blocked("fresh completed 5m or 15m snapshot required",["timeframes.5m_or_15m"])
    return _ready({"timeframe":item.get("timeframe","5m_or_15m"),
                   "direction":item.get("direction"),"score":item.get("score")},
                  "lower timeframe snapshot supplied by multi-timeframe provider")


def _regime_timeframe_sync(ctx):
    frames=ctx.get("timeframes")
    valid=[item for item in frames.values() if _valid_timeframe_snapshot(item)] if isinstance(frames,dict) else []
    if len(valid)<2: return _blocked("at least two fresh completed timeframe snapshots required",["timeframes"])
    return _timeframes(ctx)



def _vwap(ctx):
    rows, err = _base(ctx, 10)
    if err: return err
    denom=sum(x["volume"] for x in rows[-50:])
    if denom<=0: return _blocked("volume unavailable for VWAP",["positive_volume"])
    value=sum(((x["high"]+x["low"]+x["close"])/3)*x["volume"] for x in rows[-50:])/denom
    return _ready({"vwap_50":value,"last_close":rows[-1]["close"],"above_vwap":rows[-1]["close"]>value},
                  "50-bar typical-price volume weighted average")


def _market_structure(ctx):
    rows, err = _base(ctx, 20)
    if err: return err
    highs=[x["high"] for x in rows]; lows=[x["low"] for x in rows]
    swings_h=[]; swings_l=[]; p=3
    for i in range(p,len(rows)-p):
        if highs[i]>=max(highs[i-p:i+p+1]) and highs[i]>max(highs[i-p:i]+highs[i+1:i+p+1]): swings_h.append((i,highs[i]))
        if lows[i]<=min(lows[i-p:i+p+1]) and lows[i]<min(lows[i-p:i]+lows[i+1:i+p+1]): swings_l.append((i,lows[i]))
    trend="UNKNOWN"
    if len(swings_h)>=2 and len(swings_l)>=2:
        up=swings_h[-1][1]>swings_h[-2][1] and swings_l[-1][1]>swings_l[-2][1]
        down=swings_h[-1][1]<swings_h[-2][1] and swings_l[-1][1]<swings_l[-2][1]
        trend="UPTREND" if up else "DOWNTREND" if down else "MIXED"
    last=rows[-1]["close"]
    bos="BULLISH" if swings_h and last>swings_h[-1][1] else "BEARISH" if swings_l and last<swings_l[-1][1] else "NONE"
    return _ready({"trend":trend,"break_of_structure":bos,
                   "last_swing_high":swings_h[-1][1] if swings_h else None,
                   "last_swing_low":swings_l[-1][1] if swings_l else None},
                  "confirmed 3-bar fractal pivots on completed candles")


def _cross_market_correlation(ctx):
    related=ctx.get("related_closes")
    base=[_num(x) for x in (ctx.get("correlation_base_closes") or ctx.get("closes",[]))]
    if not isinstance(related,dict) or len(base)<3:
        return _blocked("aligned close series for related markets required",["closes","related_closes"])
    base_r=[base[i]/base[i-1]-1 for i in range(1,len(base)) if base[i-1]>0]
    results={}
    for symbol, values in related.items():
        v=[_num(x) for x in values]
        r=[v[i]/v[i-1]-1 for i in range(1,len(v)) if v[i-1]>0]
        n=min(len(base_r),len(r))
        if n<3: results[str(symbol)]={"status":"insufficient_samples"}; continue
        a=base_r[-n:]; b=r[-n:]; ma=mean(a); mb=mean(b)
        da=[x-ma for x in a]; db=[x-mb for x in b]
        den=sqrt(sum(x*x for x in da)*sum(x*x for x in db))
        results[str(symbol)]={"correlation":sum(x*y for x,y in zip(da,db))/den if den else None,"samples":n}
    return _ready(results,"Pearson correlation of aligned close-to-close returns")


def _supply_demand(ctx):
    result=_support_resistance(ctx)
    if result.get("status")!="computed": return result
    rows=_candles(ctx); window=rows[-50:]
    low_zone=result["value"]["support_zone"]; high_zone=result["value"]["resistance_zone"]
    last=rows[-1]["close"]
    return _ready({"demand_zone":low_zone,"supply_zone":high_zone,
                   "near_demand":low_zone[0]<=last<=low_zone[1],
                   "near_supply":high_zone[0]<=last<=high_zone[1]},
                  "rolling support/resistance as demand/supply proxy; no resting-order claim")


def _order_block(ctx):
    rows, err = _base(ctx, 8)
    if err: return err
    candidates=[]
    for i in range(max(1,len(rows)-30),len(rows)-1):
        prev, nxt=rows[i-1],rows[i]
        if prev["close"]<prev["open"] and nxt["close"]>prev["high"]:
            candidates.append({"side":"BULLISH","low":prev["low"],"high":prev["open"],"bar_index":i-1})
        if prev["close"]>prev["open"] and nxt["close"]<prev["low"]:
            candidates.append({"side":"BEARISH","low":prev["open"],"high":prev["high"],"bar_index":i-1})
    return _ready({"candidates":candidates[-5:],"count":len(candidates)},
                  "last opposite candle before a close beyond its full range; heuristic zone")


def _long_short(ctx):
    data=ctx.get("derivatives") or {}
    ratio=_num(data.get("long_short_ratio"),-1)
    if ratio<=0: return _blocked("verified long/short ratio feed required",["derivatives.long_short_ratio"])
    return _ready({"long_short_ratio":ratio,"crowded":"LONG" if ratio>1.5 else "SHORT" if ratio<0.67 else "BALANCED"},
                  "provider-reported long/short ratio; population scope must be checked")


def _liquidation_tracker(ctx):
    events=ctx.get("liquidations")
    if not isinstance(events,list): return _blocked("normalized liquidation events required",["liquidations"])
    valid=[x for x in events if isinstance(x,dict) and _num(x.get("notional_usdt"))>0]
    return _ready({"event_count":len(valid),"long_notional":sum(_num(x.get("notional_usdt")) for x in valid if x.get("liquidated_position")=="LONG"),
                   "short_notional":sum(_num(x.get("notional_usdt")) for x in valid if x.get("liquidated_position")=="SHORT")},
                  "executed public liquidation prints only; not a liquidation-risk heatmap")


def _basis(ctx):
    spot=_num(ctx.get("spot_price")); future=_num(ctx.get("futures_price"))
    if spot<=0 or future<=0: return _blocked("synchronized spot and futures marks required",["spot_price","futures_price"])
    return _ready({"basis":future-spot,"basis_pct":(future/spot-1)*100},
                  "synchronized spot-versus-futures mark comparison")


def _arbitrage(ctx):
    prices=ctx.get("exchange_prices")
    if not isinstance(prices,dict) or len(prices)<2: return _blocked("two or more synchronized venue marks required",["exchange_prices"])
    clean={str(k):_num(v) for k,v in prices.items() if _num(v)>0}
    if len(clean)<2: return _blocked("insufficient valid venue marks",["positive_exchange_prices"])
    buy=min(clean,key=clean.get); sell=max(clean,key=clean.get)
    gross=(clean[sell]/clean[buy]-1)*100
    costs_verified=ctx.get("execution_costs_verified") is True
    fee=ctx.get("round_trip_fee_pct"); slip=ctx.get("round_trip_slippage_pct")
    if costs_verified and fee is not None and slip is not None:
        net=gross-_num(fee)-_num(slip)
        net_known=True
    else:
        net=None
        net_known=False
    return _ready({"buy_venue":buy,"sell_venue":sell,"gross_spread_pct":gross,
                   "estimated_net_spread_pct":net,"positive_after_costs":(net>0) if net_known else None,
                   "execution_costs_verified":net_known,"venue_marks":clean,
                   "execution_permitted":False},
                  "read-only simultaneous venue-mark comparison; net spread withheld until verified fees/slippage are supplied; excludes transfer, funding and latency risk")


def _opportunity(ctx):
    result=early_opportunity_assessment(ctx)
    if result.get("status")!="computed": return result
    return _ready({k:result.get(k) for k in ("score","tier","reasons","missing_confirmations","breakout_confirmed","watch_entry_zone","invalidation_reference","targets_reference")},
                  "pre-breakout confluence assessment; watch-only, no trade order")


def _generic_score(ctx):
    evidence=ctx.get("evidence_scores")
    if not isinstance(evidence,dict) or not evidence: return _blocked("named engine evidence scores required",["evidence_scores"])
    valid=[_clamp(_num(v)) for v in evidence.values() if v is not None]
    if not valid: return _blocked("no valid evidence scores",["numeric evidence scores"])
    return _ready({"confluence_score":round(mean(valid),2),"evidence_count":len(valid),"evidence":evidence},
                  "unweighted mean of supplied subsystem scores; not win probability")


def _timeframes(ctx):
    frames=ctx.get("timeframes")
    valid=[(name,item) for name,item in frames.items() if _valid_timeframe_snapshot(item)] if isinstance(frames,dict) else []
    if len(valid)<2: return _blocked("at least two fresh completed timeframe analyses required",["timeframes"])
    directions=[str(item.get("direction","NEUTRAL")).upper() for _,item in valid]
    directional=[x for x in directions if x in ("UP","DOWN","LONG","SHORT")]
    if not directional: return _blocked("timeframe direction values missing",["timeframes.*.direction"])
    up=sum(x in ("UP","LONG") for x in directional); down=sum(x in ("DOWN","SHORT") for x in directional)
    return _ready({"up_frames":up,"down_frames":down,"total_directional_frames":len(directional),
                   "frames_used":[name for name,_ in valid],
                   "latest_completed_at":max(item["last_completed_at"] for _,item in valid),
                   "consensus":"UP" if up>down else "DOWN" if down>up else "MIXED",
                   "agreement_pct":max(up,down)/len(directional)*100},
                  "directional agreement across provided frame snapshots")


_TIMEFRAME_SECONDS={"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,
                    "1h":3600,"2h":7200,"4h":14400,"1d":86400,"1w":604800}


def _valid_timeframe_snapshot(item):
    if not isinstance(item,dict): return False
    frame=str(item.get("timeframe", ""))
    interval=_TIMEFRAME_SECONDS.get(frame)
    direction=str(item.get("direction", "")).upper()
    if interval is None or direction not in ("UP","DOWN","LONG","SHORT","NEUTRAL"): return False
    try:
        timestamp=datetime.fromisoformat(str(item.get("last_completed_at","")).replace("Z","+00:00"))
        if timestamp.tzinfo is None: timestamp=timestamp.replace(tzinfo=timezone.utc)
        age=(datetime.now(timezone.utc)-timestamp.astimezone(timezone.utc)).total_seconds()
    except (TypeError,ValueError,OverflowError):
        return False
    return 0 <= age <= max(120,interval*2)


def _paper_positions(ctx):
    positions=ctx.get("positions")
    if not isinstance(positions,list): return _blocked("paper position ledger required",["positions"])
    active=[x for x in positions if isinstance(x,dict) and x.get("status")=="OPEN"]
    return _ready({"active_count":len(active),"symbols":sorted({str(x.get("symbol","")) for x in active}),
                   "trading_mode":"simulation"},"read-only paper-ledger inspection; no order submission")


def _system_health(ctx):
    health=ctx.get("system_health")
    if not isinstance(health,dict): return _blocked("runtime health snapshot required",["system_health"])
    return _ready({"services":health,"degraded":any(str(v).lower() not in ("ok","healthy","up") for v in health.values())},
                  "read-only infrastructure health snapshot")




def _ml_dataset(ctx, horizon: int = 3):
    rows, err = _base(ctx, 140)
    if err: return None, err
    samples=[]
    start=55
    for i in range(start, len(rows)-horizon):
        hist=rows[:i+1]
        closes=[x["close"] for x in hist]
        current=hist[-1]
        vol_base=mean(x["volume"] for x in hist[-21:-1]) if len(hist)>=21 else 0
        atr=_atr(hist[-30:])
        rsi=_rsi(closes[-60:])
        e20=_ema(closes[-50:],20); e50=_ema(closes[-60:],50)
        span=current["high"]-current["low"]
        features=[
            closes[-1]/closes[-2]-1 if closes[-2] else 0,
            closes[-1]/closes[-4]-1 if closes[-4] else 0,
            closes[-1]/closes[-6]-1 if closes[-6] else 0,
            (current["close"]-current["open"])/current["close"],
            (current["close"]-current["low"])/span if span else 0.5,
            current["volume"]/vol_base if vol_base>0 else 1.0,
            atr/current["close"] if atr else 0.0,
            (rsi/100.0) if rsi is not None else 0.5,
            ((e20/e50)-1) if e20 and e50 else 0.0,
        ]
        future=rows[i+horizon]["close"]
        label=1 if future>current["close"] else 0
        samples.append((features,label))
    if len(samples)<60:
        return None,_blocked("too_few_chronological_training_samples",["at_least_60_labeled_samples"])
    return samples,None


def _live_market_features(ctx):
    """Build inference features from the latest available completed candle."""
    rows,err=_base(ctx,60)
    if err:return None,err
    closes=[x["close"] for x in rows]
    current=rows[-1]
    vol_base=mean(x["volume"] for x in rows[-21:-1]) if len(rows)>=21 else 0
    atr=_atr(rows[-30:])
    rsi=_rsi(closes[-60:])
    e20=_ema(closes[-50:],20);e50=_ema(closes[-60:],50)
    span=current["high"]-current["low"]
    return [
        closes[-1]/closes[-2]-1 if closes[-2] else 0,
        closes[-1]/closes[-4]-1 if closes[-4] else 0,
        closes[-1]/closes[-6]-1 if closes[-6] else 0,
        (current["close"]-current["open"])/current["close"],
        (current["close"]-current["low"])/span if span else 0.5,
        current["volume"]/vol_base if vol_base>0 else 1.0,
        atr/current["close"] if atr else 0.0,
        (rsi/100.0) if rsi is not None else 0.5,
        ((e20/e50)-1) if e20 and e50 else 0.0,
    ],None


def _standardize(train, test):
    width=len(train[0][0])
    means=[mean(row[0][j] for row in train) for j in range(width)]
    scales=[]
    for j in range(width):
        sd=pstdev(row[0][j] for row in train)
        scales.append(sd if sd>1e-12 else 1.0)
    def transform(rows):
        return [([(row[0][j]-means[j])/scales[j] for j in range(width)],row[1]) for row in rows]
    return transform(train),transform(test),means,scales


def _sigmoid(x):
    x=max(-35.0,min(35.0,x))
    return 1.0/(1.0+exp(-x))


def _logistic_model(ctx):
    persisted = predict_direction_model(ctx)
    if persisted is not None:
        return persisted
    dataset,err=_ml_dataset(ctx)
    if err: return err
    split=max(40,int(len(dataset)*0.8))
    train_raw,test_raw=dataset[:max(40,split-3)],dataset[split:]
    train,test,means,scales=_standardize(train_raw,test_raw)
    width=len(train[0][0]); weights=[0.0]*width; bias=0.0
    lr=0.04; l2=0.015; epochs=260
    for _ in range(epochs):
        grad=[0.0]*width; gb=0.0
        for features,label in train:
            p=_sigmoid(sum(w*x for w,x in zip(weights,features))+bias)
            error=p-label
            for j,x in enumerate(features): grad[j]+=error*x
            gb+=error
        n=len(train)
        weights=[weights[j]-lr*(grad[j]/n+l2*weights[j]) for j in range(width)]
        bias-=lr*gb/n
    probs=[_sigmoid(sum(w*x for w,x in zip(weights,features))+bias) for features,_ in test]
    labels=[label for _,label in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(probs,labels))/len(labels) if labels else None
    brier=mean((p-y)**2 for p,y in zip(probs,labels)) if labels else None
    latest_features,feature_error=_live_market_features(ctx)
    if feature_error:return feature_error
    normalized=[(latest_features[j]-means[j])/scales[j] for j in range(width)]
    probability=_sigmoid(sum(w*x for w,x in zip(weights,normalized))+bias)
    names=["return_1","return_3","return_5","body_pct","close_location","volume_ratio","atr_pct","rsi_scaled","ema_gap"]
    explanation=sorted([{"feature":names[j],"coefficient":round(weights[j],6),
                         "standardized_contribution":round(weights[j]*normalized[j],6)}
                        for j in range(width)],key=lambda x:abs(x["standardized_contribution"]),reverse=True)
    return _ready({"model":"regularized_logistic_regression","horizon_bars":3,
                   "training_samples":len(train),"holdout_samples":len(test),
                   "chronological_holdout_accuracy_pct":round(accuracy*100,2) if accuracy is not None else None,
                   "holdout_brier_score":round(brier,5) if brier is not None else None,
                   "research_probability_up":round(probability,5),
                   "feature_contributions":explanation[:5],
                   "warning":"Small-sample research model; accuracy is not evidence of future edge and probability is not independently calibrated."},
                  "pure-Python logistic regression; chronological 80/20 split, standardized on training data only")


def _tree_gini(labels):
    if not labels: return 0.0
    p=sum(labels)/len(labels)
    return 2*p*(1-p)


def _build_tree(rows, depth, rng):
    labels=[x[1] for x in rows]
    majority=1 if sum(labels)>=len(labels)/2 else 0
    if depth<=0 or len(set(labels))<=1 or len(rows)<12:
        return {"leaf":majority}
    feature_count=len(rows[0][0])
    candidates=rng.sample(range(feature_count),max(1,int(sqrt(feature_count))))
    best=None
    parent=_tree_gini(labels)
    for feature in candidates:
        values=sorted(x[0][feature] for x in rows)
        for q in (0.2,0.4,0.6,0.8):
            threshold=values[min(len(values)-1,int(q*(len(values)-1)))]
            left=[x for x in rows if x[0][feature]<=threshold]
            right=[x for x in rows if x[0][feature]>threshold]
            if len(left)<4 or len(right)<4: continue
            impurity=(len(left)*_tree_gini([x[1] for x in left])+len(right)*_tree_gini([x[1] for x in right]))/len(rows)
            gain=parent-impurity
            if best is None or gain>best[0]: best=(gain,feature,threshold,left,right)
    if best is None or best[0]<=0:
        return {"leaf":majority}
    _,feature,threshold,left,right=best
    return {"feature":feature,"threshold":threshold,
            "left":_build_tree(left,depth-1,rng),"right":_build_tree(right,depth-1,rng)}


def _tree_predict(tree,features):
    node=tree
    while "leaf" not in node:
        node=node["left"] if features[node["feature"]]<=node["threshold"] else node["right"]
    return node["leaf"]


def _random_forest(ctx):
    dataset,err=_ml_dataset(ctx)
    if err: return err
    split=max(40,int(len(dataset)*0.8))
    train,test,_,_=_standardize(dataset[:max(40,split-3)],dataset[split:])
    rng=random.Random(20261127)
    trees=[]
    for i in range(21):
        boot=[train[rng.randrange(len(train))] for _ in range(len(train))]
        trees.append(_build_tree(boot,3,rng))
    predictions=[sum(_tree_predict(tree,features) for tree in trees)/len(trees) for features,_ in test]
    labels=[label for _,label in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(predictions,labels))/len(labels) if labels else None
    latest,feature_error=_live_market_features(ctx)
    if feature_error:return feature_error
    means=[mean(row[0][j] for row in dataset[:split]) for j in range(len(latest))]
    scales=[pstdev(row[0][j] for row in dataset[:split]) or 1.0 for j in range(len(latest))]
    normalized=[(latest[j]-means[j])/scales[j] for j in range(len(latest))]
    probability=sum(_tree_predict(tree,normalized) for tree in trees)/len(trees)
    return _ready({"model":"random_forest_21_shallow_trees","training_samples":len(train),
                   "holdout_samples":len(test),"chronological_holdout_accuracy_pct":round(accuracy*100,2) if accuracy is not None else None,
                   "research_vote_fraction_up":round(probability,5),
                   "warning":"Small deterministic forest for research only; no calibrated probability or live strategy approval."},
                  "pure-Python bootstrap forest, depth 3, randomized feature subsets and chronological holdout")


def _anomaly_detection(ctx):
    rows,err=_base(ctx,45)
    if err:return err
    current=rows[-1]; previous=rows[-31:-1]
    values={
      "return_pct":(current["close"]/rows[-2]["close"]-1)*100 if rows[-2]["close"] else 0,
      "volume":current["volume"],
      "range_pct":(current["high"]-current["low"])/current["close"]*100,
    }
    histories={
      "return_pct":[(x["close"]/previous[i-1]["close"]-1)*100 for i,x in enumerate(previous) if i>0 and previous[i-1]["close"]>0],
      "volume":[x["volume"] for x in previous],
      "range_pct":[(x["high"]-x["low"])/x["close"]*100 for x in previous if x["close"]>0],
    }
    zscores={}
    for key,value in values.items():
        hist=histories[key]; sd=pstdev(hist) if len(hist)>1 else 0
        zscores[key]=round((value-mean(hist))/sd,4) if sd else 0
    return _ready({"observations":values,"z_scores":zscores,
                   "anomaly_flags":[k for k,v in zscores.items() if abs(v)>=2.5]},
                  "30-bar rolling z-score of return, volume and candle range")


def _clustering(ctx):
    rows,err=_base(ctx,60)
    if err:return err
    samples=[]
    for i in range(20,len(rows)):
        window=rows[i-20:i]
        close=window[-1]["close"]
        ret=close/window[0]["close"]-1 if window[0]["close"] else 0
        vol=pstdev([x["close"]/window[j-1]["close"]-1 for j,x in enumerate(window) if j>0 and window[j-1]["close"]>0])
        vr=window[-1]["volume"]/(mean(x["volume"] for x in window[:-1]) or 1)
        samples.append([ret,vol,vr])
    means=[mean(x[j] for x in samples) for j in range(3)]
    scales=[pstdev(x[j] for x in samples) or 1 for j in range(3)]
    data=[[(x[j]-means[j])/scales[j] for j in range(3)] for x in samples]
    centers=[data[0],data[len(data)//2],data[-1]]
    labels=[0]*len(data)
    for _ in range(30):
        new=[]
        for row in data:
            distances=[sum((row[j]-center[j])**2 for j in range(3)) for center in centers]
            new.append(min(range(3),key=lambda k:distances[k]))
        updated=[]
        for k in range(3):
            group=[data[i] for i,label in enumerate(new) if label==k]
            updated.append([mean(x[j] for x in group) for j in range(3)] if group else centers[k])
        if new==labels and updated==centers: break
        labels,centers=new,updated
    return _ready({"clusters":3,"latest_cluster":labels[-1],
                   "cluster_sizes":[labels.count(k) for k in range(3)],
                   "features":["20-bar_return","20-bar_volatility","last_volume_ratio"]},
                  "deterministic three-cluster k-means on standardized rolling market features")


def _forecast(ctx):
    rows,err=_base(ctx,40)
    if err:return err
    closes=[x["close"] for x in rows[-30:]]
    returns=[closes[i]/closes[i-1]-1 for i in range(1,len(closes)) if closes[i-1]>0]
    drift=mean(returns) if returns else 0
    dispersion=pstdev(returns) if len(returns)>1 else 0
    last=closes[-1]
    return _ready({"horizon_bars":3,"drift_per_bar_pct":drift*100,
                   "naive_projection":last*((1+drift)**3),
                   "historical_return_dispersion_pct":dispersion*100},
                  "rolling mean-return extrapolation; scenario estimate, not calibrated forecast")


def _empirical_probability(ctx):
    dataset,err=_ml_dataset(ctx)
    if err:return err
    labels=[label for _,label in dataset[:-1]]
    probability=sum(labels)/len(labels) if labels else None
    return _ready({"historical_up_frequency":round(probability,5) if probability is not None else None,
                   "sample_count":len(labels),"horizon_bars":3},
                  "empirical historical base rate; not conditional or calibrated for the current setup")


def _ai_analyst(ctx):
    trend=_trend(ctx); comp=_compression(ctx); volume=_volume(ctx); acc=_accumulation(ctx)
    parts=[x for x in (trend,comp,volume,acc) if x.get("status")=="computed"]
    if not parts:return _blocked("insufficient technical evidence",["trend","compression","volume","accumulation"])
    direction=trend["value"]["direction"] if trend.get("status")=="computed" else "UNKNOWN"
    notes=[]
    if comp.get("status")=="computed" and comp["value"]["compressed"]:notes.append("السوق في نطاق منضغط")
    if acc.get("status")=="computed" and acc["value"]["possible_absorption"]:notes.append("يوجد ضغط شراء محتمل مع نطاق محدود")
    if volume.get("status")=="computed" and volume["value"]["anomaly"]:notes.append("الحجم شاذ مقارنة بالعينة السابقة")
    return _ready({"directional_context":direction,"observations":notes,
                   "evidence_modules":len(parts),"analyst_type":"deterministic_explainable"},
                  "rule-based synthesis of independent market features; not a generative model")


def _ensemble(ctx):
    logistic=_logistic_model(ctx); forest=_random_forest(ctx); trend=_trend(ctx)
    evidence=[]
    for model in (logistic,forest):
        if model.get("status")=="computed":
            value=model["value"].get("research_probability_up",model["value"].get("research_vote_fraction_up"))
            evidence.append(value)
    if not evidence:return _blocked("no trained research model available",["historical_training_window"])
    p=mean(evidence)
    trend_up=trend.get("status")=="computed" and trend["value"]["direction"]=="UP"
    return _ready({"ensemble_research_score_up":round(p,5),"models_used":len(evidence),
                   "trend_agreement":trend_up},
                  "unweighted ensemble of in-session research models; not probability-calibrated or trade-authorizing")


def _explain_model(ctx):
    model=_logistic_model(ctx)
    if model.get("status")!="computed":return model
    return _ready({"top_feature_contributions":model["value"]["feature_contributions"],
                   "holdout_accuracy_pct":model["value"]["chronological_holdout_accuracy_pct"],
                   "model":"regularized_logistic_regression"},
                  "feature attribution from standardized linear coefficients; correlational, not causal")




def _trend_exhaustion(ctx):
    rows,err=_base(ctx,35)
    if err:return err
    closes=[x["close"] for x in rows]
    recent=(closes[-1]/closes[-6]-1)*100 if closes[-6] else 0
    prior=(closes[-6]/closes[-11]-1)*100 if closes[-11] else 0
    rsi=_rsi(closes)
    slowing=abs(recent)<abs(prior)
    stretched=(rsi is not None and (rsi>=72 or rsi<=28))
    return _ready({"recent_5bar_return_pct":recent,"prior_5bar_return_pct":prior,
                   "momentum_slowing":slowing,"rsi14":rsi,
                   "exhaustion_candidate":bool(slowing and stretched)},
                  "two adjacent five-bar returns and RSI extreme; candidate only")


def _smc(ctx):
    structure=_market_structure(ctx); sweep=_sweep(ctx); blocks=_order_block(ctx); gaps=_fvg(ctx)
    unavailable = [name for name, result in (
        ("market_structure", structure), ("liquidity_sweep", sweep),
        ("order_block", blocks), ("fair_value_gap", gaps),
    ) if result.get("status") != "computed"]
    if unavailable:
        return _blocked("required price-action components did not pass", unavailable)
    return _ready({"structure":structure,"liquidity_sweep":sweep,
                   "order_block_proxy":blocks,"fair_value_gaps":gaps},
                  "transparent price-action components; no claim of identifying institutional orders")


def _regime_detector(ctx):
    rows,err=_base(ctx,60)
    if err:return err
    trend=_trend(ctx); comp=_compression(ctx); atr=_atr(rows); price=rows[-1]["close"]
    atr_pct=atr/price*100 if atr and price else 0
    compressed=comp.get("status")=="computed" and comp["value"]["compressed"]
    direction=trend.get("value",{}).get("direction","RANGE")
    regime="HIGH_VOLATILITY" if atr_pct>=2.0 else "LOW_VOLATILITY_RANGE" if compressed else "TRENDING" if direction in ("UP","DOWN") else "RANGE"
    return _ready({"regime":regime,"trend":direction,"atr_pct":round(atr_pct,4),"compressed":compressed},
                  "EMA trend, ATR percentage and rolling range compression; heuristic regime labels")


def _derivative_divergence(ctx):
    deriv=ctx.get("derivatives")
    rows,err=_base(ctx,10)
    if err:return err
    if not isinstance(deriv,dict) or deriv.get("open_interest_change_pct") is None:
        return _blocked("open-interest change and funding history required",["derivatives.open_interest_change_pct","derivatives.funding_rate"])
    price_change=(rows[-1]["close"]/rows[-6]["close"]-1)*100 if rows[-6]["close"] else 0
    oi_change=_num(deriv.get("open_interest_change_pct"))
    divergence=(price_change>0 and oi_change<0) or (price_change<0 and oi_change>0)
    return _ready({"price_change_5_pct":price_change,"open_interest_change_pct":oi_change,
                   "divergence_candidate":divergence,"funding_rate":deriv.get("funding_rate")},
                  "price-return versus provider-reported open-interest change")


def _confidence(ctx):
    evidence=ctx.get("evidence_scores")
    if not isinstance(evidence,dict) or not evidence:return _blocked("independent evidence scores required",["evidence_scores"])
    values=[_clamp(_num(v)) for v in evidence.values() if v is not None]
    if not values:return _blocked("no valid evidence scores",["numeric evidence_scores"])
    coverage=len(values)/max(1,len(evidence))
    score=mean(values)
    level="HIGH_CONFLUENCE" if score>=80 and coverage>=0.8 else "MODERATE_CONFLUENCE" if score>=60 else "LOW_CONFLUENCE"
    return _ready({"confluence_score":round(score,2),"evidence_coverage_pct":round(coverage*100,2),
                   "level":level,"is_probability":False},
                  "mean of independent subsystem scores and evidence coverage; explicitly not probability")


def _entry_precision(ctx):
    rows,err=_base(ctx,30)
    if err:return err
    price=rows[-1]["close"]; atr=_atr(rows) or price*0.01
    vwap_result=_vwap(ctx); sr=_support_resistance(ctx)
    vwap=vwap_result.get("value",{}).get("vwap_50") if vwap_result.get("status")=="computed" else None
    support=sr.get("value",{}).get("support_zone") if sr.get("status")=="computed" else None
    resistance=sr.get("value",{}).get("resistance_zone") if sr.get("status")=="computed" else None
    return _ready({"reference_price":price,"atr14":atr,"watch_band":[price-0.25*atr,price+0.25*atr],
                   "distance_to_vwap_pct":round((price/vwap-1)*100,4) if vwap else None,
                   "support_zone":support,"resistance_zone":resistance},
                  "ATR watch band with contextual VWAP and rolling range levels; not an executable limit price")


def _trade_quality(ctx):
    plan=ctx.get("plan") or {}
    entry=_num(plan.get("entry")); stop=_num(plan.get("stop")); target=_num(plan.get("target"))
    evidence=ctx.get("evidence_scores") or {}
    if entry<=0 or stop<=0 or target<=0:return _blocked("entry, stop and target are required",["plan.entry","plan.stop","plan.target"])
    risk=abs(entry-stop); reward=abs(target-entry)
    rr=reward/risk if risk else 0
    score=mean([_clamp(_num(x)) for x in evidence.values()]) if evidence else None
    return _ready({"risk_reward":round(rr,4),"confluence_score":round(score,2) if score is not None else None,
                   "quality":"PASS_REVIEW" if rr>=1.5 and (score is None or score>=65) else "REJECT_OR_REVIEW"},
                  "plan geometry plus supplied evidence scores; no win probability")


def _false_breakout(ctx):
    rows,err=_base(ctx,25)
    if err:return err
    prior=rows[-22:-2]; breakout=rows[-2]; latest=rows[-1]
    if len(prior)<10:return _blocked("insufficient prior range",["at_least_10_prior_bars"])
    hi=max(x["high"] for x in prior); lo=min(x["low"] for x in prior)
    up=breakout["close"]>hi and latest["close"]<=hi
    down=breakout["close"]<lo and latest["close"]>=lo
    return _ready({"failed_upward_breakout":up,"failed_downward_breakout":down,
                   "previous_close":breakout["close"],"latest_close":latest["close"],
                   "prior_range":[lo,hi]},
                  "two most recent completed candles against previous 20-bar range")


def _conflict_resolver(ctx):
    agents=ctx.get("agent_results")
    if not isinstance(agents,list) or not agents:
        aggregate=_agents(ctx)
        if aggregate.get("status")!="computed":return _blocked("agent directions required",["agent_results"])
        agents=aggregate["value"].get("agent_assessments")
    if not isinstance(agents,list) or not agents:return _blocked("agent directions required",["agent_results"])
    directions=[x.get("direction") for x in agents if isinstance(x,dict) and x.get("direction") in ("LONG","SHORT","NEUTRAL")]
    if not directions:return _blocked("no recognized agent direction",["agent_results.*.direction"])
    longs=directions.count("LONG"); shorts=directions.count("SHORT")
    return _ready({"long_votes":longs,"short_votes":shorts,"neutral_votes":directions.count("NEUTRAL"),
                   "conflict":longs>0 and shorts>0,
                   "resolution":"LONG" if longs>shorts else "SHORT" if shorts>longs else "WAIT"},
                  "transparent vote aggregation; disagreements reduce readiness")


def _rank_opportunities(ctx):
    items=ctx.get("opportunity_candidates")
    if not isinstance(items,list) or not items:return _blocked("opportunity candidate list required",["opportunity_candidates"])
    valid=[x for x in items if isinstance(x,dict) and x.get("score") is not None]
    ranked=sorted([{"symbol":str(x.get("symbol","")),"score":_clamp(_num(x.get("score"))),
                    "tier":x.get("tier")} for x in valid],key=lambda x:x["score"],reverse=True)
    return _ready({"ranked":ranked,"count":len(ranked)},"descending sort of supplied, already-calculated candidate scores")


def _entry_readiness(ctx):
    confirmation=ctx.get("entry_confirmation")
    risk=ctx.get("risk_approval")
    if not isinstance(confirmation,dict) or not isinstance(risk,dict):
        return _blocked("entry confirmation and risk approval required",["entry_confirmation","risk_approval"])
    ready=confirmation.get("state")=="CONFIRMED" and risk.get("approved") is True
    return _ready({"ready":ready,"entry_state":confirmation.get("state"),
                   "risk_approved":risk.get("approved") is True,
                   "decision":"PAPER_WATCH_READY" if ready else "WAIT"},
                  "strict conjunction of completed-candle confirmation and risk approval")


def _dynamic_risk(ctx):
    account=ctx.get("account") or {}; plan=ctx.get("plan") or {}
    equity=_num(account.get("equity")); entry=_num(plan.get("entry")); stop=_num(plan.get("stop"))
    if equity<=0 or entry<=0 or stop<=0 or entry==stop:return _blocked("equity, entry and stop required",["account.equity","plan.entry","plan.stop"])
    base=min(2.0,max(0.0,_num(ctx.get("risk_pct"),1.0)))
    vol=_num(ctx.get("volatility_pct"),1.0); dd=_num(ctx.get("drawdown_pct"),0.0)
    multiplier=1.0
    if vol>3:multiplier*=0.5
    elif vol>1.5:multiplier*=0.75
    if dd>=5:multiplier*=0.5
    elif dd>=2:multiplier*=0.75
    effective=base*multiplier
    return _ready({"base_risk_pct":base,"effective_risk_pct":round(effective,4),
                   "risk_amount":equity*effective/100,"quantity":equity*effective/100/abs(entry-stop)},
                  "rule-based volatility and drawdown scaling; capped at 2 percent")


def _portfolio_risk(ctx):
    positions=ctx.get("positions")
    account=ctx.get("account") or {}
    equity=_num(account.get("equity"))
    if not isinstance(positions,list) or equity<=0:return _blocked("paper positions and equity required",["positions","account.equity"])
    opened=[x for x in positions if isinstance(x,dict) and x.get("status")=="OPEN"]
    exposure=sum(abs(_num(x.get("entry"))*_num(x.get("quantity"))) for x in opened)
    return _ready({"gross_exposure":exposure,"equity":equity,"exposure_to_equity_pct":exposure/equity*100,
                   "open_positions":len(opened)},"gross paper notional exposure divided by paper equity")


def _max_drawdown(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list):return _blocked("closed paper trade history required",["closed_trades"])
    equity=_num(ctx.get("starting_balance"),10000.0); peak=equity; max_dd=0.0
    for trade in trades:
        if not isinstance(trade,dict):continue
        equity+=_num(trade.get("pnl"))
        peak=max(peak,equity)
        if peak>0:max_dd=max(max_dd,(peak-equity)/peak*100)
    return _ready({"ending_equity":equity,"peak_equity":peak,"max_drawdown_pct":round(max_dd,4)},
                  "chronological realized paper-trade PnL curve; open PnL excluded")


def _correlation_risk(ctx):
    correlations=ctx.get("correlations")
    if not isinstance(correlations,list):return _blocked("pairwise portfolio correlations required",["correlations"])
    high=[x for x in correlations if isinstance(x,dict) and abs(_num(x.get("correlation")))>=0.8]
    return _ready({"high_correlation_pairs":high,"count":len(high)},
                  "absolute Pearson correlation threshold of 0.8 on supplied aligned return series")


def _leverage_risk(ctx):
    plan=ctx.get("plan") or {}
    side=str(plan.get("side","LONG")).upper()
    entry=_num(plan.get("entry")); stop=_num(plan.get("stop")); leverage=_num(plan.get("leverage"),1)
    mmr=min(0.1,max(0.0,_num(plan.get("maintenance_margin_rate"),0.005)))
    if entry<=0 or stop<=0 or leverage<1 or side not in ("LONG","SHORT"):return _blocked("valid leveraged position plan required",["plan.entry","plan.stop","plan.leverage","plan.side"])
    liquidation=entry*(1-1/leverage+mmr) if side=="LONG" else entry*(1+1/leverage-mmr)
    stop_before_liquidation=stop>liquidation if side=="LONG" else stop<liquidation
    return _ready({"estimated_liquidation_price":liquidation,"stop_before_liquidation":stop_before_liquidation,
                   "leverage":leverage,"maintenance_margin_rate":mmr,
                   "warning":"Isolated-margin approximation; actual exchange liquidation depends on maintenance tiers, fees, funding and account margin."},
                  "simplified isolated-margin estimate only; must not replace exchange risk data")


def _liquidation_protection(ctx):
    risk=_leverage_risk(ctx)
    if risk.get("status")!="computed":return risk
    value=risk["value"]
    return _ready({"protected":value["stop_before_liquidation"],
                   "estimated_liquidation_price":value["estimated_liquidation_price"],
                   "leverage":value["leverage"]},
                  "checks planned stop is on safer side of approximate liquidation level")


def _slippage_estimate(ctx):
    book=ctx.get("orderbook") or {}; side=str(ctx.get("order_side","BUY")).upper(); qty=_num(ctx.get("quantity"))
    levels=book.get("asks" if side=="BUY" else "bids") or []
    if side not in ("BUY","SELL") or qty<=0 or not levels:return _blocked("side, quantity and matching orderbook depth required",["order_side","quantity","orderbook"])
    remaining=qty; cost=0.0; filled=0.0
    for level in levels:
        if len(level)<2:continue
        price=_num(level[0]); size=_num(level[1])
        take=min(remaining,size)
        if price>0 and take>0:cost+=take*price;filled+=take;remaining-=take
        if remaining<=1e-12:break
    if filled<=0:return _blocked("no executable depth",["positive_orderbook_levels"])
    avg=cost/filled; best=_num(levels[0][0])
    return _ready({"requested_quantity":qty,"filled_quantity":filled,"unfilled_quantity":max(0,remaining),
                   "average_fill_estimate":avg,"best_price":best,
                   "slippage_pct":abs(avg/best-1)*100 if best else None},
                  "book-walk estimate from visible levels; excludes hidden liquidity and queue position")


def _fee_calc(ctx):
    notional=_num(ctx.get("notional")); rate=_num(ctx.get("fee_rate"))
    if notional<=0 or rate<0:return _blocked("positive notional and nonnegative fee rate required",["notional","fee_rate"])
    sides=max(1,min(2,int(_num(ctx.get("fee_sides"),2))))
    return _ready({"notional":notional,"fee_rate_per_side":rate,"fee_sides":sides,
                   "estimated_fee":notional*rate*sides},"fee arithmetic using supplied rate; exchange tier must be verified")


def _volatility_stop(ctx):
    rows,err=_base(ctx,20)
    if err:return err
    price=rows[-1]["close"]; atr=_atr(rows); multiplier=min(5.0,max(0.5,_num(ctx.get("atr_multiple"),1.5)))
    plan=ctx.get("plan") or {}
    side=str(ctx.get("side") or plan.get("side") or "").upper()
    if not atr or side not in ("LONG","SHORT"):return _blocked("ATR and explicit position side required",["atr14","side"])
    stop=price-multiplier*atr if side=="LONG" else price+multiplier*atr
    return _ready({"reference_price":price,"atr14":atr,"atr_multiple":multiplier,"stop_reference":stop},
                  "ATR-based volatility stop reference; not exchange order")


def _breakeven(ctx):
    entry=_num(ctx.get("entry")); rate=_num(ctx.get("fee_rate")); side=str(ctx.get("side","LONG")).upper()
    if entry<=0 or rate<0 or side not in ("LONG","SHORT"):return _blocked("entry, fee rate and side required",["entry","fee_rate","side"])
    cost=entry*(1+rate)/(1-rate) if side=="LONG" and rate<1 else entry
    cost=entry*(1-rate)/(1+rate) if side=="SHORT" else cost
    return _ready({"gross_fee_adjusted_breakeven":cost,"entry":entry,"side":side},
                  "two-sided proportional fee break-even estimate; excludes funding and slippage")


def _trailing_stop(ctx):
    side=str(ctx.get("side","LONG")).upper()
    high=_num(ctx.get("highest_price")); low=_num(ctx.get("lowest_price")); atr=_num(ctx.get("atr"))
    multiple=min(5.0,max(0.5,_num(ctx.get("atr_multiple"),2.0)))
    if side=="LONG" and high>0 and atr>0:stop=high-multiple*atr
    elif side=="SHORT" and low>0 and atr>0:stop=low+multiple*atr
    else:return _blocked("side, favorable extreme and ATR required",["side","highest_price_or_lowest_price","atr"])
    return _ready({"trailing_stop_reference":stop,"side":side,"atr_multiple":multiple},
                  "ATR trailing-stop reference; does not modify a position")


def _daily_limit(ctx):
    equity=_num((ctx.get("account") or {}).get("equity")); pnl=_num(ctx.get("daily_pnl"))
    limit=min(10.0,max(0.1,_num(ctx.get("daily_loss_limit_pct"),3.0)))
    if equity<=0:return _blocked("paper equity required",["account.equity"])
    loss_pct=max(0,-pnl)/equity*100
    return _ready({"daily_pnl":pnl,"daily_loss_pct":round(loss_pct,4),
                   "limit_pct":limit,"limit_breached":loss_pct>=limit},
                  "realized daily PnL against configured paper-equity loss limit")


def _circuit_breaker(ctx):
    daily=_daily_limit(ctx)
    …4411 tokens truncated…dered": True, "first_timestamp": unique[0]["time"],
        "last_timestamp": unique[-1]["time"],
        "timestamp_policy": "source_epoch_preserved_and_sorted",
        "normalized_candles": unique,
    }, "finite OHLCV validation, millisecond epoch ordering, duplicate removal, and normalized output")


def _liquidity(ctx):
    book = ctx.get("orderbook")
    if not isinstance(book, dict):
        return _blocked("live order-book snapshot required", ["orderbook.bids", "orderbook.asks"])
    bids, asks = book.get("bids") or [], book.get("asks") or []
    try:
        valid_bids = [(float(x[0]), float(x[1])) for x in bids if len(x) >= 2 and float(x[0]) > 0 and float(x[1]) > 0]
        valid_asks = [(float(x[0]), float(x[1])) for x in asks if len(x) >= 2 and float(x[0]) > 0 and float(x[1]) > 0]
    except (TypeError, ValueError, IndexError, OverflowError):
        return _blocked("order-book levels are malformed", ["positive_price_size_levels"])
    if not valid_bids or not valid_asks:
        return _blocked("both bid and ask sides are required", ["nonempty_bids", "nonempty_asks"])
    best_bid = max(x[0] for x in valid_bids)
    best_ask = min(x[0] for x in valid_asks)
    if best_ask <= best_bid:
        return _blocked("crossed or locked order book; spread is not trustworthy", ["uncrossed_orderbook"])
    bid_depth = sum(p*q for p,q in valid_bids[:20])
    ask_depth = sum(p*q for p,q in valid_asks[:20])
    mid = (best_bid + best_ask) / 2
    return _ready({
        "best_bid": best_bid, "best_ask": best_ask, "mid_price": mid,
        "spread_abs": best_ask-best_bid, "spread_bps": (best_ask-best_bid)/mid*10000,
        "bid_depth_notional": bid_depth, "ask_depth_notional": ask_depth,
        "total_depth_notional": bid_depth+ask_depth,
        "depth_imbalance": (bid_depth-ask_depth)/(bid_depth+ask_depth) if bid_depth+ask_depth else 0,
        "levels_used": min(20, len(valid_bids))+min(20, len(valid_asks)),
        "provider": book.get("provider"),
    }, "top-20 validated order-book depth and quoted spread; displayed liquidity can be cancelled")


def _volatility(ctx):
    rows, err = _base(ctx, 20)
    if err:
        return err
    closes = [x["close"] for x in rows]
    atr = _atr(rows, 14)
    returns = [(closes[i]/closes[i-1]-1) for i in range(1, len(closes)) if closes[i-1] > 0]
    window = returns[-20:]
    realized = pstdev(window) * sqrt( periods_per_year := 365*24*4 ) * 100 if len(window) >= 2 and str(ctx.get("interval")) == "15m" else (pstdev(window)*100 if len(window)>=2 else None)
    price = closes[-1]
    return _ready({
        "atr14": atr, "atr_pct": atr/price*100 if atr is not None and price else None,
        "realized_return_volatility_pct": realized,
        "return_observations": len(window), "interval": ctx.get("interval"),
        "volatility_state": "HIGH" if atr is not None and atr/price >= 0.04 else "LOW" if atr is not None and atr/price <= 0.01 else "NORMAL" if atr is not None else "UNKNOWN",
    }, "Wilder ATR14 and standard deviation of completed-bar returns; annualization only for 15m crypto bars")


def _data_quality(ctx):
    raw=_raw_candle_records(ctx)
    if not isinstance(raw,list):return _blocked("raw candles are required for quality checks",["candles"])
    if len(raw)<20:return _blocked("at least 20 raw candles are required for quality checks",["20_raw_candles"])
    times=[]
    invalid_timestamp_rows=0
    invalid_ohlc=0
    for row in raw:
        if not isinstance(row,dict):
            invalid_timestamp_rows+=1;invalid_ohlc+=1
            continue
        timestamp=_num(row.get("time"),float("nan"))
        if not isfinite(timestamp) or timestamp<0 or not timestamp.is_integer():
            invalid_timestamp_rows+=1
        else:
            times.append(int(timestamp))
        try:
            values=[float(row[key]) for key in ("open","high","low","close","volume")]
            op,high,low,close,volume=values
            valid=all(isfinite(value) for value in values) and min(op,high,low,close)>0 and volume>=0
            valid=valid and high>=max(op,close,low) and low<=min(op,close,high)
        except (KeyError,TypeError,ValueError,OverflowError):
            valid=False
        if not valid:invalid_ohlc+=1
    duplicate_count=len(times)-len(set(times))
    ascending=all(times[i]>=times[i-1] for i in range(1,len(times)))
    descending=all(times[i]<=times[i-1] for i in range(1,len(times)))
    ordered=ascending or descending
    source_order="ascending" if ascending else "descending" if descending else "mixed"
    gaps=sum(1 for i in range(1,len(times)) if times[i]==times[i-1])
    return _ready({"candles":len(raw),"timestamps_present":len(times),
                   "duplicate_timestamps":duplicate_count,"timestamps_ordered":ordered,
                   "source_timestamp_order":source_order,"duplicate_timestamp_pairs":gaps,
                   "invalid_timestamp_rows":invalid_timestamp_rows,
                   "invalid_ohlc_rows":invalid_ohlc,
                   "quality_passed":duplicate_count==0 and ordered and invalid_timestamp_rows==0 and invalid_ohlc==0},
                  "raw-row schema, finite OHLCV, price/volume bounds, unique timestamps and monotonic provider ordering checks")


def _funding_rate(ctx):
    data=ctx.get("derivatives") or {}
    rate=data.get("funding_rate")
    if rate is None:return _blocked("verified funding-rate snapshot required",["derivatives.funding_rate"])
    value=_num(rate,float("nan"))
    if not isfinite(value):return _blocked("funding rate is not finite",["derivatives.funding_rate"])
    return _ready({"funding_rate":value,"funding_rate_pct":value*100,
                   "provider":data.get("provider"),"data_quality":"provider_snapshot"},
                  "read-only provider funding-rate snapshot; not a predicted next rate")


def _open_interest(ctx):
    data=ctx.get("derivatives") or {}
    oi=data.get("open_interest")
    if oi is None:return _blocked("verified open-interest snapshot required",["derivatives.open_interest"])
    value=_num(oi,-1)
    if value<0:return _blocked("open interest is invalid",["derivatives.open_interest"])
    return _ready({"open_interest":value,"change_pct":data.get("open_interest_change_pct"),
                   "provider":data.get("provider"),"data_quality":"provider_snapshot"},
                  "read-only provider open-interest snapshot; contract unit follows venue")


def _spot_opportunity(ctx):
    if str(ctx.get("category","spot")).lower()!="spot":
        return _blocked("spot category required",["category=spot"])
    return _opportunity(ctx)


def _futures_opportunity(ctx):
    if str(ctx.get("category","")).lower()!="linear":
        return _blocked("USDT linear futures candles are required",["category=linear"])
    result=_opportunity(ctx)
    if result.get("status")!="computed":return result
    deriv=_derivatives(ctx)
    return _ready({**result["value"],
                   "derivatives_context":deriv.get("value") if deriv.get("status")=="computed" else None,
                   "derivatives_status":deriv.get("status")},
                  "futures opportunity confluence over completed linear candles plus provider derivatives context")


def _trade_journal(ctx):
    trades=ctx.get("positions")
    if not isinstance(trades,list):return _blocked("paper trade ledger required",["positions"])
    closed=[x for x in trades if isinstance(x,dict) and x.get("status")=="CLOSED"]
    opened=[x for x in trades if isinstance(x,dict) and x.get("status")=="OPEN"]
    pnls=[_num(x.get("pnl")) for x in closed]
    return _ready({"total_trades":len(trades),"open_trades":len(opened),"closed_trades":len(closed),
                   "realized_net_pnl":sum(pnls),
                   "win_rate_pct":sum(1 for x in pnls if x>0)/len(pnls)*100 if pnls else None,
                   "journal_source":"paper_ledger"},
                  "read-only journal aggregation over the persisted paper ledger")

# Each catalogue engine is routable. Similar engines share audited mathematical primitives,
# while model- and provider-dependent engines remain explicitly blocked when inputs are absent.


def _bs_price(spot, strike, years, rate, volatility, is_call):
    if years<=0 or volatility<=0 or spot<=0 or strike<=0:return max(spot-strike,0) if is_call else max(strike-spot,0)
    root=sqrt(years);d1=(__import__("math").log(spot/strike)+(rate+0.5*volatility*volatility)*years)/(volatility*root)
    d2=d1-volatility*root
    normal=NormalDist()
    disc=exp(-rate*years)
    if is_call:return spot*normal.cdf(d1)-strike*disc*normal.cdf(d2)
    return strike*disc*normal.cdf(-d2)-spot*normal.cdf(-d1)


def _implied_volatility(market_price,spot,strike,years,rate,is_call):
    if market_price<=0 or years<=0 or spot<=0 or strike<=0:return None
    intrinsic=max(spot-strike,0) if is_call else max(strike-spot,0)
    if market_price<intrinsic:return None
    low,high=0.0001,5.0
    if _bs_price(spot,strike,years,rate,high,is_call)<market_price:return None
    for _ in range(80):
        mid=(low+high)/2
        value=_bs_price(spot,strike,years,rate,mid,is_call)
        if value>market_price:high=mid
        else:low=mid
    return (low+high)/2


def _options_chain(ctx):
    chain=ctx.get("options_chain")
    spot=_num(ctx.get("underlying_price"))
    if not isinstance(chain,list) or not chain:return None,_blocked("verified option chain snapshot required",["options_chain"])
    if spot<=0:return None,_blocked("underlying mark required",["underlying_price"])
    output=[];gross_gamma=0.0;signed_gamma=0.0;has_sign=True
    for contract in chain:
        if not isinstance(contract,dict):continue
        strike=_num(contract.get("strike"));days=_num(contract.get("days_to_expiry"))
        kind=str(contract.get("type","CALL")).upper()
        if strike<=0 or days<=0 or kind not in ("CALL","PUT"):continue
        years=days/365.0;rate=_num(contract.get("risk_free_rate"),0.0)
        iv=_num(contract.get("implied_volatility"))
        mid=_num(contract.get("mark_price"))
        if mid<=0:
            bid=_num(contract.get("bid"));ask=_num(contract.get("ask"))
            mid=(bid+ask)/2 if bid>0 and ask>=bid else 0
        if iv<=0 and mid>0:
            estimate=_implied_volatility(mid,spot,strike,years,rate,kind=="CALL")
            iv=estimate or 0
        if iv<=0:continue
        root=sqrt(years);d1=(__import__("math").log(spot/strike)+(rate+0.5*iv*iv)*years)/(iv*root)
        pdf=exp(-0.5*d1*d1)/sqrt(2*__import__("math").pi)
        delta=NormalDist().cdf(d1) if kind=="CALL" else NormalDist().cdf(d1)-1
        gamma=pdf/(spot*iv*root)
        vega=spot*pdf*root/100
        oi=_num(contract.get("open_interest"));mult=_num(contract.get("contract_multiplier"),1.0)
        exposure=gamma*oi*mult*spot*spot*0.01
        dealer_sign=contract.get("dealer_position_sign")
        if dealer_sign not in (-1,1):has_sign=False
        else:signed_gamma+=exposure*dealer_sign
        gross_gamma+=exposure
        output.append({"symbol":contract.get("symbol"),"type":kind,"strike":strike,
                       "days_to_expiry":days,"implied_volatility":iv,"delta":delta,
                       "gamma":gamma,"vega_per_1vol_point":vega,
                       "open_interest":oi,"gamma_exposure_per_1pct_move":exposure})
    if not output:return None,_blocked("no valid option contracts with implied volatility",["valid_iv_or_bid_ask","strike","expiry","contract_type"])
    return {"contracts":output,"count":len(output),"gross_gamma_exposure_per_1pct_move":gross_gamma,
            "net_gamma_exposure_per_1pct_move":signed_gamma if has_sign else None,
            "net_gamma_available":has_sign},None


def _options_analytics(ctx):
    summary,err=_options_chain(ctx)
    if err:return err
    return _ready(summary,"Black-Scholes greeks with supplied or bisection-derived implied volatility")


def _implied_volatility_engine(ctx):
    summary,err=_options_chain(ctx)
    if err:return err
    values=[x["implied_volatility"] for x in summary["contracts"]]
    return _ready({"contract_count":len(values),"mean_iv":mean(values),
                   "median_iv":median(values),"min_iv":min(values),"max_iv":max(values),
                   "contracts":summary["contracts"]},
                  "implied volatility supplied by provider or derived from bid/ask midpoint via Black-Scholes")


def _gamma_exposure(ctx):
    summary,err=_options_chain(ctx)
    if err:return err
    return _ready({"gross_gamma_exposure_per_1pct_move":summary["gross_gamma_exposure_per_1pct_move"],
                   "net_gamma_exposure_per_1pct_move":summary["net_gamma_exposure_per_1pct_move"],
                   "net_gamma_available":summary["net_gamma_available"],
                   "contract_count":summary["count"],
                   "warning":"Open interest alone does not identify dealer-side positioning; net GEX is omitted unless dealer_position_sign is supplied."},
                  "Black-Scholes gamma times open interest, multiplier and underlying squared; 1 percent move scaling")


def _liquidation_heatmap(ctx):
    events=ctx.get("liquidations")
    if not isinstance(events,list):return _blocked("normalized liquidation trades required",["liquidations"])
    valid=[x for x in events if isinstance(x,dict) and _num(x.get("price"))>0 and _num(x.get("notional_usdt"))>0]
    if not valid:return _blocked("no valid liquidation price/notional records",["liquidations[].price","liquidations[].notional_usdt"])
    bins=max(5,min(40,int(_num(ctx.get("price_bins"),12))))
    lo=min(_num(x["price"]) for x in valid);hi=max(_num(x["price"]) for x in valid)
    if hi<=lo:
        return _ready({"levels":[{"price":lo,"notional_usdt":sum(_num(x["notional_usdt"]) for x in valid),"events":len(valid)}]},
                      "single-price liquidation aggregation")
    step=(hi-lo)/bins;levels=[{"notional_usdt":0.0,"events":0} for _ in range(bins)]
    for event in valid:
        idx=min(bins-1,max(0,int((_num(event["price"])-lo)/step)))
        levels[idx]["notional_usdt"]+=_num(event["notional_usdt"]);levels[idx]["events"]+=1
    for i,item in enumerate(levels):
        item["price_center"]=lo+(i+0.5)*step
    return _ready({"levels":[x for x in levels if x["events"]],"event_count":len(valid),
                   "total_notional_usdt":sum(x["notional_usdt"] for x in valid),
                   "warning":"Observed liquidation prints only; this is not a prediction of future liquidation levels."},
                  "price-bucket aggregation of supplied executed liquidation events")


def _strategy_optimizer(ctx):
    candidates=ctx.get("strategy_candidates")
    if not isinstance(candidates,list) or not candidates:return _blocked("strategy candidates with validation metrics required",["strategy_candidates"])
    clean=[]
    for item in candidates:
        if not isinstance(item,dict):continue
        trades=int(_num(item.get("validation_trades")))
        ret=_num(item.get("validation_return"));dd=_num(item.get("validation_drawdown"),100)
        if trades<30 or dd>=20:continue
        clean.append({"name":str(item.get("name","unnamed")),"validation_return":ret,
                      "validation_drawdown":dd,"validation_trades":trades,
                      "parameters":item.get("parameters",{})})
    ranked=sorted(clean,key=lambda x:(x["validation_return"],-x["validation_drawdown"]),reverse=True)
    return _ready({"ranked_candidates":ranked,"selected_for_manual_review":ranked[0] if ranked else None,
                   "automatic_deployment":False,"minimum_validation_trades":30,"maximum_drawdown_pct":20},
                  "ranking of externally evaluated validation results; never auto-deploys")


def _parameter_optimizer(ctx):
    grid=ctx.get("parameter_trials")
    if not isinstance(grid,list) or not grid:return _blocked("parameter trial results required",["parameter_trials"])
    valid=[]
    for item in grid:
        if not isinstance(item,dict):continue
        trades=int(_num(item.get("validation_trades")))
        score=_num(item.get("validation_score"),float("-inf"))
        if trades>=30 and isfinite(score):
            valid.append({"parameters":item.get("parameters",{}),"validation_score":score,
                          "validation_trades":trades,"max_drawdown_pct":_num(item.get("max_drawdown_pct"),100)})
    valid.sort(key=lambda x:x["validation_score"],reverse=True)
    return _ready({"best_trial":valid[0] if valid else None,"eligible_trials":len(valid),
                   "trials_received":len(grid),"selection":"validation score with minimum sample guard"},
                  "chooses among completed external parameter trials; does not search or deploy by itself")


def _win_rate(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list):return _blocked("closed trade history required",["closed_trades"])
    pnls=[_num(x.get("pnl")) for x in trades if isinstance(x,dict) and x.get("status","CLOSED")=="CLOSED"]
    return _ready({"trade_count":len(pnls),"wins":sum(x>0 for x in pnls),
                   "losses":sum(x<0 for x in pnls),"breakeven":sum(x==0 for x in pnls),
                   "win_rate_pct":sum(x>0 for x in pnls)/len(pnls)*100 if pnls else None},
                  "realized closed-paper-trade PnL; excludes open positions")


def _profit_factor(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list):return _blocked("closed trade history required",["closed_trades"])
    pnls=[_num(x.get("pnl")) for x in trades if isinstance(x,dict) and x.get("status","CLOSED")=="CLOSED"]
    gross_win=sum(x for x in pnls if x>0);gross_loss=abs(sum(x for x in pnls if x<0))
    return _ready({"gross_profit":gross_win,"gross_loss":gross_loss,
                   "profit_factor":gross_win/gross_loss if gross_loss else None,
                   "trade_count":len(pnls)},"realized paper PnL ratio; undefined when no losses")


def _expectancy(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list):return _blocked("closed trade history required",["closed_trades"])
    pnls=[_num(x.get("pnl")) for x in trades if isinstance(x,dict) and x.get("status","CLOSED")=="CLOSED"]
    if not pnls:return _blocked("no closed trades available",["at_least_1_closed_trade"])
    return _ready({"expectancy_per_trade":mean(pnls),"trade_count":len(pnls),
                   "gross_win_mean":mean([x for x in pnls if x>0]) if any(x>0 for x in pnls) else 0,
                   "gross_loss_mean":mean([x for x in pnls if x<0]) if any(x<0 for x in pnls) else 0},
                  "arithmetic average of realized net paper PnL per closed trade")


def _continuous_learning(ctx):
    baseline=ctx.get("baseline_metrics");recent=ctx.get("recent_metrics")
    labeled=int(_num(ctx.get("new_labeled_samples")))
    drift=_model_drift(ctx)
    if drift.get("status")!="computed":return drift
    threshold=max(30,int(_num(ctx.get("minimum_new_samples"),100)))
    ready=labeled>=threshold or drift["value"]["drift_detected"]
    return _ready({"new_labeled_samples":labeled,"minimum_new_samples":threshold,
                   "drift_detected":drift["value"]["drift_detected"],
                   "retraining_candidate":ready,"automatic_retraining":False,
                   "requires_out_of_sample_validation":True},
                  "retraining readiness gate; no background trainer or autonomous model replacement")


def _trade_recovery(ctx):
    positions=ctx.get("positions")
    if not isinstance(positions,list):return _blocked("paper position ledger required",["positions"])
    findings=[]
    for position in positions:
        if not isinstance(position,dict) or position.get("status")!="OPEN":continue
        issues=[]
        if _num(position.get("entry"))<=0:issues.append("MISSING_OR_INVALID_ENTRY")
        if _num(position.get("quantity"))<=0:issues.append("MISSING_OR_INVALID_QUANTITY")
        if _num(position.get("stop_loss",position.get("stopLoss")))<=0:issues.append("MISSING_STOP")
        if not position.get("id"):issues.append("MISSING_POSITION_ID")
        if issues:findings.append({"symbol":position.get("symbol"),"position_id":position.get("id"),"issues":issues})
    return _ready({"positions_checked":sum(1 for x in positions if isinstance(x,dict) and x.get("status")=="OPEN"),
                   "recovery_findings":findings,"requires_operator_review":bool(findings),
                   "mutated_ledger":False},
                  "read-only paper ledger integrity scan; never fabricates fills or silently repairs state")


def _ai_prediction(ctx):
    logistic=_logistic_model(ctx);forest=_random_forest(ctx);forecast=_forecast(ctx)
    outputs=[]
    if logistic.get("status")=="computed":
        outputs.append({"model":"logistic","up_score":logistic["value"]["research_probability_up"]})
    if forest.get("status")=="computed":
        outputs.append({"model":"forest","up_score":forest["value"]["research_vote_fraction_up"]})
    if not outputs:return _blocked("no model produced a research score",["historical_ohlcv"])
    score=mean(x["up_score"] for x in outputs)
    direction="UP_BIAS" if score>=0.55 else "DOWN_BIAS" if score<=0.45 else "UNCERTAIN"
    return _ready({"directional_bias":direction,"research_score_up":round(score,5),
                   "models":outputs,"naive_forecast":forecast.get("value") if forecast.get("status")=="computed" else None,
                   "probability_calibrated":False},
                  "ensemble of current-window research estimators; not a production prediction service")


def _scheduler(ctx):
    jobs=ctx.get("scheduled_jobs")
    if not isinstance(jobs,list):return _blocked("scheduler job inventory required",["scheduled_jobs"])
    valid=[]
    for job in jobs:
        if not isinstance(job,dict):continue
        interval=_num(job.get("interval_seconds"))
        valid.append({"name":str(job.get("name","unnamed")),"enabled":job.get("enabled") is True,
                      "interval_seconds":interval,"valid_interval":interval>=1})
    return _ready({"jobs":valid,"enabled_jobs":sum(x["enabled"] and x["valid_interval"] for x in valid),
                   "scheduler_backend_configured":ctx.get("scheduler_backend_configured") is True},
                  "read-only scheduler inventory; no background scheduler is started by this adapter")


def _component_health(ctx, key):
    value=ctx.get(key)
    if not isinstance(value,dict):return _blocked(f"{key} health snapshot required",[key])
    return _ready({"component":key,"health":value,
                   "healthy":str(value.get("status","")).lower() in ("ok","healthy","up")},
                  f"read-only {key} health metadata")


def _cache(ctx):return _component_health(ctx,"cache")
def _database(ctx):return _component_health(ctx,"database")
def _websocket(ctx):return _component_health(ctx,"websocket")


def _error_recovery(ctx):
    failures=ctx.get("recent_failures")
    if not isinstance(failures,list):return _blocked("recent service failure records required",["recent_failures"])
    output=[]
    for failure in failures:
        if not isinstance(failure,dict):continue
        code=str(failure.get("error_code","UNKNOWN"))
        retryable=code in ("TIMEOUT","RATE_LIMIT","CONNECTION_RESET","HTTP_5XX")
        output.append({"service":failure.get("service"),"error_code":code,"retryable":retryable,
                       "recommended_action":"BOUNDED_RETRY_WITH_BACKOFF" if retryable else "MANUAL_REVIEW"})
    return _ready({"failures":output,"retryable_count":sum(x["retryable"] for x in output)},
                  "failure classification only; retries are owned by provider client policies")


def _notification(ctx):
    events=ctx.get("notification_events")
    if not isinstance(events,list):return _blocked("notification event records required",["notification_events"])
    messages=[]
    for event in events:
        if not isinstance(event,dict):continue
        kind=str(event.get("type","INFO")).upper()
        if kind not in ("OPPORTUNITY","RISK","TARGET","STOP","SYSTEM"):kind="INFO"
        messages.append({"type":kind,"title":str(event.get("title","QUANT NEXUS"))[:100],
                         "message":str(event.get("message",""))[:500],
                         "dedupe_key":event.get("dedupe_key")})
    return _ready({"notification_intents":messages,"count":len(messages),
                   "delivery_performed":False},
                  "validated notification outbox intents; delivery is handled by configured notification transport")


def _security(ctx):
    policy=ctx.get("security_policy")
    if not isinstance(policy,dict):return _blocked("runtime security policy snapshot required",["security_policy"])
    checks={
      "paper_only":policy.get("live_trading_enabled") is False and policy.get("trading_mode")=="simulation",
      "no_exchange_trade_credentials":policy.get("exchange_trade_credentials_present") is False,
      "https_required":policy.get("https_enabled") is True,
      "secret_redaction":policy.get("secrets_redacted") is True,
      "admin_auth":policy.get("admin_auth_enabled") is True,
    }
    failed=[k for k,v in checks.items() if not v]
    return _ready({"checks":checks,"failed_checks":failed,"secure":not failed},
                  "fail-closed inspection of supplied deployment security flags; does not inspect secret values")



def _deep_learning_mlp(ctx):
    dataset,err=_ml_dataset(ctx)
    if err:return err
    split=max(40,int(len(dataset)*0.8))
    train,test,means,scales=_standardize(dataset[:max(40,split-3)],dataset[split:])
    rng=random.Random(20261127)
    inputs=len(train[0][0]);h1=8;h2=4
    w1=[[rng.gauss(0,0.12) for _ in range(inputs)] for _ in range(h1)]
    b1=[0.0]*h1
    w2=[[rng.gauss(0,0.12) for _ in range(h1)] for _ in range(h2)]
    b2=[0.0]*h2
    w3=[rng.gauss(0,0.12) for _ in range(h2)];b3=0.0
    lr=0.012;l2=0.002
    def forward(x):
        a1=[__import__("math").tanh(sum(w*xv for w,xv in zip(row,x))+b) for row,b in zip(w1,b1)]
        a2=[__import__("math").tanh(sum(w*av for w,av in zip(row,a1))+b) for row,b in zip(w2,b2)]
        return a1,a2,_sigmoid(sum(w*a for w,a in zip(w3,a2))+b3)
    for epoch in range(110):
        order=list(range(len(train)));rng.shuffle(order)
        rate=lr*(1-0.35*epoch/110)
        for idx in order:
            x,y=train[idx];a1,a2,p=forward(x);d3=p-y
            d2=[d3*w3[j]*(1-a2[j]*a2[j]) for j in range(h2)]
            d1=[(sum(d2[k]*w2[k][j] for k in range(h2)))*(1-a1[j]*a1[j]) for j in range(h1)]
            old_w2=[row[:] for row in w2];old_w3=w3[:]
            w3=[w3[j]-rate*(d3*a2[j]+l2*w3[j]) for j in range(h2)];b3-=rate*d3
            for k in range(h2):
                for j in range(h1):w2[k][j]-=rate*(d2[k]*a1[j]+l2*w2[k][j])
                b2[k]-=rate*d2[k]
            for j in range(h1):
                for k in range(inputs):w1[j][k]-=rate*(d1[j]*x[k]+l2*w1[j][k])
                b1[j]-=rate*d1[j]
    predictions=[forward(x)[2] for x,_ in test]
    labels=[y for _,y in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(predictions,labels))/len(labels) if labels else None
    brier=mean((p-y)**2 for p,y in zip(predictions,labels)) if labels else None
    live_features,feature_error=_live_market_features(ctx)
    if feature_error:return feature_error
    latest=[(live_features[j]-means[j])/scales[j] for j in range(inputs)]
    probability=forward(latest)[2]
    return _ready({"model":"two_hidden_layer_mlp","hidden_layers":[h1,h2],
                   "training_samples":len(train),"holdout_samples":len(test),
                   "chronological_holdout_accuracy_pct":round(accuracy*100,2) if accuracy is not None else None,
                   "holdout_brier_score":round(brier,5) if brier is not None else None,
                   "research_score_up":round(probability,5),
                   "warning":"Small MLP trained per request on this OHLCV window; not a persistent production model or calibrated probability."},
                  "pure-Python two-hidden-layer tanh MLP with chronological holdout and train-only normalization")


def _rl_agent(ctx):
    rows,err=_base(ctx,160)
    if err:return err
    fee=max(0.0,_num(ctx.get("simulated_fee_per_side_pct"),0.05))/100
    start=55; transitions=[]
    def state_at(index):
        hist=rows[:index+1];closes=[x["close"] for x in hist]
        fast=_ema(closes[-50:],20);price=closes[-1]
        trend="UP" if fast and price>fast*1.002 else "DOWN" if fast and price<fast*0.998 else "RANGE"
        momentum="POS" if price>closes[-4] else "NEG"
        atr=_atr(hist[-30:]);vol="HIGH" if atr and price and atr/price>0.015 else "LOW"
        return (trend,momentum,vol)
    for i in range(start,len(rows)-1):
        current=rows[i]["close"];future=rows[i+1]["close"]
        if current<=0:continue
        transitions.append((state_at(i),state_at(i+1),(future/current-1)*100))
    if len(transitions)<40:return _blocked("insufficient chronological reinforcement-learning transitions",["at_least_40_transitions"])
    split=max(30,int(len(transitions)*0.8));training=transitions[:max(30,split-1)];testing=transitions[split:]
    actions=("LONG","SHORT","FLAT")
    q={};rng=random.Random(20261127);alpha=0.08;gamma=0.85
    for episode in range(35):
        epsilon=max(0.02,0.25*(1-episode/35))
        previous="FLAT"
        for state,next_state,ret in training:
            values=q.setdefault(state,{action:0.0 for action in actions})
            if rng.random()<epsilon:action=rng.choice(actions)
            else:action=max(actions,key=lambda a:values[a])
            exposure={"LONG":1.0,"SHORT":-1.0,"FLAT":0.0}[action]
            reward=exposure*ret-(fee*100 if action!=previous else 0.0)
            next_values=q.setdefault(next_state,{a:0.0 for a in actions})
            target=reward+gamma*max(next_values.values())
            values[action]+=alpha*(target-values[action])
            previous=action
    total=1.0;benchmark=1.0;rewards=[];action_counts={x:0 for x in actions};previous="FLAT"
    for state,next_state,ret in testing:
        values=q.get(state,{a:0.0 for a in actions})
        action=max(actions,key=lambda a:values[a])
        exposure={"LONG":1.0,"SHORT":-1.0,"FLAT":0.0}[action]
        reward=exposure*ret-(fee*100 if action!=previous else 0.0)
        total*=max(0.000001,1+reward/100);benchmark*=max(0.000001,1+ret/100)
        rewards.append(reward);action_counts[action]+=1;previous=action
    return _ready({"algorithm":"tabular_q_learning","training_transitions":len(training),
                   "holdout_transitions":len(testing),"holdout_return_pct":round((total-1)*100,4),
                   "buy_and_hold_return_pct":round((benchmark-1)*100,4),
                   "mean_reward_per_transition_pct":round(mean(rewards),5) if rewards else None,
                   "holdout_action_counts":action_counts,
                   "warning":"Toy OHLCV simulator with discrete states and simplified fees; not evidence of deployable RL edge."},
                  "chronological Q-learning training on earlier simulated OHLCV transitions and frozen-policy holdout")



def _fit_second_order_tree(features,gradients,hessians,indices,depth=2,l2=1.0,
                           min_child_weight=2.0,gamma=0.05):
    total_g=sum(gradients[i] for i in indices)
    total_h=sum(hessians[i] for i in indices)
    leaf=-total_g/(total_h+l2) if total_h+l2 else 0.0
    if depth<=0 or len(indices)<12 or total_h<2*min_child_weight:
        return {"leaf":leaf}
    width=len(features[0]);best=None
    for feature in range(width):
        ordered=sorted(features[i][feature] for i in indices)
        candidates=[]
        for q in (0.15,0.3,0.45,0.55,0.7,0.85):
            threshold=ordered[min(len(ordered)-1,int(q*(len(ordered)-1)))]
            if not candidates or threshold!=candidates[-1]:candidates.append(threshold)
        for threshold in candidates:
            left=[i for i in indices if features[i][feature]<=threshold]
            right=[i for i in indices if features[i][feature]>threshold]
            if len(left)<4 or len(right)<4:continue
            gl=sum(gradients[i] for i in left);hl=sum(hessians[i] for i in left)
            gr=total_g-gl;hr=total_h-hl
            if hl<min_child_weight or hr<min_child_weight:continue
            gain=0.5*(gl*gl/(hl+l2)+gr*gr/(hr+l2)-total_g*total_g/(total_h+l2))-gamma
            if best is None or gain>best[0]:best=(gain,feature,threshold,left,right)
    if best is None or best[0]<=0:return {"leaf":leaf}
    _,feature,threshold,left,right=best
    return {"feature":feature,"threshold":threshold,
            "left":_fit_second_order_tree(features,gradients,hessians,left,depth-1,l2,min_child_weight,gamma),
            "right":_fit_second_order_tree(features,gradients,hessians,right,depth-1,l2,min_child_weight,gamma)}


def _boost_tree_predict(tree,features):
    node=tree
    while "leaf" not in node:
        node=node["left"] if features[node["feature"]]<=node["threshold"] else node["right"]
    return node["leaf"]


def _xgboost_classifier(ctx):
    dataset,err=_ml_dataset(ctx)
    if err:return err
    split=max(40,int(len(dataset)*0.8))
    train_raw,test_raw=dataset[:max(40,split-3)],dataset[split:]
    train,test,means,scales=_standardize(train_raw,test_raw)
    features=[x[0] for x in train];labels=[x[1] for x in train]
    positive=sum(labels)/len(labels)
    base=max(-3.0,min(3.0,__import__("math").log(max(1e-5,positive)/max(1e-5,1-positive))))
    train_logits=[base]*len(train);trees=[];learning_rate=0.08;rounds=28
    for _ in range(rounds):
        probabilities=[_sigmoid(x) for x in train_logits]
        gradients=[p-y for p,y in zip(probabilities,labels)]
        hessians=[max(1e-5,p*(1-p)) for p in probabilities]
        tree=_fit_second_order_tree(features,gradients,hessians,list(range(len(train))),depth=2)
        trees.append(tree)
        for i,row in enumerate(features):
            train_logits[i]+=learning_rate*_boost_tree_predict(tree,row)
    def predict_probability(row):
        logit=base+sum(learning_rate*_boost_tree_predict(tree,row) for tree in trees)
        return _sigmoid(logit)
    probabilities=[predict_probability(row[0]) for row in test]
    holdout_labels=[row[1] for row in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(probabilities,holdout_labels))/len(holdout_labels) if holdout_labels else None
    brier=mean((p-y)**2 for p,y in zip(probabilities,holdout_labels)) if holdout_labels else None
    live,live_error=_live_market_features(ctx)
    if live_error:return live_error
    normalized=[(live[j]-means[j])/scales[j] for j in range(len(live))]
    research_score=predict_probability(normalized)
    return _ready({"model":"xgboost_style_second_order_gradient_boosted_trees",
                   "boosting_rounds":rounds,"max_tree_depth":2,"training_samples":len(train),
                   "holdout_samples":len(test),
                   "chronological_holdout_accuracy_pct":round(accuracy*100,2) if accuracy is not None else None,
                   "holdout_brier_score":round(brier,5) if brier is not None else None,
                   "research_score_up":round(research_score,5),
                   "warning":"Pure-Python XGBoost-style second-order tree booster, not the upstream XGBoost library; research-only and uncalibrated."},
                  "regularized logistic-loss gradient boosting with second-order gain and chronological holdout")




def _sequence_training_data(ctx, sequence_length: int = 12):
    dataset,err=_ml_dataset(ctx)
    if err:return None,err
    samples=[]
    for end in range(sequence_length-1,len(dataset)):
        sequence=[row[0] for row in dataset[end-sequence_length+1:end+1]]
        samples.append((sequence,dataset[end][1]))
    split=max(40,int(len(samples)*0.8))
    train_end=max(30,split-3)
    train_raw=samples[:train_end]
    test_raw=samples[split:]
    if len(train_raw)<30 or len(test_raw)<5:
        return None,_blocked("insufficient purged sequence samples",["minimum_30_training_sequences","minimum_5_holdout_sequences"])
    width=len(train_raw[0][0][0])
    flattened=[vector for sequence,_ in train_raw for vector in sequence]
    means=[mean(vector[j] for vector in flattened) for j in range(width)]
    scales=[pstdev(vector[j] for vector in flattened) or 1.0 for j in range(width)]
    normalize=lambda seq:[[ (v[j]-means[j])/scales[j] for j in range(width)] for v in seq]
    train=[(normalize(seq),label) for seq,label in train_raw]
    test=[(normalize(seq),label) for seq,label in test_raw]
    rows=_candles(ctx)
    if len(rows)<sequence_length+59:
        return None,_blocked("insufficient latest sequence context",["latest_completed_candle_window"])
    live=[]
    for end in range(len(rows)-sequence_length,len(rows)):
        features,feature_error=_live_market_features({"candles":rows[:end+1]})
        if feature_error:return None,feature_error
        live.append([(features[j]-means[j])/scales[j] for j in range(width)])
    return {
        "train":train,"test":test,"live":live,
        "train_count":len(train),"holdout_count":len(test),
        "sequence_length":sequence_length,"feature_count":width
    },None


def _fit_sequence_readout(train_embeddings,train_labels,test_embeddings,test_labels,live_embedding):
    if not train_embeddings or not test_embeddings:
        return _blocked("sequence encoder produced empty embeddings",["valid_sequence_embeddings"])
    width=len(train_embeddings[0])
    means=[mean(row[j] for row in train_embeddings) for j in range(width)]
    scales=[pstdev(row[j] for row in train_embeddings) or 1.0 for j in range(width)]
    train=[([(row[j]-means[j])/scales[j] for j in range(width)],label)
           for row,label in zip(train_embeddings,train_labels)]
    test=[([(row[j]-means[j])/scales[j] for j in range(width)],label)
          for row,label in zip(test_embeddings,test_labels)]
    live=[(live_embedding[j]-means[j])/scales[j] for j in range(width)]
    weights=[0.0]*width;bias=0.0;learning_rate=0.045;l2=0.02
    for _ in range(180):
        gradients=[0.0]*width;bias_gradient=0.0
        for features,label in train:
            probability=_sigmoid(sum(w*x for w,x in zip(weights,features))+bias)
            error=probability-label
            for j,value in enumerate(features):gradients[j]+=error*value
            bias_gradient+=error
        n=len(train)
        weights=[weights[j]-learning_rate*(gradients[j]/n+l2*weights[j]) for j in range(width)]
        bias-=learning_rate*bias_gradient/n
    holdout_probabilities=[_sigmoid(sum(w*x for w,x in zip(weights,features))+bias)
                            for features,_ in test]
    labels=[label for _,label in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(holdout_probabilities,labels))/len(labels)
    brier=mean((p-y)**2 for p,y in zip(holdout_probabilities,labels))
    live_probability=_sigmoid(sum(w*x for w,x in zip(weights,live))+bias)
    return {
        "research_score_up":round(live_probability,5),
        "chronological_holdout_accuracy_pct":round(accuracy*100,2),
        "holdout_brier_score":round(brier,5),
    }


def _lstm_encode(sequence, weights, biases, hidden_size: int = 8):
    hidden=[0.0]*hidden_size
    cell=[0.0]*hidden_size
    for vector in sequence:
        combined=hidden+vector
        gates=[biases[j]+sum(combined[k]*weights[k][j] for k in range(len(combined)))
               for j in range(hidden_size*4)]
        input_gate=[_sigmoid(x) for x in gates[0:hidden_size]]
        forget_gate=[_sigmoid(x) for x in gates[hidden_size:hidden_size*2]]
        output_gate=[_sigmoid(x) for x in gates[hidden_size*2:hidden_size*3]]
        candidate=[__import__("math").tanh(x) for x in gates[hidden_size*3:hidden_size*4]]
        cell=[forget_gate[j]*cell[j]+input_gate[j]*candidate[j] for j in range(hidden_size)]
        hidden=[output_gate[j]*__import__("math").tanh(cell[j]) for j in range(hidden_size)]
    return hidden


def _lstm_forecast(ctx):
    data,err=_sequence_training_data(ctx)
    if err:return err
    input_size=data["feature_count"];hidden_size=8
    rng=random.Random(27112026)
    weights=[[rng.gauss(0,0.12) for _ in range(hidden_size*4)]
             for _ in range(input_size+hidden_size)]
    biases=[0.0]*(hidden_size*4)
    for j in range(hidden_size,hidden_size*2):biases[j]=1.0
    train_embeddings=[_lstm_encode(seq,weights,biases,hidden_size) for seq,_ in data["train"]]
    test_embeddings=[_lstm_encode(seq,weights,biases,hidden_size) for seq,_ in data["test"]]
    live_embedding=_lstm_encode(data["live"],weights,biases,hidden_size)
    result=_fit_sequence_readout(train_embeddings,[y for _,y in data["train"]],
                                 test_embeddings,[y for _,y in data["test"]],live_embedding)
    if result.get("status")=="blocked_missing_input":return result
    return _ready({"model":"lstm_reservoir_with_trained_logistic_readout",
                   "hidden_size":hidden_size,"sequence_length":data["sequence_length"],
                   "training_sequences":data["train_count"],"holdout_sequences":data["holdout_count"],
                   **result,
                   "warning":"LSTM gate weights are deterministic fixed reservoir features; only the output readout is trained on this request. This is a research baseline, not a fully backprop-trained persistent LSTM."},
                  "single-layer LSTM feature extractor with deterministic recurrent gates and trained readout; chronological purged holdout")


def _transformer_encode(sequence, query_weights, key_weights, value_weights, hidden_size: int = 8):
    projected=[]
    length=len(sequence)
    for index,vector in enumerate(sequence):
        positioned=[]
        for j,value in enumerate(vector):
            scale=10000.0**(2*(j//2)/max(1,len(vector)))
            angle=(index+1)/scale
            positional=__import__("math").sin(angle) if j%2==0 else __import__("math").cos(angle)
            positioned.append(value+positional*0.05)
        query=[sum(positioned[k]*query_weights[k][j] for k in range(len(positioned))) for j in range(hidden_size)]
        key=[sum(positioned[k]*key_weights[k][j] for k in range(len(positioned))) for j in range(hidden_size)]
        value=[sum(positioned[k]*value_weights[k][j] for k in range(len(positioned))) for j in range(hidden_size)]
        projected.append((query,key,value))
    last_query=projected[-1][0]
    scores=[sum(last_query[j]*item[1][j] for j in range(hidden_size))/sqrt(hidden_size)
            for item in projected]
    peak=max(scores)
    exps=[exp(max(-35.0,min(35.0,value-peak))) for value in scores]
    total=sum(exps) or 1.0
    attention=[value/total for value in exps]
    context=[sum(attention[i]*projected[i][2][j] for i in range(length))
             for j in range(hidden_size)]
    last_value=projected[-1][2]
    return [__import__("math").tanh(context[j]+last_value[j]) for j in range(hidden_size)]


def _transformer_forecast(ctx):
    data,err=_sequence_training_data(ctx)
    if err:return err
    input_size=data["feature_count"];hidden_size=8
    rng=random.Random(27112027)
    scale=1.0/sqrt(input_size)
    query_weights=[[rng.gauss(0,scale*0.35) for _ in range(hidden_size)] for _ in range(input_size)]
    key_weights=[[rng.gauss(0,scale*0.35) for _ in range(hidden_size)] for _ in range(input_size)]
    value_weights=[[rng.gauss(0,scale*0.35) for _ in range(hidden_size)] for _ in range(input_size)]
    encode=lambda seq:_transformer_encode(seq,query_weights,key_weights,value_weights,hidden_size)
    train_embeddings=[encode(seq) for seq,_ in data["train"]]
    test_embeddings=[encode(seq) for seq,_ in data["test"]]
    live_embedding=encode(data["live"])
    result=_fit_sequence_readout(train_embeddings,[y for _,y in data["train"]],
                                 test_embeddings,[y for _,y in data["test"]],live_embedding)
    if result.get("status")=="blocked_missing_input":return result
    return _ready({"model":"single_head_self_attention_with_trained_logistic_readout",
                   "hidden_size":hidden_size,"sequence_length":data["sequence_length"],
                   "training_sequences":data["train_count"],"holdout_sequences":data["holdout_count"],
                   **result,
                   "warning":"Query/key/value projections are deterministic fixed research features; only the output readout is trained. This is not a fully end-to-end trained Transformer or a persistent model."},
                  "single-head scaled dot-product self-attention feature extractor with positional encoding and trained readout; chronological purged holdout")


_HANDLER_IDS = {
    "E005":_base, "E006":_base, "E008":_external,
    "E009":_trend, "E011":_support_resistance, "E012":_accumulation,
    "E013":_smc, "E014":_sweep, "E015":_fvg, "E016":_breakout,
    "E017":_divergence, "E019":_candlestick, "E020":_fibonacci,
    "E022":_volume_profile, "E023":_divergence, "E024":_candlestick,
    "E026":_higher_timeframe, "E027":_lower_timeframe, "E028":_regime_timeframe_sync, "E029":_market_phase,
    "E030":_timing, "E031":_timing, "E032":_trend_exhaustion,
    "E034":_early_breakout, "E035":_accumulation, "E036":_sweep,
    "E037":_momentum_explosion, "E038":_whale_activity, "E039":_volume, "E040":_compression,
    "E042":_breakout, "E043":_external,
    "E044":_ai_analyst, "E045":_logistic_model, "E046":_external, "E047":_external,
    "E048":_external, "E049":_external, "E050":_external, "E051":_random_forest,
    "E052":_anomaly_detection, "E053":_clustering, "E054":_regime_detector, "E055":_forecast,
    "E056":_empirical_probability, "E057":_ensemble, "E058":_logistic_model, "E059":_explain_model,
    "E060":_derivatives, "E061":_derivatives, "E062":_derivatives,
    "E063":_external, "E064":_external, "E065":_external, "E066":_external,
    "E067":_leverage_risk, "E068":_derivative_divergence, "E069":_external, "E070":_external, "E071":_external,
    "E073":_external, "E074":_risk, "E075":_entry_precision, "E076":_risk, "E077":_take_profit,
    "E078":_external, "E079":_external, "E080":_false_breakout, "E081":_external,
    "E082":_external, "E083":_signal_expiration, "E084":_backtest, "E085":_external,
    "E086":_risk, "E087":_dynamic_risk, "E088":_portfolio_risk, "E089":_max_drawdown,
    "E090":_correlation_risk, "E091":_portfolio, "E092":_liquidation_protection, "E093":_slippage_estimate,
    "E094":_fee_calc, "E095":_volatility_stop, "E096":_breakeven, "E097":_trailing_stop,
    "E098":_daily_limit, "E099":_external, "E100":_risk_approval,
    "E102":_walk_forward, "E104":_external, "E105":_external, "E106":_external,
    "E107":_external, "E108":_external, "E109":_attribution, "E110":_backtest,
    "E111":_backtest, "E112":_backtest, "E113":_strategy_compare, "E114":_model_drift, "E115":_external,
    "E116":_portfolio, "E117":_portfolio, "E118":_external, "E119":_position_monitor,
    "E120":_position_monitor, "E121":_external, "E122":_external, "E123":_external,
    "E124":_backtest, "E125":_portfolio,
    "E127":_ai_analyst, "E128":_orderbook, "E129":_smc, "E130":_derivatives,
    "E131":_trend, "E132":_external, "E133":_risk, "E134":_external,
    "E135":_agents, "E136":_conflict_resolver, "E137":_agents, "E138":_knowledge_memory, "E139":_external, "E140":_autonomous_research,
    "E141":_external, "E142":_event_bus, "E143":_external, "E144":_external,
    "E145":_external, "E146":_external, "E147":_external, "E148":_external,
    "E149":_duplicate_signal_filter, "E150":_external, "E151":_audit_log, "E152":_model_registry,
    "E153":_data_replay, "E154":_external, "E155":_resource_monitor, "E156":_watchdog,
}


_HANDLER_IDS.update({
    "E001":_base,"E002":_orderbook,"E003":_orderbook,"E004":_compression,
    "E007":_external,"E008":_cross_market_correlation,"E010":_market_structure,
    "E018":_momentum,"E021":_vwap,"E025":_timeframes,"E033":_opportunity,
    "E041":_opportunity,"E043":_arbitrage,"E062":_long_short,"E064":_liquidation_tracker,
    "E065":_basis,"E066":_derivatives,"E072":_generic_score,"E073":_confidence,
    "E075":_risk,"E078":_trade_quality,"E081":_conflict_resolver,"E082":_rank_opportunities,
    "E083":_external,"E085":_entry_readiness,"E089":_portfolio,"E090":_portfolio,
    "E093":_risk,"E094":_risk,"E097":_risk,"E099":_circuit_breaker,
    "E101":_backtest,"E103":_paper_positions,"E104":_monte_carlo,"E105":_backtest,
    "E106":_backtest,"E107":_overfit,"E108":_out_of_sample,"E110":_backtest,
    "E111":_backtest,"E112":_backtest,"E113":_backtest,"E114":_backtest,
    "E115":_backtest,"E118":_position_monitor,"E121":_position_monitor,
    "E122":_position_monitor,"E123":_position_monitor,"E126":_agents,
    "E127":_agents,"E129":_sweep,"E131":_trend,"E132":_external,
    "E133":_risk,"E134":_adaptive_router,"E135":_agents,"E136":_agents,
    "E137":_agents,"E138":_external,"E139":_adaptive_router,"E140":_agents,
    "E141":_system_health,"E142":_system_health,"E143":_system_health,
    "E144":_system_health,"E145":_system_health,"E146":_system_health,
    "E147":_system_health,"E148":_system_health,"E149":_system_health,
    "E150":_system_health,"E151":_system_health,"E152":_system_health,
    "E153":_system_health,"E154":_system_health,"E155":_system_health,
    "E156":_system_health,
})

def _news_events(ctx):
    events=ctx.get("news_events")
    if not isinstance(events,list):return _blocked("normalized news events from a verified provider required",["news_events"])
    output=[]
    positive=("approval","partnership","integration","listing","launch","adoption","upgrade","inflow","زيادة","إدراج","شراكة","اعتماد")
    negative=("hack","exploit","lawsuit","delist","unlock","outflow","breach","attack","اختراق","دعوى","إلغاء إدراج","فتح قفل")
    for event in events:
        if not isinstance(event,dict):continue
        title=str(event.get("title",""));body=str(event.get("summary",""))
        text=(title+" "+body).lower()
        pos=sum(word in text for word in positive);neg=sum(word in text for word in negative)
        sentiment="POSITIVE" if pos>neg else "NEGATIVE" if neg>pos else "NEUTRAL"
        output.append({"title":title[:200],"source":event.get("source"),
                       "published_at":event.get("published_at"),"sentiment":sentiment,
                       "keyword_evidence":{"positive":pos,"negative":neg}})
    return _ready({"events":output,"count":len(output),
                   "warning":"Keyword triage only; provider credibility and factual verification remain external."},
                  "rule-based event triage over provider-supplied headlines and summaries")


_HANDLER_IDS.update({
    "E007":_news_events,
    "E047":_lstm_forecast,
    "E048":_transformer_forecast,
    "E046":_deep_learning_mlp,
    "E049":_rl_agent,
    "E050":_xgboost_classifier,
    "E008":_cross_market_correlation,
    "E014":_order_block,
    "E046":_deep_learning_mlp,
    "E049":_rl_agent,
    "E050":_xgboost_classifier,
    "E063":_liquidation_heatmap,
    "E069":_options_analytics,
    "E070":_implied_volatility_engine,
    "E071":_gamma_exposure,
    "E079":_entry_readiness,
    "E083":_signal_expiration,
    "E138":_knowledge_memory,
    "E105":_strategy_optimizer,
    "E106":_parameter_optimizer,
    "E110":_win_rate,
    "E111":_profit_factor,
    "E112":_expectancy,
    "E115":_continuous_learning,
    "E123":_trade_recovery,
    "E132":_ai_prediction,
    "E141":_scheduler,
    "E143":_cache,
    "E144":_database,
    "E145":_websocket,
    "E148":_error_recovery,
    "E149":_duplicate_signal_filter,
    "E150":_notification,
    "E154":_security,
    "E074":_risk_reward,
})
# Final handler map: bind each engine to its most specific available implementation.
_HANDLER_IDS.update({
    "E001":_market_data_ingestion, "E002":_orderbook, "E003":_liquidity, "E004":_volatility,
    "E005":_data_normalization, "E006":_data_quality, "E007":_news_events, "E008":_cross_market_correlation,
    "E009":_trend, "E010":_market_structure, "E011":_support_resistance, "E012":_supply_demand,
    "E013":_smc, "E014":_order_block, "E015":_fvg, "E016":_breakout, "E017":_divergence,
    "E018":_momentum, "E019":_candlestick, "E020":_fibonacci, "E021":_vwap,
    "E022":_volume_profile, "E023":_divergence, "E024":_candlestick,
    "E025":_timeframes, "E026":_higher_timeframe, "E027":_lower_timeframe,
    "E028":_regime_timeframe_sync, "E029":_market_phase, "E030":_timing, "E031":_timing, "E032":_trend_exhaustion,
    "E033":_opportunity, "E034":_early_breakout, "E035":_accumulation, "E036":_sweep,
    "E037":_momentum_explosion, "E038":_whale_activity, "E039":_volume, "E040":_compression,
    "E041":_futures_opportunity, "E042":_spot_opportunity, "E043":_arbitrage,
    "E044":_ai_analyst, "E045":_logistic_model, "E046":_deep_learning_mlp, "E047":_lstm_forecast,
    "E048":_transformer_forecast, "E049":_rl_agent, "E050":_xgboost_classifier,
    "E051":_random_forest, "E052":_anomaly_detection, "E053":_clustering, "E054":_regime_detector,
    "E055":_forecast, "E056":_empirical_probability, "E057":_ensemble, "E058":_continuous_learning,
    "E059":_explain_model, "E060":_funding_rate, "E061":_open_interest, "E062":_long_short,
    "E063":_liquidation_heatmap, "E064":_liquidation_tracker, "E065":_basis, "E066":_derivatives,
    "E067":_leverage_risk, "E068":_derivative_divergence, "E069":_options_analytics,
    "E070":_implied_volatility_engine, "E071":_gamma_exposure, "E072":_generic_score,
    "E073":_confidence, "E074":_risk_reward, "E075":_entry_precision, "E076":_risk,
    "E077":_take_profit, "E078":_trade_quality, "E079":_entry_readiness, "E080":_false_breakout,
    "E081":_conflict_resolver, "E082":_rank_opportunities, "E083":_signal_expiration, "E084":_expectancy,
    "E085":_entry_readiness, "E086":_risk, "E087":_dynamic_risk, "E088":_portfolio_risk,
    "E089":_max_drawdown, "E090":_correlation_risk, "E091":_portfolio, "E092":_liquidation_protection,
    "E093":_slippage_estimate, "E094":_fee_calc, "E095":_volatility_stop, "E096":_breakeven,
    "E097":_trailing_stop, "E098":_daily_limit, "E099":_circuit_breaker, "E100":_risk_approval,
    "E101":_backtest, "E102":_walk_forward, "E103":_paper_positions, "E104":_monte_carlo,
    "E105":_strategy_optimizer, "E106":_parameter_optimizer, "E107":_overfit,
    "E108":_out_of_sample, "E109":_attribution, "E110":_win_rate, "E111":_profit_factor,
    "E112":_expectancy, "E113":_strategy_compare, "E114":_model_drift, "E115":_continuous_learning,
    "E116":_position_monitor, "E117":_position_monitor, "E118":_entry_readiness,
    "E119":_position_monitor, "E120":_position_monitor, "E121":_position_monitor,
    "E122":_position_monitor, "E123":_trade_recovery, "E124":_trade_journal,
    "E125":_portfolio, "E126":_agents, "E127":_ai_analyst, "E128":_orderbook,
    "E129":_smc, "E130":_derivatives, "E131":_trend, "E132":_ai_prediction,
    "E133":_risk, "E134":_adaptive_router, "E135":_agents, "E136":_conflict_resolver,
    "E137":_agents, "E138":_knowledge_memory, "E139":_adaptive_router, "E140":_autonomous_research,
    "E141":_scheduler, "E142":_event_bus, "E143":_cache, "E144":_database,
    "E145":_websocket, "E146":_system_health, "E147":_system_health, "E148":_error_recovery,
    "E149":_duplicate_signal_filter, "E150":_notification, "E151":_audit_log,
    "E152":_model_registry, "E153":_data_replay, "E154":_security,
    "E155":_resource_monitor, "E156":_watchdog,
})

# All remaining catalogue IDs still have a callable, fail-closed adapter.
for _catalogue_item in ENGINE_CATALOG:
    _HANDLER_IDS.setdefault(_catalogue_item["id"], _external)


def _sanitize_runtime_value(value: Any, path: str = "$", invalid_paths: list[str] | None = None):
    """Prevent NaN/Infinity from escaping an engine adapter into strict JSON responses."""
    if invalid_paths is None:
        invalid_paths = []
    if isinstance(value, float) and not isfinite(value):
        invalid_paths.append(path)
        return None
    if isinstance(value, dict):
        return {
            str(key): _sanitize_runtime_value(item, f"{path}.{key}", invalid_paths)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_runtime_value(item, f"{path}[{index}]", invalid_paths)
            for index, item in enumerate(value)
        ]
    return value


def run_engine(engine_id: str, context: dict) -> dict:
    item = next((x for x in ENGINE_CATALOG if x["id"] == engine_id), None)
    if item is None:
        return {"engine_id":engine_id,"status":"unknown_engine"}
    handler = _HANDLER_IDS.get(engine_id)
    if handler is None:
        value = _external(context)
    elif handler is _base:
        _, error = _base(context, 30)
        value = error or _ready({"valid_candles":len(_candles(context))},"validated OHLCV schema")
    else:
        try:
            value = handler(context)
        except (TypeError, ValueError, KeyError, ZeroDivisionError, OverflowError) as exc:
            value = {"status":"input_error","reason":type(exc).__name__}
    invalid_numeric_paths: list[str] = []
    value = _sanitize_runtime_value(value, invalid_paths=invalid_numeric_paths)
    if invalid_numeric_paths:
        value = {
            "status": "invalid_numeric_output",
            "reason": "Engine produced NaN or Infinity; unsafe numeric fields were suppressed.",
            "invalid_numeric_paths": invalid_numeric_paths,
            "sanitized_value": value,
        }
    adapter_available = handler is not None and handler is not _external
    runtime_status = value.get("status") if isinstance(value, dict) else "invalid_result"
    context_keys = sorted(str(key) for key, item_value in context.items() if item_value is not None)
    market_snapshot = context.get("market_snapshot") or {}
    heartbeats = context.get("heartbeats") if isinstance(context.get("heartbeats"), dict) else {}
    api_heartbeat = heartbeats.get("api") if isinstance(heartbeats.get("api"), dict) else {}
    api_age = _num(api_heartbeat.get("age_seconds"), 61.0)
    system_health = context.get("system_health") if isinstance(context.get("system_health"), dict) else {}
    positions = context.get("positions")
    known_positions = positions if isinstance(positions, list) else None
    open_positions = [
        position for position in (known_positions or [])
        if isinstance(position, dict) and str(position.get("status", "")).upper() == "OPEN"
    ]
    current_prices = context.get("current_prices") if isinstance(context.get("current_prices"), dict) else {}
    missing_position_marks = [
        str(position.get("symbol", "")).upper()
        for position in open_positions
        if _num(current_prices.get(str(position.get("symbol", "")).upper())) <= 0
    ]
    input_signals = {
        "market_snapshot_valid":bool(context.get("candles") and market_snapshot.get("freshness_status") == "fresh"),
        "orderbook_available":bool(context.get("orderbook")),
        "orderbook_fresh":bool(context.get("orderbook") and _fresh_observation(context,"orderbook_observed_at")),
        "trades_available":bool(context.get("trades")),
        "trades_fresh":bool(context.get("trades") and _fresh_observation(context,"trades_observed_at")),
        "timeframes_available":len(context.get("timeframes") or {}) >= 2,
        "timeframes_fresh":sum(1 for item in (context.get("timeframes") or {}).values()
                                if _valid_timeframe_snapshot(item)) >= 2,
        "portfolio_context_available":"account" in context and "positions" in context,
        "trade_history_available":bool(context.get("closed_trades")),
        # An explicitly observed empty paper ledger is a valid idle state: no
        # position needs a mark. Every open paper position still needs its own
        # fresh, positive mark before position-monitoring readiness can pass.
        "paper_positions_known":known_positions is not None,
        "open_positions_count":len(open_positions),
        "position_marks_available":not missing_position_marks,
        "missing_position_mark_symbols":missing_position_marks,
        "entry_confirmation_available":bool(context.get("entry_confirmation")),
        "api_heartbeat_fresh":api_age <= 60,
        "system_health_ok":bool(system_health) and all(value == "ok" for value in system_health.values()),
        "system_health_available":bool(system_health),
        "opportunity_history_available":isinstance(context.get("opportunity_events"), list),
        "scheduler_jobs_available":isinstance(context.get("scheduler_jobs", context.get("scheduled_jobs")), list),
        "event_bus_available":isinstance(context.get("event_bus"), dict),
        "cache_available":isinstance(context.get("cache"), dict),
        "database_available":isinstance(context.get("database"), dict),
        "websocket_available":isinstance(context.get("websocket"), dict),
        "failure_log_available":isinstance(context.get("recent_failures"), list),
        "signal_list_available":isinstance(context.get("signals"), list),
        "notification_transport_available":bool(context.get("notification_transport_available")),
        "audit_log_available":isinstance(context.get("audit_events"), list),
        "model_registry_available":isinstance(context.get("model_versions"), list),
        "replay_log_available":isinstance(context.get("replay_events"), list),
        "security_policy_available":isinstance(context.get("security_policy"), dict),
        "resource_snapshot_available":isinstance(context.get("resource_snapshot"), dict),
        "heartbeat_records_available":isinstance(heartbeats, dict) and bool(heartbeats),
    }
    return {"engine_id":engine_id,"name":item["name"],"group":item["group"],
            "catalog_status":item["status"],"runtime":value,
            "checked_at":datetime.now(timezone.utc).isoformat(),
            "adapter_evidence":{"available":adapter_available,
                                 "name":getattr(handler,"__name__",None) if handler else None,
                                 "source":"app.engine_suite" if adapter_available else None},
            "input_evidence":{"available":bool(runtime_status == "computed" and context_keys),
                              "context_keys_present":context_keys,
                              **input_signals},
            "trading_mode":"simulation","live_trading_enabled":False}


def run_engine_suite(context: dict, engine_ids: list[str] | None = None) -> dict:
    selected = engine_ids or [item["id"] for item in ENGINE_CATALOG]
    results = [run_engine(engine_id, context) for engine_id in selected]
    counts = {}
    for result in results:
        status = result.get("runtime",{}).get("status","unknown")
        counts[status] = counts.get(status,0)+1
    return {"total_requested":len(selected),"counts":counts,"results":results,
            "trading_mode":"simulation","live_trading_enabled":False,
            "disclaimer":"A callable adapter is not equivalent to a verified production data path. Missing feeds and model artifacts are explicitly blocked; no live orders are possible."}


def early_opportunity_assessment(context: dict) -> dict:
    """Score pre-breakout evidence from completed candles and optional live snapshots."""
    rows, error = _base(context, 60)
    if error:
        return {"status":"insufficient_data","reason":error["reason"],"score":0,
                "tier":"UNRATED","trading_mode":"simulation","live_trading_enabled":False}
    comp=_compression(context); acc=_accumulation(context); vol=_volume(context)
    sweep=_sweep(context); book=_orderbook(context); flow=_trades(context)
    br=_breakout(context); reg=context.get("regime") if isinstance(context.get("regime"),dict) else {}
    weights={"compression":20,"accumulation":20,"volume":15,"liquidity":15,"order_flow":10,"structure":10,"regime":5,"derivatives":5}
    parts={key:0.0 for key in weights}
    reasons=[]; missing=[]
    if comp.get("status")=="computed":
        v=comp["value"]
        if v["compressed"]: parts["compression"]=20; reasons.append("انضغاط النطاق")
        elif v["range_ratio"] is not None and v["range_ratio"]<0.85: parts["compression"]=12
    else: missing.append("compression")
    if acc.get("status")=="computed":
        v=acc["value"]
        if v["possible_absorption"]: parts["accumulation"]=20; reasons.append("ضغط شراء محتمل مع نطاق سعري محدود")
        elif v["signed_volume_pressure"] is not None and v["signed_volume_pressure"]>0.1: parts["accumulation"]=10
    else: missing.append("accumulation")
    if vol.get("status")=="computed":
        v=vol["value"]
        if v["volume_ratio"] is not None and v["volume_ratio"]>=1.5: parts["volume"]=15; reasons.append("ارتفاع الحجم")
        elif v["volume_ratio"] is not None and v["volume_ratio"]>=1.2: parts["volume"]=8
    else: missing.append("volume")
    if book.get("status")=="computed":
        imb=book["value"]["imbalance"]
        parts["liquidity"]=_clamp((imb+0.15)/0.65*15,0,15)
        if imb>=0.15: reasons.append("اختلال دفتر الأوامر لصالح الطلب")
    else: missing.append("orderbook")
    if flow.get("status")=="computed":
        delta=flow["value"]["delta_notional"]; total=flow["value"]["buy_notional"]+flow["value"]["sell_notional"]
        parts["order_flow"]=_clamp((delta/total+1)/2*10,0,10) if total else 0
        if delta>0: reasons.append("صافي تدفق صفقات شراء")
    else: missing.append("trade_flow")
    if sweep.get("status")=="computed":
        if sweep["value"]["bullish_sweep"]: parts["structure"]=10; reasons.append("سحب سيولة هابط مع إغلاق استردادي")
        elif br.get("status")=="computed" and br["value"]["breakout_up"]: parts["structure"]=8; reasons.append("اختراق صاعد مؤكد بإغلاق شمعة")
        elif not sweep["value"]["bearish_sweep"]: parts["structure"]=4
    else: missing.append("structure")
    if reg.get("status")=="ok":
        parts["regime"]=5 if reg.get("trend")=="UPTREND" else 2.5 if reg.get("trend")=="RANGE" else 0
    else: missing.append("market_regime")
    deriv=_derivatives(context)
    if deriv.get("status")=="computed":
        funding=deriv["value"]["funding_rate"]
        parts["derivatives"]=5 if funding<=0.0005 else 2.5 if funding<=0.001 else 0
    else: missing.append("derivatives")
    score=round(sum(parts.values()),2)
    confirmed=bool(br.get("status")=="computed" and br["value"]["breakout_up"])
    if score>=80 and not confirmed: tier="GOLD_EARLY"
    elif score>=65: tier="GREEN_WATCH"
    elif score>=45: tier="SILVER_EARLY"
    else: tier="NO_SETUP"
    if confirmed: tier="BREAKOUT_CONFIRMED"
    close=rows[-1]["close"]; atr=_atr(rows) or close*0.01
    entry_low=close-0.15*atr; entry_high=close+0.1*atr
    invalidation=close-1.5*atr
    return {"status":"computed","symbol":context.get("symbol"),"category":context.get("category","spot"),
            "interval":context.get("interval"),"score":score,"max_score":100,"components":parts,
            "tier":tier,"breakout_confirmed":confirmed,"reasons":reasons,"missing_confirmations":missing,
            "reference_price":close,"watch_entry_zone":[round(entry_low,10),round(entry_high,10)],
            "invalidation_reference":round(invalidation,10),
            "targets_reference":[round(close+2*atr,10),round(close+3*atr,10)],
            "plan_note":"Research watch-zone only; not an order or probability. Confirm entry, liquidity and risk independently.",
            "trading_mode":"simulation","live_trading_enabled":False}


def catalogue_runtime_coverage() -> dict:
    all_ids={x["id"] for x in ENGINE_CATALOG}
    routed=all_ids.intersection(_HANDLER_IDS)
    external_only=sorted(x for x in routed if _HANDLER_IDS.get(x) is _external)
    callable_adapters=sorted(routed-set(external_only))
    status_counts={status:sum(1 for x in ENGINE_CATALOG if x["status"]==status)
                   for status in ("implemented","partial","planned")}
    return {
        "catalogue_engines":len(all_ids),
        "routed_adapters":len(routed),
        "callable_adapter_coverage_pct":round(len(routed)/len(all_ids)*100,2) if all_ids else 0,
        "callable_adapters":len(callable_adapters),
        "active_runtime_adapters":0,
        "external_or_model_blocked_adapters":len(external_only),
        "external_or_model_blocked_ids":external_only,
        "unrouted_adapters":sorted(all_ids-routed),
        "catalogue_status_counts":status_counts,
        "trading_mode":"simulation","live_trading_enabled":False,
        "note":"Adapter counts describe callable code only. ACTIVE counts are produced by request-time evidence evaluation, never by adapter presence."
    }

