import datetime as dt

import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from screening import engine
from screening.condition_tree import FieldError
from utils import auth
from utils.formatting import compact_number, days_ago, last_trading_day, pct, rupiah
from utils.state import require_client

st.set_page_config(page_title="Strategy Screener - Swing Saham", page_icon="🧠", layout="wide")
auth.require_login()
st.title("🧠 Strategy Screener")
st.caption(
    "Engine screening berbasis condition-tree (spesifikasi internal) di atas data Invezgo — "
    "field teknikal (SMA/EMA/RSI/ADX/Donchian/OBV, dll) + field bandarmologi (broker net value, "
    "inventory, konsentrasi top-5). Alat bantu penyaringan awal, bukan sinyal eksekusi otomatis."
)

client = require_client()

LIQUID_DEFAULT = [
    "BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNVR", "ICBP", "INDF", "KLBF",
    "ANTM", "MDKA", "PGAS", "PTBA", "ADRO", "ITMG", "INCO", "TINS", "SMGR", "INTP",
    "CPIN", "JPFA", "AALI", "EXCL", "ISAT", "TOWR", "MNCN", "SCMA", "GOTO", "ARTO",
    "BRIS", "BBTN", "AKRA", "UNTR", "HRUM", "HMSP", "GGRM", "PWON", "CTRA", "BSDE",
]

MAX_UNIVERSE = 60


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list(_client):
    return _client.list_stock()


@st.cache_resource(show_spinner=False)
def load_strategies():
    return engine.load_all_strategies()


strategies = load_strategies()
if not strategies:
    st.error("Tidak ada file strategi ditemukan di `screening/strategies/`.")
    st.stop()

try:
    stocks = load_stock_list(client)
except InvezgoAPIError as e:
    st.error(f"Gagal memuat daftar saham: {e.message}")
    st.stop()

all_codes = sorted(s["code"] for s in stocks)
code_to_name = {s["code"]: s["name"] for s in stocks}

strategy_ids = list(strategies.keys())
strategy_id = st.selectbox(
    "Pilih Strategi", strategy_ids,
    format_func=lambda sid: strategies[sid].get("name", sid),
)
strategy = strategies[strategy_id]

is_warning = strategy.get("output_type") == "warning"
is_ranking = strategy.get("scoring") is not None

badge = "⚠️ Sinyal Waspada (bukan entry baru)" if is_warning else ("📊 Ranking Komposit" if is_ranking else "✅ Boolean Screening")
st.info(f"**{badge}**\n\n{strategy.get('thesis', '')}")

with st.expander("Lihat definisi JSON strategi ini"):
    st.json(strategy)

st.subheader("Universe Saham")
default_universe = [c for c in LIQUID_DEFAULT if c in code_to_name] or all_codes[:30]
universe = st.multiselect(
    f"Pilih saham yang mau discreening (maks {MAX_UNIVERSE} — tiap saham butuh 2 API call)",
    all_codes, default=default_universe,
    format_func=lambda c: f"{c} — {code_to_name.get(c, '')}",
)
if len(universe) > MAX_UNIVERSE:
    st.warning(f"Terlalu banyak ({len(universe)}). Hanya {MAX_UNIVERSE} saham pertama yang akan diproses.")
    universe = universe[:MAX_UNIVERSE]

c1, c2 = st.columns(2)
frm = c1.date_input("Data historis dari", value=days_ago(400), max_value=dt.date.today())
to = c2.date_input("Sampai", value=last_trading_day(), max_value=dt.date.today())

run = st.button("🚀 Jalankan Screening", type="primary", disabled=not universe)

if run:
    try:
        engine.validate_strategy(strategy)
    except FieldError as e:
        st.error(str(e))
        st.stop()

    progress = st.progress(0.0, text="Memulai...")

    def on_progress(i, total, code):
        progress.progress((i + 1) / total, text=f"Memproses {code} ({i + 1}/{total})...")

    if is_ranking:
        result = engine.run_ranking(client, strategy, universe, frm.isoformat(), to.isoformat(), progress_cb=on_progress)
        progress.empty()
        ranking = result["ranking"]
        skipped = result["skipped"]

        if not ranking:
            st.warning("Tidak ada saham yang lolos universe_filter.")
        else:
            st.success(f"Top {len(ranking)} saham berdasarkan skor komposit.")
            rows = []
            for r in ranking:
                row = {"Kode": r["code"], "Nama": code_to_name.get(r["code"], ""), "Harga": rupiah(r["last_close"]), "Skor Total": r["score_total"]}
                row.update({k.replace("_", " ").title(): v for k, v in r["sub_scores"].items()})
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        if skipped:
            with st.expander(f"{len(skipped)} saham dilewati (error/data kosong)"):
                st.dataframe(pd.DataFrame(skipped), hide_index=True, use_container_width=True)

    else:
        results = engine.run_screening(client, strategy, universe, frm.isoformat(), to.isoformat(), progress_cb=on_progress)
        progress.empty()

        errors = [r for r in results if r.get("error")]
        no_universe = [r for r in results if not r.get("error") and not r.get("universe_ok")]
        passed = [r for r in results if r.get("lolos")]
        failed_conditions = [r for r in results if not r.get("error") and r.get("universe_ok") and not r.get("lolos")]

        st.success(f"{len(passed)} dari {len(universe)} saham lolos kondisi strategi.")

        if passed:
            rows = []
            for r in passed:
                rows.append({
                    "Kode": r["code"],
                    "Nama": code_to_name.get(r["code"], ""),
                    "Harga": rupiah(r["last_close"]),
                    "Broker Akumulator Utama": r.get("top_broker") or "-",
                    "Skor Konfirmasi": f"{r['confirmation_score']*100:.0f}%" if r.get("confirmation_score") is not None else "-",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

            for r in passed:
                with st.expander(f"Detail {r['code']}"):
                    for t in r.get("trace", []):
                        leaf = t["leaf"]
                        icon = "✅" if t["result"] else "❌"
                        st.markdown(f"{icon} `{leaf.get('field')}` {leaf.get('agg', '')} {leaf.get('op')} {leaf.get('value', leaf.get('value_field', ''))} — actual: `{t.get('actual')}`")
        else:
            st.caption("Tidak ada saham yang lolos kondisi utama pada universe ini.")

        with st.expander(f"{len(failed_conditions)} saham tidak lolos kondisi (dalam universe)"):
            if failed_conditions:
                st.dataframe(
                    pd.DataFrame([{"Kode": r["code"], "Excluded (red flag)": r.get("excluded", False)} for r in failed_conditions]),
                    hide_index=True, use_container_width=True,
                )

        if no_universe:
            with st.expander(f"{len(no_universe)} saham gagal universe_filter (likuiditas/histori kurang)"):
                st.dataframe(pd.DataFrame([{"Kode": r["code"]} for r in no_universe]), hide_index=True, use_container_width=True)

        if errors:
            with st.expander(f"{len(errors)} saham error/data kosong"):
                st.dataframe(pd.DataFrame(errors)[["code", "error"]], hide_index=True, use_container_width=True)
