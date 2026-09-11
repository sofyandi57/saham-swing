"""Condition tree grammar + evaluator — skema-query-screening-engine.md §2-3.

A FieldContext wraps one ticker's already-computed data (technical columns,
broker series, candlestick patterns) and resolves `field_id` -> pd.Series on
demand. Referencing a field_id that isn't in the registry is a validation
error, per §1: "Field yang dipakai kondisi tapi tidak ada di registry harus
dianggap error validasi, bukan di-skip diam-diam."
"""
from __future__ import annotations

import operator as _op

import numpy as np
import pandas as pd

from screening.broker import BROKER_FIELDS
from screening.fundamentals import FUNDAMENTAL_FIELDS
from screening.technicals import TECHNICAL_FIELDS

CATEGORICAL_FIELDS = {"candlestick_pattern"}
SCALAR_FIELDS = {"history_days_available"}
SUPPORTED_FIELDS = (
    set(TECHNICAL_FIELDS) | set(BROKER_FIELDS) | set(FUNDAMENTAL_FIELDS) | CATEGORICAL_FIELDS | SCALAR_FIELDS
)

_OPS = {
    ">": _op.gt, ">=": _op.ge, "<": _op.lt, "<=": _op.le,
    "==": _op.eq, "!=": _op.ne,
}


class FieldError(ValueError):
    pass


class FieldContext:
    def __init__(
        self,
        technical_df: pd.DataFrame,
        broker_fields: dict,
        candlestick_patterns: set[str],
        fundamentals: dict | None = None,
    ):
        self.technical_df = technical_df
        self.broker_fields = broker_fields
        self.candlestick_patterns = candlestick_patterns
        self.fundamentals = fundamentals or {}
        self.history_days_available = len(technical_df)

    def get_series(self, field_id: str) -> pd.Series:
        if field_id in self.technical_df.columns:
            return self.technical_df[field_id]
        if field_id in self.broker_fields:
            series = self.broker_fields[field_id]
            if series.empty:
                return series
            return series.reindex(self.technical_df.index, fill_value=0.0)
        if field_id in FUNDAMENTAL_FIELDS:
            value = self.fundamentals.get(field_id)
            if value is None:
                return pd.Series(dtype=float)
            return pd.Series([value] * len(self.technical_df), index=self.technical_df.index)
        raise FieldError(
            f"Field '{field_id}' tidak ada di Field Registry "
            f"(screening/technicals.py, screening/broker.py, atau screening/fundamentals.py)."
        )


def _sign(x: float) -> str:
    if pd.isna(x):
        return "zero"
    if x > 0:
        return "positive"
    if x < 0:
        return "negative"
    return "zero"


def _streak(series: pd.Series, positive: bool) -> int:
    count = 0
    for v in series.iloc[::-1]:
        if pd.isna(v):
            break
        if (positive and v > 0) or (not positive and v < 0):
            count += 1
        else:
            break
    return count


def _slope(tail: pd.Series) -> str:
    vals = tail.dropna().values
    if len(vals) < 2:
        return "flat"
    x = np.arange(len(vals))
    m = np.polyfit(x, vals, 1)[0]
    if m > 0:
        return "up"
    if m < 0:
        return "down"
    return "flat"


def _sign_change(series: pd.Series, frm: str, to: str, window: int) -> bool:
    tail = series.tail(window)
    if tail.empty:
        return False
    current_sign = _sign(tail.iloc[-1])
    if current_sign != to:
        return False
    earlier = tail.iloc[:-1]
    return any(_sign(v) == frm for v in earlier)


def _compare(a, op: str, b) -> bool:
    if op == "between":
        lo, hi = b
        if a is None or pd.isna(a):
            return False
        return lo <= a <= hi
    if a is None or (isinstance(a, float) and pd.isna(a)):
        return False
    if b is None or (isinstance(b, float) and pd.isna(b)):
        return False
    return _OPS[op](a, b)


