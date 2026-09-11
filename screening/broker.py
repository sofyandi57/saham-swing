"""Broker/bandarmologi part of the Field Registry, built from a single
`inventory_chart_stock` call per ticker (one API call covers the whole
window instead of one call per day).

Definitions follow skema-query-screening-engine.md §1, with the pragmatic
adaptations noted inline where Invezgo's response shape forces an
approximation (documented so results aren't mistaken for exact figures).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _broker_daily_frame(raw: dict) -> pd.DataFrame:
    """Pivot inventory-chart raw JSON into a date x broker matrix of daily net values."""
    brokers = raw.get("broker", []) or []
    frames = []
    for b in brokers:
        code = b.get("broker", "?")
        data = b.get("data", []) or []
        if not data:
            continue
        s = pd.DataFrame(data)
        s["date"] = pd.to_datetime(s["date"]).dt.normalize()
        s = s.groupby("date")["value"].sum()
        s.name = code
        frames.append(s)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, axis=1).sort_index().fillna(0.0)
    return df


def build_broker_fields(raw: dict, top_n: int = 5) -> dict[str, pd.Series]:
    """Return the broker time-series fields keyed by field_id, indexed by date.

    - broker_net_value: daily series of the single largest net accumulator
      broker over the fetched window (the broker whose fetched-window total
      net value is highest) — used for streak/sign_change checks.
    - broker_net_value_top5: per day, sum of that day's top-`top_n` broker
      values (re-ranked every day, matching "top-5 hari itu").
    - broker_inventory: running cumulative sum of broker_net_value since the
      start of the fetched window (the anchor).
    - broker_concentration_top5: per day, |top-N sum| / |sum of all fetched
      brokers| — approximation, since total market volume isn't available
      from this endpoint (only the `limit` most significant brokers are
      returned by Invezgo, not the whole market).
    """
    df = _broker_daily_frame(raw)
    if df.empty:
        empty = pd.Series(dtype=float)
        return {
            "broker_net_value": empty,
            "broker_net_value_top5": empty,
            "broker_inventory": empty,
            "broker_concentration_top5": empty,
            "_top_broker": None,
            "_broker_daily": df,
        }

    totals = df.sum(axis=0).sort_values(ascending=False)
    top_broker = totals.index[0]
    broker_net_value = df[top_broker]

    def top5_sum(row: pd.Series) -> float:
        return row.sort_values(ascending=False).head(top_n).sum()

    broker_net_value_top5 = df.apply(top5_sum, axis=1)

    def concentration(row: pd.Series) -> float:
        total_abs = row.abs().sum()
        if total_abs == 0:
            return np.nan
        top_abs = row.abs().sort_values(ascending=False).head(top_n).sum()
        return top_abs / total_abs

    broker_concentration_top5 = df.apply(concentration, axis=1)
    broker_inventory = broker_net_value.cumsum()

    return {
        "broker_net_value": broker_net_value,
        "broker_net_value_top5": broker_net_value_top5,
        "broker_inventory": broker_inventory,
        "broker_concentration_top5": broker_concentration_top5,
        "_top_broker": top_broker,
        "_broker_daily": df,
    }


BROKER_FIELDS = [
    "broker_net_value",
    "broker_net_value_top5",
    "broker_inventory",
    "broker_concentration_top5",
]
