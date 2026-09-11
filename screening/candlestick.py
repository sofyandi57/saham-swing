"""Candlestick pattern recognition — categorical field `candlestick_pattern`
from the Field Registry (skema-query-screening-engine.md §1, footnote on §7.4/7.5).

Unlike numeric fields this isn't a simple column: `detect_last_patterns(df)`
returns the set of pattern names matched by the most recent bar(s). The
condition tree treats `candlestick_pattern == "<name>"` as a membership test
against that set (see condition_tree.py).
"""
from __future__ import annotations

import pandas as pd

PATTERNS = ["hammer", "bullish_engulfing", "dragonfly_doji", "inside_day_break"]


def _is_hammer(o, h, l, c) -> bool:
    body = abs(c - o)
    rng = h - l
    if rng <= 0:
        return False
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    return lower_shadow >= 2 * body and upper_shadow <= 0.3 * body if body > 0 else lower_shadow >= 0.6 * rng


def _is_dragonfly_doji(o, h, l, c) -> bool:
    rng = h - l
    if rng <= 0:
        return False
    body = abs(c - o)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    return body <= 0.05 * rng and lower_shadow >= 0.6 * rng and upper_shadow <= 0.1 * rng


def _is_bullish_engulfing(prev, cur) -> bool:
    prev_bearish = prev["close"] < prev["open"]
    cur_bullish = cur["close"] > cur["open"]
    engulfs = cur["open"] <= prev["close"] and cur["close"] >= prev["open"]
    return bool(prev_bearish and cur_bullish and engulfs)


def _is_inside_day_break(mother, inside, breakout) -> bool:
    is_inside = inside["high"] <= mother["high"] and inside["low"] >= mother["low"]
    breaks_up = breakout["close"] > inside["high"]
    return bool(is_inside and breaks_up)


def detect_last_patterns(df: pd.DataFrame) -> set[str]:
    """Patterns matched by the most recent bar(s) of an OHLC DataFrame."""
    if len(df) < 1:
        return set()
    found: set[str] = set()
    last = df.iloc[-1]

    if _is_hammer(last["open"], last["high"], last["low"], last["close"]):
        found.add("hammer")
    if _is_dragonfly_doji(last["open"], last["high"], last["low"], last["close"]):
        found.add("dragonfly_doji")
    if len(df) >= 2 and _is_bullish_engulfing(df.iloc[-2], last):
        found.add("bullish_engulfing")
    if len(df) >= 3 and _is_inside_day_break(df.iloc[-3], df.iloc[-2], last):
        found.add("inside_day_break")

    return found
