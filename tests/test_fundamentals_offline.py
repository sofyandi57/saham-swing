"""Offline smoke test for screening/fundamentals.py and the two new
strategies (bpjs_intraday, under_value) that depend on it — synthetic data,
no network calls."""
import numpy as np
import pandas as pd

from screening import engine, fundamentals

np.random.seed(7)


def make_candles(n=90, drift=0.0, start_price=1000, big_up_last_day=False):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    # Daily noise ~2.5% of price so ATR% comes out realistically volatile
    # (needed for HOT1 to clear bpjs_intraday's atr_pct > 2 threshold).
    close = start_price + np.cumsum(np.random.normal(drift, start_price * 0.025, n))
    close = np.maximum(close, 50)
    if big_up_last_day:
        close[-1] = close[-2] * 1.05  # +5% today, clean signal for BPJS test
    open_ = close + np.random.normal(0, start_price * 0.01, n)
    high = np.maximum(open_, close) + np.abs(np.random.normal(0, start_price * 0.015, n))
    low = np.minimum(open_, close) - np.abs(np.random.normal(0, start_price * 0.015, n))
    volume = np.abs(np.random.normal(8_000_000, 1_000_000, n))
    if big_up_last_day:
        volume[-1] = volume[:-1].mean() * 3  # volume spike today
    return [
        {"date": d.strftime("%Y-%m-%dT00:00:00.000Z"), "open": o, "high": h, "low": l, "close": c, "volume": v}
        for d, o, h, l, c, v in zip(dates, open_, high, low, close, volume)
    ]


def make_inventory(n_days=30, bias=0.5):
    # Must end on the same "today" as make_candles's 90-bday range starting
    # 2024-01-01, or the broker series won't cover the most recent candle
    # and reindexing fills it with 0 — silently breaking window=1 checks.
    all_dates = pd.date_range("2024-01-01", periods=90, freq="B")
    dates = all_dates[-n_days:]
    brokers = ["AK", "YP", "PD"]
    out = []
    for b in brokers:
        # All brokers share the bias (broad-based buying/selling), with a
        # low std relative to the mean so the top-5 SUM is reliably signed
        # the same way as `bias` — a lone optimistic broker isn't enough to
        # flip a mixed book positive, which is the realistic behavior we
        # want bpjs_intraday's window=1 sum check to key off.
        data = [
            {"date": d.strftime("%Y-%m-%d"), "value": float(np.random.normal(bias * 1_000_000_000, 100_000_000))}
            for d in dates
        ]
        out.append({"broker": b, "data": data})
    return {"price": [], "broker": out}


class FakeClient:
    def __init__(self, keystat_data=None):
        self.calls = 0
        self.keystat_calls = []
        self.keystat_data = keystat_data or {}

    def chart_stock(self, code, frm, to):
        self.calls += 1
        return make_candles(big_up_last_day=(code == "HOT1"))

    def inventory_chart_stock(self, code, frm, to, scope="val", investor="all", market="ALL", limit=None):
        self.calls += 1
        bias = 0.9 if code == "HOT1" else 0.1
        return make_inventory(bias=bias)

    def keystat_chart(self, code, type_, name, limit="1"):
        self.calls += 1
        self.keystat_calls.append((code, name))
        value = self.keystat_data.get(code, {}).get(name)
        if value is None:
            return []
        return [{"date": "Q2 2025", "year": 2025, "amount": value, "period": "Q2"}]


strategies = engine.load_all_strategies()

print("=== fundamentals.fetch_fundamentals: only PER resolves ===")
client = FakeClient(keystat_data={"CHEAP1": {"PER": 8.5}})
result = fundamentals.fetch_fundamentals(client, "CHEAP1")
print("result:", result)
assert result == {"per": 8.5}, result
print("PBV/ROE absent (not guessed) when unresolved: OK")

print("\n=== fundamentals.fetch_fundamentals: all three + per_pbv derived ===")
client2 = FakeClient(keystat_data={"CHEAP2": {"PER": 8.0, "PBV": 1.0, "ROE": 12.5}})
result2 = fundamentals.fetch_fundamentals(client2, "CHEAP2")
print("result:", result2)
assert result2["per"] == 8.0 and result2["pbv"] == 1.0 and result2["roe"] == 12.5
assert result2["per_pbv"] == 8.0, result2
print("per_pbv correctly derived: OK")

print("\n=== fundamentals fallback candidate name (PE instead of PER) ===")
client3 = FakeClient(keystat_data={"CHEAP3": {"PE": 7.0, "PB": 0.8, "ROE": 15.0}})
result3 = fundamentals.fetch_fundamentals(client3, "CHEAP3")
print("result:", result3)
assert result3["per"] == 7.0 and result3["pbv"] == 0.8
print("fallback candidate name resolved: OK")

print("\n=== under_value strategy end-to-end: cheap stock passes, expensive one doesn't ===")
uv = strategies["under_value"]
client4 = FakeClient(keystat_data={
    "CHEAP4": {"PER": 8.0, "PBV": 1.0, "ROE": 10.0},   # per_pbv=8 < 9 -> should pass
    "EXPENSIVE4": {"PER": 25.0, "PBV": 4.0, "ROE": 10.0},  # way over thresholds -> should fail
    "NODATA4": {},  # nothing resolves -> should fail gracefully, not crash
})
results = engine.run_screening(client4, uv, ["CHEAP4", "EXPENSIVE4", "NODATA4"], "2024-01-01", "2024-05-01")
by_code = {r["code"]: r for r in results}
print("CHEAP4:", by_code["CHEAP4"].get("lolos"), by_code["CHEAP4"].get("error"))
print("EXPENSIVE4:", by_code["EXPENSIVE4"].get("lolos"), by_code["EXPENSIVE4"].get("error"))
print("NODATA4:", by_code["NODATA4"].get("lolos"), by_code["NODATA4"].get("error"))
assert by_code["CHEAP4"]["lolos"] is True, by_code["CHEAP4"]
assert by_code["EXPENSIVE4"]["lolos"] is False
assert by_code["NODATA4"]["lolos"] is False and by_code["NODATA4"].get("error") is None
print("under_value correctly discriminates cheap vs expensive vs no-data: OK")

print("\n=== bpjs_intraday strategy end-to-end: today's big-gap-up stock should surface ===")
np.random.seed(7)  # isolate from random-stream drift consumed by earlier sections
bpjs = strategies["bpjs_intraday"]
client5 = FakeClient()
results5 = engine.run_screening(client5, bpjs, ["HOT1", "COLD1"], "2024-01-01", "2024-05-01")
by_code5 = {r["code"]: r for r in results5}
print("HOT1:", by_code5["HOT1"].get("lolos"))
print("COLD1:", by_code5["COLD1"].get("lolos"))
assert by_code5["HOT1"]["lolos"] is True, by_code5["HOT1"]
assert by_code5["COLD1"]["lolos"] is False
print("bpjs_intraday correctly flags the gap-up/volume-spike stock: OK")

print("\n=== need_fundamentals gating: composite_ranking (no fundamental fields) never calls keystat_chart ===")
client6 = FakeClient()
engine.run_screening(client6, strategies["breakout_broker_confirm"], ["ANY1"], "2024-01-01", "2024-05-01")
assert client6.keystat_calls == [], client6.keystat_calls
print("OK: strategies that don't reference per/pbv/roe skip keystat calls entirely (no wasted API usage).")

print("\nAll fundamentals/BPJS/under_value checks passed.")
