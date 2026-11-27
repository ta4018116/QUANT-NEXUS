"""Runtime adapters for the 156-engine QUANT NEXUS catalogue.

Every catalogue entry has a callable contract. A result is either computed from
provided, validated evidence or explicitly blocked because its required input
(model artifact, provider feed, portfolio data, etc.) is absent. No fabricated
market data, probabilities, or orders are produced.
"""
from __future__ import annotations

from math import exp, isfinite, sqrt
import random
from statistics import NormalDist, mean, median, pstdev
from typing import Any

from .engine_catalog import ENGINE_CATALOG


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


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
    resistance = highs[-3]
    support = lows[2]
    return _ready({"support_zone": [lows[0], lows[min(4, len(lows)-1)]],
                   "resistance_zone": [highs[max(0, len(highs)-5)], highs[-1]],
                   "nearest_support_distance_pct": round((current-support)/current*100, 4),
                   "nearest_resistance_distance_pct": round((resistance-current)/current*100, 4)},
                  "rolling extrema zones; not institutional order-flow claims")


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
    if not isinstance(agents,list) or not agents: return _blocked("independent agent assessments required",["agent_results"])
    valid=[x for x in agents if isinstance(x,dict) and x.get("direction") in ("LONG","SHORT","NEUTRAL")]
    if not valid: return _blocked("no valid agent directions",["agent direction assessments"])
    long=sum(x["direction"]=="LONG" for x in valid); short=sum(x["direction"]=="SHORT" for x in valid)
    direction="LONG" if long>short else "SHORT" if short>long else "NEUTRAL"
    return _ready({"agents":len(valid),"long_votes":long,"short_votes":short,"consensus":direction,
                   "agreement_pct":max(long,short)/len(valid)*100},
                  "unweighted directional vote; not an independent prediction")


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
    if not isinstance(item,dict): return _blocked("4h snapshot required",["timeframes.4h"])
    return _ready({"timeframe":"4h","direction":item.get("direction"),"score":item.get("score")},
                  "higher timeframe snapshot supplied by multi-timeframe provider")


def _lower_timeframe(ctx):
    frames=ctx.get("timeframes")
    item=(frames.get("5m") or frames.get("15m")) if isinstance(frames,dict) else None
    if not isinstance(item,dict): return _blocked("5m or 15m snapshot required",["timeframes.5m_or_15m"])
    return _ready({"timeframe":item.get("timeframe","5m_or_15m"),
                   "direction":item.get("direction"),"score":item.get("score")},
                  "lower timeframe snapshot supplied by multi-timeframe provider")


def _regime_timeframe_sync(ctx):
    frames=ctx.get("timeframes")
    if not isinstance(frames,dict) or len(frames)<2: return _blocked("multiple timeframe snapshots required",["timeframes"])
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
    base=[_num(x) for x in ctx.get("closes",[])]
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
    fee=_num(ctx.get("round_trip_fee_pct")); slip=_num(ctx.get("round_trip_slippage_pct"))
    clean={str(k):_num(v) for k,v in prices.items() if _num(v)>0}
    if len(clean)<2: return _blocked("insufficient valid venue marks",["positive_exchange_prices"])
    buy=min(clean,key=clean.get); sell=max(clean,key=clean.get)
    gross=(clean[sell]/clean[buy]-1)*100
    net=gross-fee-slip
    return _ready({"buy_venue":buy,"sell_venue":sell,"gross_spread_pct":gross,
                   "estimated_net_spread_pct":net,"positive_after_costs":net>0},
                  "synchronized supplied marks less supplied fees and slippage; excludes transfer and latency risk")


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
    if not isinstance(frames,dict) or len(frames)<2: return _blocked("at least two timeframe analyses required",["timeframes"])
    directions=[str(x.get("direction","NEUTRAL")).upper() for x in frames.values() if isinstance(x,dict)]
    directional=[x for x in directions if x in ("UP","DOWN","LONG","SHORT")]
    if not directional: return _blocked("timeframe direction values missing",["timeframes.*.direction"])
    up=sum(x in ("UP","LONG") for x in directional); down=sum(x in ("DOWN","SHORT") for x in directional)
    return _ready({"up_frames":up,"down_frames":down,"total_directional_frames":len(directional),
                   "consensus":"UP" if up>down else "DOWN" if down>up else "MIXED",
                   "agreement_pct":max(up,down)/len(directional)*100},
                  "directional agreement across provided frame snapshots")


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
    dataset,err=_ml_dataset(ctx)
    if err: return err
    split=max(40,int(len(dataset)*0.8))
    train_raw,test_raw=dataset[:split],dataset[split:]
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
    latest_features=dataset[-1][0]
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
    train,test,_,_=_standardize(dataset[:split],dataset[split:])
    rng=random.Random(20261127)
    trees=[]
    for i in range(21):
        boot=[train[rng.randrange(len(train))] for _ in range(len(train))]
        trees.append(_build_tree(boot,3,rng))
    predictions=[sum(_tree_predict(tree,features) for tree in trees)/len(trees) for features,_ in test]
    labels=[label for _,label in test]
    accuracy=sum((p>=0.5)==bool(y) for p,y in zip(predictions,labels))/len(labels) if labels else None
    latest=dataset[-1][0]
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
    side=str(ctx.get("side","LONG")).upper()
    if not atr or side not in ("LONG","SHORT"):return _blocked("ATR and valid side required",["atr14","side"])
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
    if daily.get("status")!="computed":return daily
    health=ctx.get("system_health") or {}
    unhealthy=[k for k,v in health.items() if str(v).lower() not in ("ok","healthy","up")]
    stopped=daily["value"]["limit_breached"] or bool(unhealthy)
    return _ready({"tripped":stopped,"daily_loss_limit_breached":daily["value"]["limit_breached"],
                   "unhealthy_services":unhealthy},"read-only circuit-breaker state; execution remains paper-only")


