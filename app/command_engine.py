"""Command-driven scanner rules and entry confirmation for QUANT NEXUS.

Rules are transparent filters over completed-candle analysis. They are not predictions.
"""
from __future__ import annotations

COMMANDS = [
 {"id":"trend_up","name":"عملات في قناة سعرية / ترند صاعد","group":"الاتجاه","icon":"📈","description":"EMA20 أعلى EMA50 والسعر فوقهما","rule":"uptrend"},
 {"id":"trend_down","name":"تحديد الاتجاه الهابط","group":"الاتجاه","icon":"📉","description":"EMA20 أدنى EMA50 والسعر تحتهما","rule":"downtrend"},
 {"id":"near_support","name":"مناطق ارتداد متوقعة من الدعم","group":"المستويات","icon":"🧲","description":"السعر قريب من الدعم ضمن 1%","rule":"near_support"},
 {"id":"near_resistance","name":"هل السعر قريب من أرضية/مقاومة قوية؟","group":"المستويات","icon":"🔧","description":"السعر قريب من المقاومة ضمن 1%","rule":"near_resistance"},
 {"id":"breakout_up","name":"اختراق القناة السعرية وتحديد الاتجاه","group":"الاختراق","icon":"🧰","description":"إغلاق آخر شمعة مكتملة فوق نطاقها المرجعي","rule":"breakout_up"},
 {"id":"breakout_down","name":"كسر النطاق (BK)","group":"الاختراق","icon":"⚙️","description":"إغلاق آخر شمعة مكتملة أسفل نطاقها المرجعي","rule":"breakout_down"},
 {"id":"retest","name":"إعادة اختبار ناجحة (فرص مضاربة)","group":"الاختراق","icon":"📌","description":"اختراق حديث مع عودة السعر قرب المستوى المخترق","rule":"retest"},
 {"id":"tight_range","name":"مسار شموع ضيق لاحتمالية الانفجار السعري","group":"الزخم","icon":"🔑","description":"تضيق النطاق مع انخفاض ATR النسبي","rule":"tight_range"},
 {"id":"volume_surge","name":"عملات يزداد فيها السيولة آخر دقائق","group":"السيولة","icon":"💹","description":"حجم آخر شمعة أعلى من متوسطه بوضوح","rule":"volume_surge"},
 {"id":"volume_dry","name":"عملات دخلت مرحلة التبريد","group":"السيولة","icon":"🚀","description":"هبوط نسبة الحجم إلى أقل من المتوسط","rule":"volume_dry"},
 {"id":"momentum_up","name":"الاقتراب من بداية انعكاس الاتجاه","group":"الزخم","icon":"✨","description":"تحسن RSI وMACD مع اتجاه صاعد أولي","rule":"momentum_up"},
 {"id":"momentum_down","name":"فقدان الزخم واحتمال انعكاس هابط","group":"الزخم","icon":"🧠","description":"تراجع RSI وMACD مع اتجاه هابط أولي","rule":"momentum_down"},
 {"id":"rsi_oversold","name":"هل العملة نزلت طبيعي ولا متصرفة بقوة؟","group":"الزخم","icon":"✨","description":"RSI منخفض دون افتراض انعكاس مؤكد","rule":"rsi_oversold"},
 {"id":"rsi_overbought","name":"هل العملة متشبعة صعوداً؟","group":"الزخم","icon":"✨","description":"RSI مرتفع ويحتاج حذراً","rule":"rsi_overbought"},
 {"id":"liquid_market","name":"عملات ذات سيولة مرتفعة","group":"السيولة","icon":"💧","description":"سيولة تداول يومية مرتفعة نسبياً","rule":"liquid_market"},
 {"id":"delayed_move","name":"هل هناك تأخر؟","group":"السوق","icon":"🗂️","description":"تضيق نطاق مع قرب السعر من حافته","rule":"delayed_move"},
 {"id":"risk_reward","name":"مخاطرة/عائد جاهزة (R:R)","group":"المخاطر","icon":"📌","description":"وجود دخول ووقف وهدف بنسبة عائد/مخاطرة لا تقل عن 1.5","rule":"risk_reward"},
 {"id":"low_risk","name":"أقرب فرصة بمخاطرة منخفضة","group":"المخاطر","icon":"✨","description":"مخاطرة سعرية تقديرية لا تتجاوز 1.2%","rule":"low_risk"},
 {"id":"large_range","name":"عملات نشطة ذات حركة قوية","group":"السوق","icon":"⚡","description":"ATR النسبي أعلى من 1%","rule":"large_range"},
 {"id":"stable_range","name":"عملات مقاومة تاريخية وثبات نطاق","group":"السوق","icon":"🧩","description":"نطاق حديث ضيق نسبياً","rule":"stable_range"},
 {"id":"price_above_vwap","name":"السعر فوق VWAP","group":"الاتجاه","icon":"🧩","description":"السعر أعلى من متوسط السعر المرجح بالحجم","rule":"above_vwap"},
 {"id":"price_below_vwap","name":"السعر أسفل VWAP","group":"الاتجاه","icon":"🧩","description":"السعر أسفل متوسط السعر المرجح بالحجم","rule":"below_vwap"},
 {"id":"macd_bull","name":"كشف النماذج الكلاسيكية / زخم إيجابي","group":"الزخم","icon":"🧰","description":"هيستوغرام MACD إيجابي","rule":"macd_bull"},
 {"id":"macd_bear","name":"زخم سلبي / ضغط بيع","group":"الزخم","icon":"🧰","description":"هيستوغرام MACD سلبي","rule":"macd_bear"},
 {"id":"best3","name":"أفضل 3 مناطق بين دعم ومقاومة","group":"المستويات","icon":"🔧","description":"فرص اتجاهية ذات درجة فنية مرتفعة","rule":"best3"},
 {"id":"fast_movers","name":"عملات تتحرك فيها بسرعة","group":"السوق","icon":"🏃","description":"تغير يومي مطلق يتجاوز 3%","rule":"fast_movers"},
]

