import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from utils import auth
from utils.formatting import compact_number, last_trading_day, pct, rupiah
from utils.state import require_client

st.set_page_config(page_title="Screener - Swing Saham", page_icon="🔍", layout="wide")
auth.render_sidebar_widget()
st.title("🔍 Screener Saham")

client = require_client()

CATEGORY_OPTIONS = [
    "COMPOSITE", "SYARIAH", "IDXENERGY", "IDXBASIC", "IDXINDUST", "IDXNONCYC",
    "IDXCYCLIC", "IDXHEALTH", "IDXFINANCE", "IDXPROPERT", "IDXTECHNO", "IDXINFRA", "IDXTRANS",
]
FILTER_COLUMNS = [None, "change", "value", "volume", "ratio"]
FILTER_OPERATORS = [None, "<", ">", "=", ">=", "<=", "!="]


def render_pair_result(data: dict, top_key: str, bottom_key: str, top_label: str, bottom_label: str):
    col1, col2 = st.columns(2)
    for col, key, label in ((col1, top_key, top_label), (col2, bottom_key, bottom_label)):
        with col:
            st.markdown(f"**{label}**")
            items = (data or {}).get(key) or []
            if not items:
                st.caption("Tidak ada data untuk kriteria ini.")
                continue
            df = pd.DataFrame(items)
            cols = [c for c in ["code", "name", "price", "change", "value", "volume"] if c in df.columns]
            df = df[cols].copy()
            if "price" in df:
                df["price"] = df["price"].apply(rupiah)
            if "change" in df:
                df["change"] = df["change"].apply(pct)
            if "value" in df:
                df["value"] = df["value"].apply(compact_number)
            if "volume" in df:
                df["volume"] = df["volume"].apply(compact_number)
            rename = {
                "code": "Kode", "name": "Nama", "price": "Harga",
                "change": "Perubahan", "value": "Nilai", "volume": "Volume",
            }
            df = df.rename(columns=rename)
            st.dataframe(df, hide_index=True, use_container_width=True)


def filter_controls(key_prefix: str):
    c1, c2, c3 = st.columns(3)
    fcol = c1.selectbox("Filter kolom", FILTER_COLUMNS, key=f"{key_prefix}_col", format_func=lambda x: x or "(tanpa filter)")
    fop = c2.selectbox("Operator", FILTER_OPERATORS, key=f"{key_prefix}_op", format_func=lambda x: x or "-")
    fval = c3.text_input("Nilai", key=f"{key_prefix}_val", placeholder="mis. 5")
    return fcol, fop, (fval or None)


tab_change, tab_foreign, tab_accum, tab_ritel, tab_formula = st.tabs(
    ["📊 Top Gainers/Losers", "🌏 Foreign Flow", "🏦 Akumulasi/Distribusi", "🧑‍🤝‍🧑 Ritel", "🧮 Formula Custom"]
)

date_str = st.session_state.setdefault("screener_date", last_trading_day().isoformat())

with tab_change:
    date_val = st.date_input("Tanggal", value=last_trading_day(), key="date_change").isoformat()
    fcol, fop, fval = filter_controls("change")
    if st.button("Jalankan", key="run_change"):
        try:
            with st.spinner("Memuat..."):
                data = client.top_change(date_val, fcol, fop, fval)
            render_pair_result(data, "gain", "loss", "🚀 Top Gainers", "🔻 Top Losers")
        except InvezgoAPIError as e:
            st.error(e.message)

with tab_foreign:
    date_val = st.date_input("Tanggal", value=last_trading_day(), key="date_foreign").isoformat()
    fcol, fop, fval = filter_controls("foreign")
    if st.button("Jalankan", key="run_foreign"):
        try:
            with st.spinner("Memuat..."):
                data = client.top_foreign(date_val, fcol, fop, fval)
            render_pair_result(data, "accum", "dist", "🟢 Foreign Net Buy", "🔴 Foreign Net Sell")
        except InvezgoAPIError as e:
            st.error(e.message)

with tab_accum:
    date_val = st.date_input("Tanggal", value=last_trading_day(), key="date_accum").isoformat()
    fcol, fop, fval = filter_controls("accum")
    if st.button("Jalankan", key="run_accum"):
        try:
            with st.spinner("Memuat..."):
                data = client.top_accumulation(date_val, fcol, fop, fval)
            render_pair_result(data, "accum", "dist", "🟢 Akumulasi", "🔴 Distribusi")
        except InvezgoAPIError as e:
            st.error(e.message)

with tab_ritel:
    date_val = st.date_input("Tanggal", value=last_trading_day(), key="date_ritel").isoformat()
    fcol, fop, fval = filter_controls("ritel")
    if st.button("Jalankan", key="run_ritel"):
        try:
            with st.spinner("Memuat..."):
                data = client.top_ritel(date_val, fcol, fop, fval)
            render_pair_result(data, "accum", "dist", "🟢 Ritel Net Buy", "🔴 Ritel Net Sell")
        except InvezgoAPIError as e:
            st.error(e.message)

with tab_formula:
    st.caption(
        "Tulis formula screener Invezgo, contoh: `change > 3 and volume > 10000000` "
        "atau `prev < close`. Field mengikuti field yang didukung Invezgo screener."
    )
    formula = st.text_input("Formula", placeholder="change > 3 and volume > 10000000", key="formula_input")
    categories = st.multiselect("Kategori indeks (opsional)", CATEGORY_OPTIONS, key="formula_categories")
    if st.button("Jalankan Screener", key="run_formula"):
        if not formula.strip():
            st.warning("Isi formula terlebih dahulu.")
        else:
            try:
                with st.spinner("Menjalankan screener..."):
                    result = client.screener_run(formula.strip(), categories or None)
                if isinstance(result, list) and result:
                    st.success(f"Ditemukan {len(result)} saham.")
                    st.dataframe(pd.DataFrame(result), hide_index=True, use_container_width=True)
                elif isinstance(result, list):
                    st.info("Tidak ada saham yang cocok dengan formula ini.")
                else:
                    st.json(result)
            except InvezgoAPIError as e:
                st.error(e.message)
