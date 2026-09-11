"""Field Registry (technical part) — see skema-query-screening-engine.md §1.

Given a daily OHLCV DataFrame (columns: date, open, high, low, close, volume),
`enrich(df)` adds every technical field_id from the registry as a column, so
the condition tree evaluator can just look columns up by name.

`value` (transaction value) isn't returned by Invezgo's chart endpoint, so we
approximate it as close*volume — good enough for a liquidity threshold, not
exact turnover.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_smooth(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder_smooth(gain, period)
    avg_loss = _wilder_smooth(loss, period)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100).where(avg_loss != 0, 100)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return _wilder_smooth(tr, period)


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = _wilder_smooth(tr, period)
    plus_di = 100 * _wilder_smooth(pd.Series(plus_dm, index=df.index), period) / atr.replace(0, np.nan)
    minus_di = 100 * _wilder_smooth(pd.Series(minus_dm, index=df.index), period) / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return _wilder_smooth(dx.fillna(0), period)


def _obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0))
    return (direction * df["volume"]).cumsum()


def _donchian(df: pd.DataFrame, period: int = 20) -> tuple[pd.Series, pd.Series]:
    upper = df["high"].rolling(period, min_periods=period).max()
    lower = df["low"].rolling(period, min_periods=period).min()
    return upper, lower


def _anchored_vwap(df: pd.DataFrame, anchor_idx: int = 0) -> pd.Series:
    """VWAP anchored at row `anchor_idx` (default: start of the fetched window)."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    tp_vol = typical * df["volume"]
    out = pd.Series(np.nan, index=df.index, dtype=float)
    cum_tp_vol = tp_vol.iloc[anchor_idx:].cumsum()
    cum_vol = df["volume"].iloc[anchor_idx:].cumsum().replace(0, np.nan)
    out.iloc[anchor_idx:] = cum_tp_vol / cum_vol
    return out


def enrich(df: pd.DataFrame, anchor_idx: int = 0) -> pd.DataFrame:
    """Return a copy of `df` with every registry technical field added as a column."""
    df = df.sort_values("date").reset_index(drop=True).copy()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)

    df["value"] = df["close"] * df["volume"]
    df["avg_value_20d"] = _sma(df["value"], 20)

    for n in (20, 50, 100, 200):
        df[f"sma{n}"] = _sma(df["close"], n)
    for n in (9, 12, 21, 26):
        df[f"ema{n}"] = _ema(df["close"], n)

    ema12 = df["ema12"] if "ema12" in df else _ema(df["close"], 12)
    ema26 = df["ema26"] if "ema26" in df else _ema(df["close"], 26)
    df["macd"] = ema12 - ema26
    df["macd_signal"] = _ema(df["macd"].fillna(0), 9)
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)
    df["adx14"] = _adx(df, 14)

    df["donchian20_upper"], df["donchian20_lower"] = _donchian(df, 20)
    df["obv"] = _obv(df)
    df["volume_spike_ratio"] = df["volume"] / _sma(df["volume"], 20).replace(0, np.nan)
    df["anchored_vwap"] = _anchored_vwap(df, anchor_idx)

    df["roc10"] = df["close"].pct_change(10) * 100
    df["obv_slope"] = df["obv"].diff(5)

    # Derived helper fields (§9 extensibility rule) — the grammar only
    # compares a field to a literal or to another field's raw value, so
    # "within +/-2 ATR of X" or "range narrowing vs before" need a
    # precomputed distance/ratio column rather than an inline expression.
    atr_safe = df["atr14"].replace(0, np.nan)
    df["donchian20_width_pct"] = (df["donchian20_upper"] - df["donchian20_lower"]) / df["close"] * 100
    df["dist_to_vwap_atr"] = (df["close"] - df["anchored_vwap"]) / atr_safe
    df["dist_to_ema21_atr"] = (df["close"] - df["ema21"]) / atr_safe
    df["low_dist_to_ema21_atr"] = (df["low"] - df["ema21"]) / atr_safe
    df["dist_to_support_pct"] = (df["close"] - df["donchian20_lower"]) / df["donchian20_lower"] * 100

    df = df.set_index(pd.to_datetime(df["date"]).dt.normalize())
    return df


TECHNICAL_FIELDS = [
    "close", "high", "low", "volume", "value",
    "sma20", "sma50", "sma100", "sma200",
    "ema9", "ema12", "ema21", "ema26",
    "macd", "macd_signal", "macd_hist",
    "rsi14", "atr14", "adx14",
    "donchian20_upper", "donchian20_lower",
    "obv", "volume_spike_ratio", "anchored_vwap", "avg_value_20d",
    "roc10", "obv_slope",
    "donchian20_width_pct", "dist_to_vwap_atr", "dist_to_ema21_atr",
    "low_dist_to_ema21_atr", "dist_to_support_pct",
]
