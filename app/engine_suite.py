"""Runtime adapters for the 156-engine QUANT NEXUS catalogue.

Every catalogue entry has a callable contract. A result is either computed from
provided, validated evidence or explicitly blocked because its required input
(model artifact, provider feed, portfolio data, etc.) is absent. No fabricated
market data, probabilities, or orders are produced.
"""
from __future__ import annotations

from math import exp, isfinite, sqrt
import random
from statistics import mean, median, pstdev
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


# Each catalogue engine is routable. Similar engines share audited mathematical primitives,
# while model- and provider-dependent engines remain explicitly blocked when inputs are absent.
_HANDLER_IDS = {
    "E005":_base, "E006":_base, "E008":_external,
    "E009":_trend, "E011":_support_resistance, "E012":_accumulation,
    "E013":_sweep, "E014":_sweep, "E015":_fvg, "E016":_breakout,
    "E017":_divergence, "E019":_candlestick, "E020":_fibonacci,
    "E022":_volume_profile, "E023":_divergence, "E024":_candlestick,
    "E026":_higher_timeframe, "E027":_lower_timeframe, "E028":_regime_timeframe_sync, "E029":_market_phase,
    "E030":_timing, "E031":_timing, "E032":_momentum,
    "E034":_early_breakout, "E035":_accumulation, "E036":_sweep,
    "E037":_momentum_explosion, "E038":_whale_activity, "E039":_volume, "E040":_compression,
    "E042":_breakout, "E043":_external,
    "E044":_ai_analyst, "E045":_logistic_model, "E046":_external, "E047":_external,
    "E048":_external, "E049":_external, "E050":_external, "E051":_random_forest,
    "E052":_anomaly_detection, "E053":_clustering, "E054":_market_phase, "E055":_forecast,
    "E056":_empirical_probability, "E057":_ensemble, "E058":_logistic_model, "E059":_explain_model,
    "E060":_derivatives, "E061":_derivatives, "E062":_derivatives,
    "E063":_external, "E064":_external, "E065":_external, "E066":_external,
    "E067":_risk, "E068":_derivatives, "E069":_external, "E070":_external, "E071":_external,
    "E073":_external, "E074":_risk, "E075":_risk, "E076":_risk, "E077":_risk,
    "E078":_external, "E079":_external, "E080":_breakout, "E081":_external,
    "E082":_external, "E083":_external, "E084":_backtest, "E085":_external,
    "E086":_risk, "E087":_risk, "E088":_portfolio, "E089":_portfolio,
    "E090":_portfolio, "E091":_portfolio, "E092":_risk, "E093":_external,
    "E094":_external, "E095":_risk, "E096":_risk, "E097":_risk,
    "E098":_risk, "E099":_external, "E100":_risk,
    "E102":_backtest, "E104":_external, "E105":_external, "E106":_external,
    "E107":_external, "E108":_external, "E109":_backtest, "E110":_backtest,
    "E111":_backtest, "E112":_backtest, "E113":_external, "E114":_external, "E115":_external,
    "E116":_portfolio, "E117":_portfolio, "E118":_external, "E119":_portfolio,
    "E120":_portfolio, "E121":_external, "E122":_external, "E123":_external,
    "E124":_backtest, "E125":_portfolio,
    "E127":_agents, "E128":_orderbook, "E129":_sweep, "E130":_derivatives,
    "E131":_trend, "E132":_external, "E133":_risk, "E134":_external,
    "E135":_agents, "E136":_agents, "E137":_agents, "E138":_external, "E139":_external, "E140":_external,
    "E141":_external, "E142":_external, "E143":_external, "E144":_external,
    "E145":_external, "E146":_external, "E147":_external, "E148":_external,
    "E149":_external, "E150":_external, "E151":_external, "E152":_external,
    "E153":_external, "E154":_external, "E155":_external, "E156":_external,
}


_HANDLER_IDS.update({
    "E001":_base,"E002":_orderbook,"E003":_orderbook,"E004":_compression,
    "E007":_external,"E008":_cross_market_correlation,"E010":_market_structure,
    "E018":_momentum,"E021":_vwap,"E025":_timeframes,"E033":_opportunity,
    "E041":_opportunity,"E043":_arbitrage,"E062":_long_short,"E064":_liquidation_tracker,
    "E065":_basis,"E066":_derivatives,"E072":_generic_score,"E073":_generic_score,
    "E075":_risk,"E078":_generic_score,"E081":_generic_score,"E082":_generic_score,
    "E083":_external,"E085":_generic_score,"E089":_portfolio,"E090":_portfolio,
    "E093":_risk,"E094":_risk,"E097":_risk,"E099":_system_health,
    "E101":_backtest,"E103":_paper_positions,"E104":_backtest,"E105":_backtest,
    "E106":_backtest,"E107":_backtest,"E108":_backtest,"E110":_backtest,
    "E111":_backtest,"E112":_backtest,"E113":_backtest,"E114":_backtest,
    "E115":_backtest,"E118":_paper_positions,"E121":_paper_positions,
    "E122":_paper_positions,"E123":_paper_positions,"E126":_agents,
    "E127":_agents,"E129":_sweep,"E131":_trend,"E132":_external,
    "E133":_risk,"E134":_agents,"E135":_agents,"E136":_agents,
    "E137":_agents,"E138":_external,"E139":_agents,"E140":_agents,
    "E141":_system_health,"E142":_system_health,"E143":_system_health,
    "E144":_system_health,"E145":_system_health,"E146":_system_health,
    "E147":_system_health,"E148":_system_health,"E149":_system_health,
    "E150":_system_health,"E151":_system_health,"E152":_system_health,
    "E153":_system_health,"E154":_system_health,"E155":_system_health,
    "E156":_system_health,
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
    return {"catalogue_engines":len(all_ids),"routed_adapters":len(routed),
            "unrouted_adapters":sorted(all_ids-routed),
            "requires_external_or_model_inputs":sum(_HANDLER_IDS.get(x) is _external for x in routed),
            "trading_mode":"simulation","live_trading_enabled":False}
