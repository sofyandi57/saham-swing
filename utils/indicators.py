"""Lightweight swing-trading helpers: ATR, fractal swing points, S/R clustering
and a simple rule-based entry/stop/target plan built on top of them.

Educational use only - not a substitute for the user's own judgement.
"""
from __future__ import annotations

import pandas as pd


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return df


def swing_points(df: pd.DataFrame, window: int = 3) -> tuple[list[float], list[float]]:
    """Fractal swing highs/lows: a bar wins if it's the extreme within +/-window bars."""
    highs, lows = [], []
    n = len(df)
    for i in range(window, n - window):
        seg_high = df["high"].iloc[i - window : i + window + 1]
        seg_low = df["low"].iloc[i - window : i + window + 1]
        if df["high"].iloc[i] == seg_high.max():
            highs.append(float(df["high"].iloc[i]))
        if df["low"].iloc[i] == seg_low.min():
            lows.append(float(df["low"].iloc[i]))
    return highs, lows


def cluster_levels(prices: list[float], tolerance_pct: float = 1.5) -> list[dict]:
    """Merge nearby prices into levels, counting touches as a rough strength score."""
    if not prices:
        return []
    levels: list[dict] = []
    for p in sorted(prices):
        placed = False
        for lv in levels:
            if abs(p - lv["level"]) / lv["level"] * 100 <= tolerance_pct:
                lv["touches"] += 1
                lv["level"] = (lv["level"] * (lv["touches"] - 1) + p) / lv["touches"]
                placed = True
                break
        if not placed:
            levels.append({"level": p, "touches": 1})
    return levels


def support_resistance(
    df: pd.DataFrame, window: int = 3, tolerance_pct: float = 1.5, max_levels: int = 6
) -> tuple[list[dict], list[dict]]:
    highs, lows = swing_points(df, window=window)
    last_close = float(df["close"].iloc[-1])

    resistance_levels = [
        lv for lv in cluster_levels(highs, tolerance_pct) if lv["level"] > last_close
    ]
    support_levels = [
        lv for lv in cluster_levels(lows, tolerance_pct) if lv["level"] < last_close
    ]

    resistance_levels.sort(key=lambda x: x["level"])
    support_levels.sort(key=lambda x: -x["level"])

    return support_levels[:max_levels], resistance_levels[:max_levels]


def build_trading_plan(
    df: pd.DataFrame, atr_period: int = 14, swing_window: int = 3, tolerance_pct: float = 1.5
) -> dict:
    """Rule-based swing entry/stop/target using ATR + fractal S/R.

    Not investment advice - purely a structured read of recent price action.
    """
    df = add_atr(df, period=atr_period)
    entry = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1]) if pd.notna(df["atr"].iloc[-1]) else None

    supports, resistances = support_resistance(df, window=swing_window, tolerance_pct=tolerance_pct)

    atr_stop_dist = atr * 1.5 if atr else entry * 0.05
    if supports:
        candidate_stop = supports[0]["level"]
        # don't let the stop sit basically on top of entry
        if entry - candidate_stop < atr_stop_dist * 0.4:
            candidate_stop = entry - atr_stop_dist
        stop = candidate_stop
    else:
        stop = entry - atr_stop_dist

    risk = max(entry - stop, entry * 0.01)

    if resistances:
        target1 = resistances[0]["level"]
        target2 = resistances[1]["level"] if len(resistances) > 1 else entry + 3 * risk
    else:
        target1 = entry + 2 * risk
        target2 = entry + 3 * risk

    return {
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "risk": risk,
        "rr1": (target1 - entry) / risk if risk else None,
        "rr2": (target2 - entry) / risk if risk else None,
        "atr": atr,
        "supports": supports,
        "resistances": resistances,
    }


def position_size(capital: float, risk_pct: float, entry: float, stop: float, lot_size: int = 100) -> dict:
    """IDX-style position sizing in lots (1 lot = 100 shares by default)."""
    risk_amount = capital * (risk_pct / 100)
    per_share_risk = max(entry - stop, 0.0001)
    shares = risk_amount / per_share_risk
    lots = int(shares // lot_size)
    shares_actual = lots * lot_size
    cost = shares_actual * entry
    actual_risk = shares_actual * per_share_risk
    return {
        "lots": lots,
        "shares": shares_actual,
        "cost": cost,
        "actual_risk": actual_risk,
    }
