"""Transparent quantitative helpers for QUANT NEXUS.

This module intentionally contains deterministic, explainable calculations.
It is not a predictive guarantee and never sends exchange orders.
"""
from __future__ import annotations

import math
from typing import Any


def ema_series(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be positive")
    output: list[float | None] = [None] * len(values)
    if len(values) < period:
        return output
    current = sum(values[:period]) / period
    output[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = values[index] * alpha + current * (1.0 - alpha)
        output[index] = current
    return output


def average_true_range(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    if period < 1 or len(candles) < period + 1:
        return None
    ranges: list[float] = []
    previous_close = float(candles[0]["close"])
    for candle in candles[1:]:
        high = float(candle["high"])
        low = float(candle["low"])
        close = float(candle["close"])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        previous_close = close
    if len(ranges) < period:
        return None
    # Wilder smoothing: seed with a simple average, then smooth the remaining bars.
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = ((value * (period - 1)) + current) / period
    return value


def enrich_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Attach transparent rationale and volatility/risk context to an analysis."""
    candles = analysis.get("candles") or []
    atr = average_true_range(candles)
    price = float(analysis.get("price") or 0.0)
    score = int(analysis.get("score") or 0)
    direction = analysis.get("direction", "NEUTRAL")
    volume_ratio = analysis.get("volumeRatio")
    reasons: list[str] = []
    if analysis.get("ema20") is not None and price:
        reasons.append("السعر أعلى من EMA20" if price > analysis["ema20"] else "السعر أدنى من EMA20")
    if analysis.get("ema20") is not None and analysis.get("ema50") is not None:
        reasons.append("EMA20 أعلى من EMA50" if analysis["ema20"] > analysis["ema50"] else "EMA20 أدنى من EMA50")
    if analysis.get("macdHistogram") is not None:
        reasons.append("زخم MACD إيجابي" if analysis["macdHistogram"] > 0 else "زخم MACD سلبي")
    if analysis.get("vwap") is not None and price:
        reasons.append("السعر أعلى من VWAP" if price > analysis["vwap"] else "السعر أدنى من VWAP")
    if volume_ratio is not None:
        reasons.append("حجم تداول أعلى من المتوسط" if volume_ratio >= 1.5 else "الحجم دون تأكيد استثنائي")
    if direction == "NEUTRAL":
        classification = "WAIT"
    elif score >= 75:
        classification = "STRONG"
    elif score >= 55:
        classification = "NEEDS_CONFIRMATION"
    else:
        classification = "HIGH_RISK"
    stop = analysis.get("stopLoss")
    risk_pct = (abs(price - float(stop)) / price * 100.0) if price > 0 and stop else None
    analysis["atr14"] = atr
    analysis["atrPercent"] = round(atr / price * 100.0, 4) if atr is not None and price > 0 else None
    analysis["riskPercent"] = round(risk_pct, 4) if risk_pct is not None else None
    analysis["classification"] = classification
    analysis["reasons"] = reasons
    analysis["riskReward"] = 1.5 if analysis.get("target1") and stop else None
    return analysis


def ema_crossover_backtest(
    candles: list[dict[str, Any]],
    *,
    starting_balance: float = 10_000.0,
    position_fraction: float = 0.20,
    fast_period: int = 10,
    slow_period: int = 30,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Long-only EMA crossover backtest, entries/exits filled on the next bar.

    Signal calculation uses the completed candle at index i and fills at the
    next candle open, avoiding same-bar look-ahead. Fees and slippage are
    charged on both sides. Results are illustrative and are not live signals.
    """
    if not math.isfinite(starting_balance) or starting_balance <= 0:
        raise ValueError("starting_balance must be positive")
    if not 0 < position_fraction <= 1:
        raise ValueError("position_fraction must be in (0, 1]")
    if fast_period < 2 or slow_period <= fast_period:
        raise ValueError("slow_period must be greater than fast_period >= 2")
    if fee_bps < 0 or slippage_bps < 0:
        raise ValueError("fees and slippage cannot be negative")
    closes = [float(c["close"]) for c in candles]
    opens = [float(c["open"]) for c in candles]
    if any(not math.isfinite(x) or x <= 0 for x in closes + opens):
        raise ValueError("candle prices must be finite and positive")
    fast = ema_series(closes, fast_period)
    slow = ema_series(closes, slow_period)
    equity = float(starting_balance)
    peak = equity
    max_drawdown = 0.0
    trades: list[dict[str, float | str]] = []
    position: dict[str, float] | None = None
    fee_rate = fee_bps / 10_000.0
    slip_rate = slippage_bps / 10_000.0

    for index in range(slow_period, len(candles) - 1):
        if fast[index - 1] is None or slow[index - 1] is None or fast[index] is None or slow[index] is None:
            continue
        cross_up = fast[index - 1] <= slow[index - 1] and fast[index] > slow[index]
        cross_down = fast[index - 1] >= slow[index - 1] and fast[index] < slow[index]
        next_open = opens[index + 1]
        if position is None and cross_up:
            fill = next_open * (1.0 + slip_rate)
            notional = equity * position_fraction
            units = notional / fill
            entry_fee = notional * fee_rate
            equity -= entry_fee
            position = {"entry": fill, "units": units, "entry_fee": entry_fee}
        elif position is not None and cross_down:
            fill = next_open * (1.0 - slip_rate)
            gross = (fill - position["entry"]) * position["units"]
            exit_fee = fill * position["units"] * fee_rate
            net = gross - position["entry_fee"] - exit_fee
            equity += gross - exit_fee
            trades.append({"entry": position["entry"], "exit": fill, "net_pnl": net, "return_pct": net / (position["entry"] * position["units"]) * 100.0})
            position = None
        mark_equity = equity
        if position is not None:
            unrealized = (closes[index] - position["entry"]) * position["units"]
            estimated_exit_fee = closes[index] * position["units"] * fee_rate
            mark_equity += unrealized - estimated_exit_fee
        peak = max(peak, mark_equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - mark_equity) / peak * 100.0)

    if position is not None and candles:
        fill = closes[-1] * (1.0 - slip_rate)
        gross = (fill - position["entry"]) * position["units"]
        exit_fee = fill * position["units"] * fee_rate
        net = gross - position["entry_fee"] - exit_fee
        equity += gross - exit_fee
        trades.append({"entry": position["entry"], "exit": fill, "net_pnl": net, "return_pct": net / (position["entry"] * position["units"]) * 100.0})
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)

    wins = [float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) > 0]
    losses = [float(t["net_pnl"]) for t in trades if float(t["net_pnl"]) < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_profit = equity - starting_balance
    return {
        "strategy": "EMA_CROSSOVER_LONG_ONLY",
        "parameters": {"fast": fast_period, "slow": slow_period, "positionFraction": position_fraction, "feeBps": fee_bps, "slippageBps": slippage_bps},
        "startingBalance": round(starting_balance, 8),
        "endingBalance": round(equity, 8),
        "netProfit": round(net_profit, 8),
        "returnPct": round(net_profit / starting_balance * 100.0, 4),
        "tradeCount": len(trades),
        "winRatePct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "profitFactor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else (None if gross_profit == 0 else "infinite"),
        "maxDrawdownPct": round(max_drawdown, 4),
        "trades": trades[-100:],
        "sampleBars": len(candles),
        "disclaimer": "Historical simulation only; not a prediction or live trading instruction.",
    }