def evaluate_leaf(leaf: dict, ctx: FieldContext, trace: list | None = None) -> bool:
    field = leaf["field"]

    if field == "candlestick_pattern":
        matched = leaf.get("value") in ctx.candlestick_patterns
        result = matched if leaf["op"] == "==" else not matched
        if trace is not None:
            trace.append({"leaf": leaf, "result": result, "actual": sorted(ctx.candlestick_patterns)})
        return result

    if field == "history_days_available":
        result = _compare(ctx.history_days_available, leaf["op"], leaf.get("value"))
        if trace is not None:
            trace.append({"leaf": leaf, "result": result, "actual": ctx.history_days_available})
        return result

    series = ctx.get_series(field)
    if series.empty:
        if trace is not None:
            trace.append({"leaf": leaf, "result": False, "actual": None, "note": "data kosong"})
        return False

    agg = leaf.get("agg")
    window = leaf.get("window", 1)

    if agg is None:
        current = series.iloc[-1]
        if "value_field" in leaf:
            other_series = ctx.get_series(leaf["value_field"])
            other = other_series.iloc[-1] if not other_series.empty else np.nan
            result = _compare(current, leaf["op"], other)
            actual = f"{current} {leaf['op']} {other}"
        else:
            result = _compare(current, leaf["op"], leaf.get("value"))
            actual = current
        if trace is not None:
            trace.append({"leaf": leaf, "result": result, "actual": actual})
        return result

    tail = series.tail(window)

    if agg == "sign_change":
        result = _sign_change(series, leaf.get("from"), leaf.get("to"), window)
        if trace is not None:
            trace.append({"leaf": leaf, "result": result, "actual": list(tail.round(2))})
        return result

    if agg == "sum":
        agg_val = tail.sum()
    elif agg == "avg":
        agg_val = tail.mean()
    elif agg == "streak_positive":
        agg_val = _streak(series, positive=True)
    elif agg == "streak_negative":
        agg_val = _streak(series, positive=False)
    elif agg == "slope":
        slope_dir = _slope(tail)
        result = slope_dir == leaf.get("value")
        if trace is not None:
            trace.append({"leaf": leaf, "result": result, "actual": slope_dir})
        return result
    elif agg == "pct_change":
        if len(series) <= window or series.iloc[-1 - window] == 0 or pd.isna(series.iloc[-1 - window]):
            agg_val = np.nan
        else:
            agg_val = (series.iloc[-1] - series.iloc[-1 - window]) / abs(series.iloc[-1 - window])
    else:
        raise FieldError(f"Agregator '{agg}' tidak dikenal.")

    result = _compare(agg_val, leaf["op"], leaf.get("value"))
    if trace is not None:
        trace.append({"leaf": leaf, "result": result, "actual": agg_val})
    return result


def evaluate_node(node: dict, ctx: FieldContext, trace: list | None = None) -> bool:
    if "and" in node:
        return all(evaluate_node(n, ctx, trace) for n in node["and"])
    if "or" in node:
        return any(evaluate_node(n, ctx, trace) for n in node["or"])
    if "not" in node:
        return not evaluate_node(node["not"], ctx, trace)
    return evaluate_leaf(node, ctx, trace)


def collect_field_ids(node: dict, out: set[str] | None = None) -> set[str]:
    """Walk a condition tree (or a list of leaves like `confirmations`) and
    collect every field_id referenced, for the validation pass in engine.py."""
    if out is None:
        out = set()
    if node is None:
        return out
    if isinstance(node, list):
        for n in node:
            collect_field_ids(n, out)
        return out
    if "and" in node:
        collect_field_ids(node["and"], out)
    elif "or" in node:
        collect_field_ids(node["or"], out)
    elif "not" in node:
        collect_field_ids(node["not"], out)
    else:
        out.add(node["field"])
        if "value_field" in node:
            out.add(node["value_field"])
    return out
