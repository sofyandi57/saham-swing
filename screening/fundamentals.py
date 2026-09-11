"""Fundamental scalar fields (PER/PBV/ROE) via Invezgo's keystat-chart
endpoint — best-effort, by design.

Invezgo's key-statistics endpoints aren't fully documented: the OpenAPI
spec doesn't enumerate valid `name` values for `/analysis/keystat-chart`
(only "ROE" appears, as a parameter example) and `/analysis/keystat`'s own
description admits the underlying figures are "sedang proses aktualisasi"
(being recalculated, may be inaccurate). We try a short list of plausible
identifiers per ratio and take whichever resolves first; anything that
doesn't resolve is simply absent rather than guessed, and the condition
tree treats a missing fundamental like a missing technical field (no
match, not a crash — see condition_tree.FieldContext.get_series).

Once used against a real API key, check which candidate actually hit
(fetch_fundamentals returns only the fields that resolved) and tighten
_STAT_CANDIDATES to the confirmed name so we stop paying for the misses.
"""
from __future__ import annotations

from invezgo import InvezgoAPIError

_STAT_CANDIDATES: dict[str, list[str]] = {
    "per": ["PER", "PE"],
    "pbv": ["PBV", "PB"],
    "roe": ["ROE"],
}


def _latest_stat_value(client, code: str, stat_name: str) -> float | None:
    try:
        data = client.keystat_chart(code, type_="Q", name=stat_name, limit="1")
    except InvezgoAPIError:
        return None
    if not data:
        return None
    row = data[0] if isinstance(data, list) else None
    if not isinstance(row, dict):
        return None
    value = row.get("amount")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_fundamentals(client, code: str) -> dict[str, float]:
    """Best-effort PER/PBV/ROE (+ derived per_pbv) for one ticker. Missing
    keys mean every candidate name failed for that ratio — not an error."""
    result: dict[str, float] = {}
    for field, candidates in _STAT_CANDIDATES.items():
        for name in candidates:
            value = _latest_stat_value(client, code, name)
            if value is not None:
                result[field] = value
                break

    if "per" in result and "pbv" in result:
        result["per_pbv"] = result["per"] * result["pbv"]

    return result


FUNDAMENTAL_FIELDS = ["per", "pbv", "roe", "per_pbv"]