def _risk_approval(ctx):
    checks=ctx.get("risk_checks")
    if not isinstance(checks,dict) or not checks:return _blocked("explicit risk-check results required",["risk_checks"])
    failed=[k for k,v in checks.items() if v is not True]
    return _ready({"approved":not failed,"failed_checks":failed},
                  "fail-closed aggregation; any missing or false check rejects approval")


def _walk_forward(ctx):
    values=ctx.get("strategy_returns")
    if not isinstance(values,list) or len(values)<20:return _blocked("at least 20 ordered strategy returns required",["strategy_returns"])
    cut=int(len(values)*0.6);train=[_num(x) for x in values[:cut]];test=[_num(x) for x in values[cut:]]
    return _ready({"train_samples":len(train),"test_samples":len(test),
                   "train_mean_return":mean(train),"test_mean_return":mean(test),
                   "train_positive_rate":sum(x>0 for x in train)/len(train),
                   "test_positive_rate":sum(x>0 for x in test)/len(test)},
                  "chronological 60/40 single split; not a full rolling walk-forward grid")


def _monte_carlo(ctx):
    values=ctx.get("strategy_returns")
    if not isinstance(values,list) or len(values)<10:return _blocked("at least 10 ordered trade returns required",["strategy_returns"])
    rng=random.Random(27112026); sims=300; horizon=len(values); endings=[]
    for _ in range(sims):
        equity=1.0
        for _ in range(horizon):equity*=1+_num(values[rng.randrange(horizon)])
        endings.append(equity)
    ordered=sorted(endings)
    return _ready({"simulations":sims,"median_terminal_equity_multiple":ordered[sims//2],
                   "p05_terminal_equity_multiple":ordered[int(sims*0.05)],
                   "p95_terminal_equity_multiple":ordered[int(sims*0.95)],
                   "fraction_below_start":sum(x<1 for x in endings)/sims},
                  "bootstrap resampling of supplied historical returns; scenarios are not forecasts")


def _overfit(ctx):
    train=ctx.get("train_metrics");valid=ctx.get("validation_metrics")
    if not isinstance(train,dict) or not isinstance(valid,dict):return _blocked("train and validation metrics required",["train_metrics","validation_metrics"])
    key="accuracy"
    if train.get(key) is None or valid.get(key) is None:return _blocked("accuracy metrics required",["train_metrics.accuracy","validation_metrics.accuracy"])
    gap=_num(train[key])-_num(valid[key])
    return _ready({"train_accuracy":_num(train[key]),"validation_accuracy":_num(valid[key]),
                   "generalization_gap":gap,"overfit_warning":gap>0.1},
                  "train-validation accuracy gap heuristic; threshold 10 percentage points")


def _out_of_sample(ctx):
    valid=ctx.get("validation_metrics")
    if not isinstance(valid,dict):return _blocked("untouched validation metrics required",["validation_metrics"])
    required=("trade_count","net_return","max_drawdown")
    if any(valid.get(k) is None for k in required):return _blocked("validation metrics incomplete",list(required))
    return _ready({k:valid[k] for k in required},"reporting on separately supplied untouched validation results")


def _attribution(ctx):
    trades=ctx.get("closed_trades")
    if not isinstance(trades,list):return _blocked("closed trades with strategy labels required",["closed_trades"])
    groups={}
    for trade in trades:
        if not isinstance(trade,dict):continue
        key=str(trade.get("strategy") or trade.get("signal_source") or "UNATTRIBUTED")
        groups[key]=groups.get(key,0)+_num(trade.get("pnl"))
    return _ready({"net_pnl_by_strategy":groups},"sum realized paper PnL by recorded strategy/source label")


def _strategy_compare(ctx):
    items=ctx.get("strategy_results")
    if not isinstance(items,list) or not items:return _blocked("strategy result set required",["strategy_results"])
    clean=[{"name":str(x.get("name","unnamed")),"net_return":_num(x.get("net_return")),
            "max_drawdown":_num(x.get("max_drawdown")),"trade_count":int(_num(x.get("trade_count")))}
           for x in items if isinstance(x,dict)]
    return _ready({"ranked":sorted(clean,key=lambda x:(x["net_return"],-x["max_drawdown"]),reverse=True)},
                  "ranking of supplied backtest results; not live strategy selection")


def _model_drift(ctx):
    baseline=ctx.get("baseline_metrics");recent=ctx.get("recent_metrics")
    if not isinstance(baseline,dict) or not isinstance(recent,dict):return _blocked("baseline and recent model metrics required",["baseline_metrics","recent_metrics"])
    metrics=("accuracy","brier_score","loss")
    drift={k:(_num(recent[k])-_num(baseline[k])) for k in metrics if baseline.get(k) is not None and recent.get(k) is not None}
    if not drift:return _blocked("no shared model metric",["shared_accuracy_or_loss_metric"])
    return _ready({"metric_deltas":drift,"drift_detected":any(abs(v)>0.1 for v in drift.values())},
                  "simple absolute metric-shift threshold; monitor only")


def _position_monitor(ctx):
    positions=ctx.get("positions");prices=ctx.get("current_prices")
    if not isinstance(positions,list) or not isinstance(prices,dict):return _blocked("paper positions and current marks required",["positions","current_prices"])
    output=[]
    for pos in positions:
        if not isinstance(pos,dict) or pos.get("status")!="OPEN":continue
        symbol=str(pos.get("symbol",""));mark=_num(prices.get(symbol))
        entry=_num(pos.get("entry"));qty=_num(pos.get("quantity"))
        if mark<=0 or entry<=0:continue
        pnl=(mark-entry)*qty if str(pos.get("side")).upper()=="LONG" else (entry-mark)*qty
        stop=_num(pos.get("stop_loss",pos.get("stopLoss")));target=_num(pos.get("take_profit",pos.get("takeProfit")))
        output.append({"symbol":symbol,"mark":mark,"unrealized_gross_pnl":pnl,
                       "stop_touched":bool(stop and ((mark<=stop) if pos.get("side")=="LONG" else (mark>=stop))),
                       "target_touched":bool(target and ((mark>=target) if pos.get("side")=="LONG" else (mark<=target)))})
    return _ready({"positions":output,"checked":len(output)},"read-only mark-to-market checks; no automatic order mutation")


def _knowledge_memory(ctx):
    events=ctx.get("opportunity_events")
    if not isinstance(events,list):return _blocked("persisted opportunity event history required",["opportunity_events"])
    counts={}
    for event in events:
        if isinstance(event,dict):
            key=str(event.get("event_type","unknown"));counts[key]=counts.get(key,0)+1
    return _ready({"event_count":len(events),"event_types":counts},
                  "read-only aggregation of persisted opportunity event history")


def _adaptive_router(ctx):
    regime=_regime_detector(ctx)
    if regime.get("status")!="computed":return regime
    name=regime["value"]["regime"]
    route="BREAKOUT_WATCH" if name=="LOW_VOLATILITY_RANGE" else "TREND_FOLLOW" if name=="TRENDING" else "RISK_REDUCTION"
    return _ready({"market_regime":name,"research_route":route,"automatic_strategy_promotion":False},
                  "rules-based research routing; does not execute or promote strategies")


def _duplicate_signal_filter(ctx):
    items=ctx.get("signals")
    if not isinstance(items,list):return _blocked("signal list with stable identifiers required",["signals"])
    seen=set();unique=[];duplicates=[]
    for item in items:
        if not isinstance(item,dict):continue
        key=(item.get("symbol"),item.get("category"),item.get("direction"),item.get("signal_time"))
        if key in seen:duplicates.append(key)
        else:seen.add(key);unique.append(item)
    return _ready({"unique_signals":unique,"duplicate_count":len(duplicates)},
                  "deduplication by symbol/category/direction/signal_time; persistence still required")




def _take_profit(ctx):
    plan=ctx.get("plan") or {}
    entry=_num(plan.get("entry")); stop=_num(plan.get("stop")); side=str(plan.get("side","LONG")).upper()
    if entry<=0 or stop<=0 or entry==stop or side not in ("LONG","SHORT"):
        return _blocked("valid entry, stop and side required",["plan.entry","plan.stop","plan.side"])
    risk=abs(entry-stop)
    ratios=ctx.get("reward_risk_targets") or [1.5,2.0,3.0]
    ratios=[_num(x) for x in ratios if _num(x)>0]
    if not ratios:return _blocked("positive reward/risk targets required",["reward_risk_targets"])
    targets=[entry+risk*x if side=="LONG" else entry-risk*x for x in ratios]
    return _ready({"entry":entry,"risk_distance":risk,"reward_risk_ratios":ratios,
                   "target_references":targets,"side":side},
                  "mechanical reward/risk target calculation; not a recommendation or order")


def _signal_expiration(ctx):
    from datetime import datetime, timezone
    created=ctx.get("signal_created_at"); now=ctx.get("now_utc")
    max_age=max(1,_num(ctx.get("max_age_seconds"),900))
    if not created or not now:return _blocked("signal timestamp and current UTC time required",["signal_created_at","now_utc"])
    try:
        created_at=datetime.fromisoformat(str(created).replace("Z","+00:00"))
        now_at=datetime.fromisoformat(str(now).replace("Z","+00:00"))
        if created_at.tzinfo is None or now_at.tzinfo is None:raise ValueError("timezone_required")
        age=(now_at-created_at).total_seconds()
    except (TypeError,ValueError):
        return _blocked("timestamps must be timezone-aware ISO-8601 values",["timezone_aware_signal_created_at","now_utc"])
    return _ready({"age_seconds":age,"max_age_seconds":max_age,"expired":age>max_age or age<0},
                  "UTC age check with explicit expiry threshold")


def _autonomous_research(ctx):
    candidates=ctx.get("strategy_candidates")
    if not isinstance(candidates,list) or not candidates:return _blocked("research strategy candidates and validation metrics required",["strategy_candidates"])
    evaluated=[]
    for item in candidates:
        if not isinstance(item,dict):continue
        train=_num(item.get("train_return")); validation=_num(item.get("validation_return"))
        dd=_num(item.get("validation_drawdown"),100)
        enough=int(_num(item.get("validation_trades")))>=30
        passed=validation>0 and dd<20 and enough and validation<=train+0.05
        evaluated.append({"name":str(item.get("name","unnamed")),"validation_return":validation,
                          "validation_drawdown":dd,"validation_trades":int(_num(item.get("validation_trades"))),
                          "research_gate_passed":passed,"promotion":"MANUAL_REVIEW_REQUIRED"})
    return _ready({"candidates":evaluated,"research_only":True},
                  "screening against supplied out-of-sample metrics; no autonomous promotion or deployment")


def _data_replay(ctx):
    events=ctx.get("replay_events")
    if not isinstance(events,list) or not events:return _blocked("timestamped replay events required",["replay_events"])
    valid=[x for x in events if isinstance(x,dict) and x.get("timestamp") is not None]
    return _ready({"ordered_events":sorted(valid,key=lambda x:str(x["timestamp"])),"event_count":len(valid)},
                  "stable timestamp ordering of supplied events; does not fetch historical venue packets")


def _audit_log(ctx):
    events=ctx.get("audit_events")
    if not isinstance(events,list):return _blocked("audit event records required",["audit_events"])
    ids=[str(x.get("event_id")) for x in events if isinstance(x,dict) and x.get("event_id")]
    return _ready({"events":len(events),"identified_events":len(ids),
                   "duplicate_event_ids":len(ids)-len(set(ids))},
                  "read-only audit event integrity check")


def _model_registry(ctx):
    models=ctx.get("model_versions")
    if not isinstance(models,list):return _blocked("registered model metadata required",["model_versions"])
    valid=[x for x in models if isinstance(x,dict) and x.get("name") and x.get("version")]
    return _ready({"registered_models":valid,"count":len(valid)},
                  "read-only model metadata inventory; no artifact loading or deployment")


def _resource_monitor(ctx):
    resources=ctx.get("resource_snapshot")
    if not isinstance(resources,dict):return _blocked("CPU, memory and worker metrics required",["resource_snapshot"])
    return _ready({"resources":resources,"pressure_detected":_num(resources.get("cpu_pct"))>=90 or _num(resources.get("memory_pct"))>=90},
                  "threshold alert on supplied runtime metrics")


def _watchdog(ctx):
    heartbeats=ctx.get("heartbeats")
    if not isinstance(heartbeats,dict) or not heartbeats:return _blocked("service heartbeat timestamps required",["heartbeats"])
    max_age=max(1,_num(ctx.get("heartbeat_max_age_seconds"),60))
    ages={k:_num(v.get("age_seconds"),float("inf")) if isinstance(v,dict) else float("inf") for k,v in heartbeats.items()}
    stale=[k for k,v in ages.items() if v>max_age]
    return _ready({"heartbeat_ages_seconds":ages,"stale_services":stale,"watchdog_alert":bool(stale)},
                  "read-only heartbeat age check; does not restart external services")


def _event_bus(ctx):
    stats=ctx.get("event_bus")
    if not isinstance(stats,dict):return _blocked("event-bus counters required",["event_bus"])
    published=int(_num(stats.get("published"))); consumed=int(_num(stats.get("consumed")))
    return _ready({"published":published,"consumed":consumed,"backlog":max(0,published-consumed)},
                  "read-only event-bus counters supplied by runtime")


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
    train,test,means,scales=_standardize(dataset[:split],dataset[split:])
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
    latest=[(dataset[-1][0][j]-means[j])/scales[j] for j in range(inputs)]
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
    split=max(30,int(len(transitions)*0.8));training=transitions[:split];testing=transitions[split:]
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
    "E046":_deep_learning_mlp,
    "E049":_rl_agent,
    "E008":_cross_market_correlation,
    "E014":_order_block,
    "E046":_external,
    "E047":_external,
    "E048":_external,
    "E049":_external,
    "E050":_external,
    "E063":_liquidation_heatmap,
    "E069":_options_analytics,
    "E070":_implied_volatility_engine,
    "E071":_gamma_exposure,
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
})
# All remaining catalogue IDs still have a callable, fail-closed adapter.
for _catalogue_item in ENGINE_CATALOG:
    _HANDLER_IDS.setdefault(_catalogue_item["id"], _external)


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
    return {"engine_id":engine_id,"name":item["name"],"group":item["group"],
            "catalog_status":item["status"],"runtime":value,
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
    active_adapters=sorted(routed-set(external_only))
    status_counts={status:sum(1 for x in ENGINE_CATALOG if x["status"]==status)
                   for status in ("implemented","partial","planned")}
    return {
        "catalogue_engines":len(all_ids),
        "routed_adapters":len(routed),
        "callable_adapter_coverage_pct":round(len(routed)/len(all_ids)*100,2) if all_ids else 0,
        "active_runtime_adapters":len(active_adapters),
        "external_or_model_blocked_adapters":len(external_only),
        "external_or_model_blocked_ids":external_only,
        "unrouted_adapters":sorted(all_ids-routed),
        "catalogue_status_counts":status_counts,
        "trading_mode":"simulation","live_trading_enabled":False,
        "note":"A callable adapter may still return blocked_missing_input when its market feed, portfolio record or runtime snapshot is absent."
    }