_RULES = {item["id"]: item["rule"] for item in COMMANDS}

def matches_command(item: dict, command_id: str) -> bool:
    rule = _RULES.get(command_id)
    if not rule:
        return False
    price = float(item.get("price") or 0)
    rsi = item.get("rsi")
    volume = item.get("volumeRatio")
    atr_pct = item.get("atrPercent")
    ema20, ema50 = item.get("ema20"), item.get("ema50")
    macd = item.get("macdHistogram")
    support, resistance = item.get("support"), item.get("resistance")
    change = abs(float(item.get("change24h") or 0))
    if rule == "uptrend": return bool(price and ema20 and ema50 and price > ema20 > ema50)
    if rule == "downtrend": return bool(price and ema20 and ema50 and price < ema20 < ema50)
    if rule == "near_support": return bool(price and support and 0 <= (price-support)/price <= .01)
    if rule == "near_resistance": return bool(price and resistance and 0 <= (resistance-price)/price <= .01)
    if rule == "breakout_up": return item.get("breakout") == "UP"
    if rule == "breakout_down": return item.get("breakout") == "DOWN"
    if rule == "retest": return item.get("breakout") == "UP" and bool(support and price >= support and (price-support)/price <= .012)
    if rule in ("tight_range","stable_range","delayed_move"):
        candles=item.get("candles") or []
        if len(candles)<20 or not price: return False
        recent=candles[-20:]
        width=(max(float(c["high"]) for c in recent)-min(float(c["low"]) for c in recent))/price
        return width <= (.025 if rule != "delayed_move" else .018)
    if rule == "volume_surge": return volume is not None and volume >= 1.5
    if rule == "volume_dry": return volume is not None and volume <= .65
    if rule == "momentum_up": return bool(rsi is not None and 48 <= rsi <= 65 and macd is not None and macd > 0 and item.get("direction") == "LONG")
    if rule == "momentum_down": return bool(rsi is not None and 35 <= rsi <= 52 and macd is not None and macd < 0 and item.get("direction") == "SHORT")
    if rule == "rsi_oversold": return rsi is not None and rsi <= 30
    if rule == "rsi_overbought": return rsi is not None and rsi >= 70
    if rule == "liquid_market": return float(item.get("turnover24h") or 0) >= 5_000_000
    if rule == "risk_reward": return bool(item.get("entry") and item.get("stopLoss") and item.get("target1") and item.get("direction") != "NEUTRAL" and float(item.get("riskReward") or 0) >= 1.5)
    if rule == "low_risk": return item.get("riskPercent") is not None and item["riskPercent"] <= 1.2
    if rule == "large_range": return atr_pct is not None and atr_pct >= 1
    if rule == "above_vwap": return bool(item.get("vwap") and price > item["vwap"])
    if rule == "below_vwap": return bool(item.get("vwap") and price < item["vwap"])
    if rule == "macd_bull": return macd is not None and macd > 0
    if rule == "macd_bear": return macd is not None and macd < 0
    if rule == "best3": return float(item.get("score") or 0) >= 70 and item.get("direction") in ("LONG","SHORT")
    if rule == "fast_movers": return change >= 3
    return False

def evaluate_entry(item: dict) -> dict:
    """Confirm on the last completed candle only; otherwise keep the setup pending."""
    direction=item.get("direction","NEUTRAL")
    price=float(item.get("price") or 0)
    score=float(item.get("score") or 0)
    rsi=item.get("rsi")
    ema20,ema50=item.get("ema20"),item.get("ema50")
    macd=item.get("macdHistogram")
    volume=item.get("volumeRatio")
    breakout=item.get("breakout")
    if direction == "NEUTRAL" or not price:
        return {"state":"WAITING","confirmed":False,"progress":0,"reason":"الاتجاه غير محسوم؛ ننتظر اكتمال الشروط"}
    bullish = direction=="LONG" and ema20 and ema50 and price>ema20>ema50 and rsi is not None and 50<=rsi<=70 and macd is not None and macd>0 and (breakout=="UP" or (volume is not None and volume>=1.25))
    bearish = direction=="SHORT" and ema20 and ema50 and price<ema20<ema50 and rsi is not None and 30<=rsi<=50 and macd is not None and macd<0 and (breakout=="DOWN" or (volume is not None and volume>=1.25))
    if bullish or bearish:
        return {"state":"CONFIRMED","confirmed":True,"progress":100,"reason":"اتجاه المتوسطات والزخم وRSI متوافقة مع إغلاق الشمعة المكتملة"}
    if score>=65 and direction in ("LONG","SHORT"):
        return {"state":"APPROACH","confirmed":False,"progress":65,"reason":"الدرجة مرتفعة لكن شرط تأكيد واحد أو أكثر غير مكتمل"}
    return {"state":"WAITING","confirmed":False,"progress":25,"reason":"الإشارة تحت المراقبة؛ لا دخول قبل التأكيد"}
