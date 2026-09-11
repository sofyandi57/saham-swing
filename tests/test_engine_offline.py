"""Offline smoke test for the screening engine using synthetic OHLCV + broker
data (no network calls) — catches structural/runtime bugs before hitting the
real Invezgo API with a paid key."""
import numpy as np
import pandas as pd

from screening import broker as broker_mod
from screening import candlestick, engine, technicals
from screening.condition_tree import FieldContext, evaluate_node

np.random.seed(42)
n = 300
dates = pd.date_range("2024-01-01", periods=n, freq="B")
base = 1000 + np.cumsum(np.random.normal(0, 8, n))
base = np.maximum(base, 50)
close = base
open_ = close + np.random.normal(0, 3, n)
high = np.maximum(open_, close) + np.abs(np.random.normal(0, 4, n))
low = np.minimum(open_, close) - np.abs(np.random.normal(0, 4, n))
volume = np.abs(np.random.normal(5_000_000, 2_000_000, n))

df = pd.DataFrame({"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})
technical_df = technicals.enrich(df)
print("technical_df shape:", technical_df.shape)
print("NaN tail check (should be all filled by day 250):")
print(technical_df[technicals.TECHNICAL_FIELDS].iloc[-1].isna().sum(), "NaN out of", len(technicals.TECHNICAL_FIELDS))

brokers = ["AK", "YP", "PD", "CC", "KZ", "ZP", "DX", "XA"]
broker_rows = []
for b in brokers:
    bias = np.random.choice([-1, 1]) * np.random.uniform(0.3, 1.0)
    for d in dates[-60:]:
        val = np.random.normal(bias * 2_000_000_000, 3_000_000_000)
        broker_rows.append({"broker": b, "data": [{"date": d.strftime("%Y-%m-%d"), "value": val}]})

# merge into the shape build_broker_fields expects: {"broker":[{"broker":code,"data":[{date,value},...]}]}
merged = {}
for row in broker_rows:
    code = row["broker"]
    merged.setdefault(code, []).extend(row["data"])
raw_inventory = {"price": [], "broker": [{"broker": k, "data": v} for k, v in merged.items()]}

broker_fields = broker_mod.build_broker_fields(raw_inventory)
print("\nTop broker:", broker_fields["_top_broker"])
print("broker_net_value tail:\n", broker_fields["broker_net_value"].tail(3))

patterns = candlestick.detect_last_patterns(df.tail(5))
print("\nDetected candlestick patterns on last bar:", patterns)

ctx = FieldContext(technical_df, broker_fields, patterns)

print("\n=== Running all strategies against synthetic ticker ===")
strategies = engine.load_all_strategies()
print(f"Loaded {len(strategies)} strategies: {list(strategies.keys())}")

for sid, strat in strategies.items():
    try:
        engine.validate_strategy(strat)
    except Exception as e:
        print(f"[{sid}] VALIDATION ERROR: {e}")
        continue
    try:
        result = engine.evaluate_strategy_for_ticker(strat, ctx)
        print(f"[{sid}] OK -> lolos={result.get('lolos')} universe_ok={result.get('universe_ok')} confirmation_score={result.get('confirmation_score')}")
    except Exception as e:
        print(f"[{sid}] RUNTIME ERROR: {type(e).__name__}: {e}")

print("\n=== Composite ranking scoring function (single ticker, sanity) ===")
comp = strategies["composite_ranking"]
for c in comp["scoring"]["components"]:
    for f in c["fields"]:
        try:
            v = engine._scoring_field_value(f, ctx)
            print(f"  {f} -> {v}")
        except Exception as e:
            print(f"  {f} -> ERROR {e}")

print("\nAll checks completed without unhandled exceptions.")
