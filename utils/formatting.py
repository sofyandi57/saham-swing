from __future__ import annotations

import datetime as dt


def rupiah(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"Rp{v:,.0f}".replace(",", ".")


def compact_number(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000_000:
        return f"{sign}{v / 1_000_000_000_000:,.2f}T"
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:,.2f}B"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:,.2f}Jt"
    if v >= 1_000:
        return f"{sign}{v / 1_000:,.1f}Rb"
    return f"{sign}{v:,.0f}"


def pct(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{v:+.2f}%"


def last_trading_day(reference: dt.date | None = None) -> dt.date:
    """Best-effort last weekday on/before `reference` (does not account for IDX holidays)."""
    d = reference or dt.date.today()
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d -= dt.timedelta(days=1)
    return d


def days_ago(n: int, reference: dt.date | None = None) -> dt.date:
    d = reference or dt.date.today()
    return d - dt.timedelta(days=n)
