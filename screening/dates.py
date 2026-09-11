"""Shared date normalization for the screening engine.

Invezgo's endpoints are inconsistent about timezone info in date strings:
`chart_stock` returns ISO timestamps with a "Z" suffix (tz-aware, e.g.
"2024-09-08T17:00:00.000Z"), while `inventory_chart_stock`'s broker series
return bare "YYYY-MM-DD" (tz-naive). pandas treats a tz-aware and a
tz-naive timestamp for the same calendar day as NOT equal, so reindexing
one series against the other's DatetimeIndex silently drops every value to
the fill default instead of raising — a broker field would read as zero
every day rather than erroring. Every date index the engine builds must
go through this to stay comparable.
"""
from __future__ import annotations

import pandas as pd


def normalize_dates(series) -> pd.DatetimeIndex:
    """Parse a column of date strings/timestamps into tz-naive midnight
    timestamps, regardless of whether the source included a timezone."""
    return pd.to_datetime(series, utc=True).dt.tz_localize(None).dt.normalize()
