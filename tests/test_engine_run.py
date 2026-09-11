"""Offline smoke test for engine.run_screening / engine.run_ranking using a
fake InvezgoClient (no network) across a small synthetic multi-ticker universe."""
import numpy as np
import pandas as pd

from screening import engine

np.random.seed(1)


def make_candles(n=300, drift=0.0, start_price=1000):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    close = start_price + np.cumsum(np.random.normal(drift, 8, n))
    close = np.maximum(close, 50)
    open_ = close + np.random.normal(0, 3, n)
    high = np.maximum(open_, close) + np.abs(np.random.normal(0, 4, n))
    low = np.minimum(open_, close) - np.abs(np.random.normal(0, 4, n))
    volume = np.abs(np.random.normal(8_000_000, 3_000_000, n))
    return [
        {"date": d.strftime("%Y-%m-%dT00:00:00.000Z"), "open": o, "high": h, "low": l, "close": c, "volume": v}
        for d, o, h, l, c, v in zip(dates, open_, high, low, close, volume)
    ]


def make_inventory(n_days=60, bias=0.5):
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    brokers = ["AK", "YP", "PD", "CC", "KZ"]
    out = []
    for b in brokers:
        b_bias = bias if b == "AK" else np.random.uniform(-0.5, 0.5)
        data = [
            {"date": d.strftime("%Y-%m-%d"), "value": float(np.random.normal(b_bias * 2_000_000_000, 2_500_000_000))}
            for d in dates
        ]
        out.append({"broker": b, "data": data})
    return {"price": [], "broker": out}


class FakeClient:
    def __init__(self):
        self.calls = 0

    def chart_stock(self, code, frm, to):
        self.calls += 1
        drift = {"BBCA": 3, "TLKM": -2, "GOTO": 0}.get(code, np.random.uniform(-2, 2))
        return make_candles(drift=drift)

    def inventory_chart_stock(self, code, frm, to, scope="val", investor="all", market="ALL", limit=None):
        self.calls += 1
        bias = {"BBCA": 0.8, "TLKM": -0.3, "GOTO": 0.1}.get(code, 0.2)
        return make_inventory(bias=bias)


client = FakeClient()
strategies = engine.load_all_strategies()
codes = ["BBCA", "TLKM", "GOTO", "ANTM", "MDKA"]

print("=== run_screening (breakout_broker_confirm) ===")
progress_log = []
results = engine.run_screening(
    client, strategies["breakout_broker_confirm"], codes, "2024-01-01", "2025-02-21",
    progress_cb=lambda i, total, code: progress_log.append((i, total, code)),
)
print("progress calls:", len(progress_log), "expected:", len(codes))
for r in results:
    print(" ", r["code"], "lolos=", r.get("lolos"), "error=", r.get("error"))

print("\n=== run_ranking (composite_ranking) ===")
rank_result = engine.run_ranking(client, strategies["composite_ranking"], codes, "2024-01-01", "2025-02-21")
for row in rank_result["ranking"]:
    print(" ", row["code"], "score_total=", row["score_total"], "sub_scores=", row["sub_scores"])
print("skipped:", rank_result["skipped"])

print(f"\nTotal fake API calls made: {client.calls} (expect {len(codes) * 2 * 2} across both runs)")
print("\nAll checks completed without unhandled exceptions.")
