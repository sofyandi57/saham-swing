"""Screening engine — orchestrates fetch -> enrich -> evaluate for a strategy
across a universe of tickers. Implements the algorithm in
skema-query-screening-engine.md §5 (boolean strategies) and §6 (composite
ranking), on top of the Invezgo API client.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from invezgo import InvezgoAPIError
from screening import broker as broker_mod
from screening import candlestick
from screening import technicals
from screening.condition_tree import (
    FieldContext,
    FieldError,
    SUPPORTED_FIELDS,
    collect_field_ids,
    evaluate_leaf,
    evaluate_node,
    _streak,
)

STRATEGIES_DIR = Path(__file__).parent / "strategies"


def load_strategy(path: Path | str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_strategies() -> dict[str, dict]:
    out = {}
    for p in sorted(STRATEGIES_DIR.glob("*.json")):
        try:
            s = load_strategy(p)
            out[s["id"]] = s
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def validate_strategy(strategy: dict) -> set[str]:
    field_ids: set[str] = set()
    scoring_field_ids: set[str] = set()
    for key in ("universe_filter", "conditions", "exclude_if"):
        collect_field_ids(strategy.get(key), field_ids)
    collect_field_ids(strategy.get("confirmations"), field_ids)
    scoring = strategy.get("scoring")
    if scoring:
        for comp in scoring.get("components", []):
            scoring_field_ids |= set(comp.get("fields", []))

    unsupported = {f for f in field_ids if f not in SUPPORTED_FIELDS}
    unsupported |= {f for f in scoring_field_ids if f not in SUPPORTED_FIELDS and f not in SCORING_FIELD_ALIASES}
    field_ids |= scoring_field_ids
    if unsupported:
        raise FieldError(
            f"Strategi '{strategy.get('id')}' memakai field yang belum didukung engine: {sorted(unsupported)}"
        )
    return field_ids


def fetch_ticker_context(client, code: str, frm: str, to: str, broker_limit: int = 10) -> FieldContext | None:
    candles = client.chart_stock(code, frm, to)
    if not candles:
        return None
    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"])
    technical_df = technicals.enrich(df)

    try:
        raw_inventory = client.inventory_chart_stock(
            code, frm, to, scope="val", investor="all", market="ALL", limit=str(broker_limit)
        )
    except InvezgoAPIError:
        raw_inventory = {"price": [], "broker": []}
    broker_fields = broker_mod.build_broker_fields(raw_inventory or {"broker": []})

    patterns = candlestick.detect_last_patterns(df.tail(5))
    return FieldContext(technical_df, broker_fields, patterns)


def evaluate_strategy_for_ticker(strategy: dict, ctx: FieldContext) -> dict:
    universe_filter = strategy.get("universe_filter")
    if universe_filter and not evaluate_node(universe_filter, ctx):
        return {"universe_ok": False, "lolos": False}

    trace: list = []
    conditions = strategy.get("conditions")
    matched = evaluate_node(conditions, ctx, trace) if conditions else True

    exclude_trace: list = []
    excluded = False
    if strategy.get("exclude_if"):
        excluded = evaluate_node(strategy["exclude_if"], ctx, exclude_trace)

    confirm_trace: list = []
    confirmation_score = None
    if strategy.get("confirmations"):
        results = []
        for leaf in strategy["confirmations"]:
            try:
                results.append(evaluate_leaf(leaf, ctx, confirm_trace))
            except FieldError:
                results.append(False)
        confirmation_score = sum(results) / len(results) if results else None

    return {
        "universe_ok": True,
        "matched": matched,
        "excluded": excluded,
        "lolos": matched and not excluded,
        "confirmation_score": confirmation_score,
        "trace": trace,
        "exclude_trace": exclude_trace,
        "confirm_trace": confirm_trace,
    }


def run_screening(client, strategy: dict, codes: list[str], frm: str, to: str, progress_cb=None) -> list[dict]:
    validate_strategy(strategy)
    results = []
    for i, code in enumerate(codes):
        if progress_cb:
            progress_cb(i, len(codes), code)
        row = {"code": code}
        try:
            ctx = fetch_ticker_context(client, code, frm, to)
        except InvezgoAPIError as e:
            row["error"] = e.message
            results.append(row)
            continue
        if ctx is None or ctx.technical_df.empty:
            row["error"] = "Tidak ada data candlestick pada rentang ini."
            results.append(row)
            continue
        try:
            evaluation = evaluate_strategy_for_ticker(strategy, ctx)
        except FieldError as e:
            row["error"] = str(e)
            results.append(row)
            continue
        row.update(evaluation)
        row["last_close"] = float(ctx.technical_df["close"].iloc[-1])
        row["top_broker"] = ctx.broker_fields.get("_top_broker")
        results.append(row)
    return results


# -- composite ranking (skema-query-screening-engine.md §6) -------------------

def _scoring_field_value(field_name: str, ctx: FieldContext):
    if field_name in ("sma20", "sma50", "sma100", "sma200"):
        sma = ctx.get_series(field_name)
        close = ctx.get_series("close")
        if sma.empty or pd.isna(sma.iloc[-1]) or sma.iloc[-1] == 0:
            return None
        return (close.iloc[-1] - sma.iloc[-1]) / sma.iloc[-1] * 100
    if field_name == "broker_net_value_streak":
        series = ctx.get_series("broker_net_value")
        return float(_streak(series, positive=True)) if not series.empty else None
    series = ctx.get_series(field_name)
    if series.empty or pd.isna(series.iloc[-1]):
        return None
    return float(series.iloc[-1])


SCORING_FIELD_ALIASES = {"broker_net_value_streak"}


def run_ranking(client, strategy: dict, codes: list[str], frm: str, to: str, progress_cb=None) -> dict:
    scoring = strategy["scoring"]
    components = scoring["components"]
    validate_strategy(strategy)

    universe_filter = strategy.get("universe_filter")
    raw_values: dict[str, dict] = {}
    last_close: dict[str, float] = {}
    skipped: list[dict] = []

    for i, code in enumerate(codes):
        if progress_cb:
            progress_cb(i, len(codes), code)
        try:
            ctx = fetch_ticker_context(client, code, frm, to)
        except InvezgoAPIError as e:
            skipped.append({"code": code, "error": e.message})
            continue
        if ctx is None or ctx.technical_df.empty:
            skipped.append({"code": code, "error": "Tidak ada data candlestick."})
            continue
        if universe_filter and not evaluate_node(universe_filter, ctx):
            continue
        values = {}
        for comp in components:
            for field in comp["fields"]:
                values[field] = _scoring_field_value(field, ctx)
        raw_values[code] = values
        last_close[code] = float(ctx.technical_df["close"].iloc[-1])

    if not raw_values:
        return {"ranking": [], "skipped": skipped}

    value_df = pd.DataFrame(raw_values).T  # index=code, columns=field
    pct_df = value_df.rank(pct=True, na_option="keep") * 100
    pct_df = pct_df.fillna(50.0)

    sub_scores = pd.DataFrame(index=value_df.index)
    for comp in components:
        cols = [f for f in comp["fields"] if f in pct_df.columns]
        sub_scores[comp["name"]] = pct_df[cols].mean(axis=1) if cols else 50.0

    weights = {c["name"]: c["weight"] for c in components}
    score_total = sum(sub_scores[name] * w for name, w in weights.items())

    output_cfg = strategy.get("output", {})
    direction = output_cfg.get("direction", "desc")
    top_n = output_cfg.get("top_n", 20)

    ranking = []
    for code in value_df.index:
        ranking.append(
            {
                "code": code,
                "score_total": round(float(score_total[code]), 2),
                "sub_scores": {name: round(float(sub_scores.loc[code, name]), 1) for name in weights},
                "last_close": last_close.get(code),
            }
        )
    ranking.sort(key=lambda r: r["score_total"], reverse=(direction == "desc"))
    return {"ranking": ranking[:top_n], "skipped": skipped}
