import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from invezgo import InvezgoAPIError
from utils.formatting import compact_number, days_ago, last_trading_day, rupiah
from utils.state import require_client

st.set_page_config(page_title="Bandarmologi - Swing Saham", page_icon="🕵️", layout="wide")
st.title("🕵️ Bandarmologi & Broker Flow")
st.caption("Data broker summary, akumulasi, dan aliran dana dari Invezgo. Reader/edukasi — bukan ajakan transaksi.")

client = require_client()


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list(_client):
    return _client.list_stock()


try:
    stocks = load_stock_list(client)
except InvezgoAPIError as e:
    st.error(f"Gagal memuat daftar saham: {e.message}")
    st.stop()

code_to_name = {s["code"]: s["name"] for s in stocks}
options = sorted(code_to_name.keys())
default_idx = options.index("BBCA") if "BBCA" in options else 0

code = st.selectbox("Kode Saham", options, index=default_idx, format_func=lambda c: f"{c} — {code_to_name.get(c, '')}")

tab_summary, tab_inventory, tab_sankey, tab_stalker = st.tabs(
    ["📋 Broker Summary", "📈 Inventory (Akumulasi)", "🌊 Sankey Flow", "🎯 Broker Stalker"]
)

with tab_summary:
    c1, c2, c3, c4 = st.columns(4)
    frm = c1.date_input("Dari", value=days_ago(30), key="sum_from")
    to = c2.date_input("Sampai", value=last_trading_day(), key="sum_to")
    investor = c3.selectbox("Investor", ["all", "f", "d"], key="sum_investor",
                             format_func=lambda x: {"all": "Semua", "f": "Asing", "d": "Domestik"}[x])
    market = c4.selectbox("Market", ["RG", "NG", "TN"], key="sum_market")

    if st.button("Muat Broker Summary", key="run_summary"):
        try:
            with st.spinner("Memuat..."):
                data = client.summary_stock(code, frm.isoformat(), to.isoformat(), investor, market)
        except InvezgoAPIError as e:
            st.error(e.message)
            data = None
        if data:
            df = pd.DataFrame(data)
            df = df.sort_values("net_value", ascending=False, key=lambda s: s.astype(float))
            show = df[["code", "name", "buy_value", "sell_value", "net_value", "buy_volume", "sell_volume", "net_volume"]].copy()
            for c in ["buy_value", "sell_value", "net_value", "buy_volume", "sell_volume", "net_volume"]:
                show[c] = show[c].astype(float).apply(compact_number)
            show.columns = ["Broker", "Nama", "Buy Value", "Sell Value", "Net Value", "Buy Vol", "Sell Vol", "Net Vol"]
            st.dataframe(show, hide_index=True, use_container_width=True, height=500)
        elif data is not None:
            st.info("Tidak ada data broker pada rentang ini.")

with tab_inventory:
    c1, c2, c3, c4 = st.columns(4)
    frm_i = c1.date_input("Dari", value=days_ago(90), key="inv_from")
    to_i = c2.date_input("Sampai", value=last_trading_day(), key="inv_to")
    scope = c3.selectbox("Skala", ["val", "vol", "freq"], key="inv_scope",
                          format_func=lambda x: {"val": "Nilai", "vol": "Volume", "freq": "Frekuensi"}[x])
    investor_i = c4.selectbox("Investor", ["all", "f", "d"], key="inv_investor",
                               format_func=lambda x: {"all": "Semua", "f": "Asing", "d": "Domestik"}[x])
    limit = st.slider("Jumlah broker ditampilkan (top by |net|)", 3, 15, 8, key="inv_limit")

    if st.button("Muat Inventory Chart", key="run_inventory"):
        try:
            with st.spinner("Memuat..."):
                data = client.inventory_chart_stock(
                    code, frm_i.isoformat(), to_i.isoformat(), scope=scope, investor=investor_i,
                    market="ALL", limit=str(limit),
                )
        except InvezgoAPIError as e:
            st.error(e.message)
            data = None

        if data:
            price_df = pd.DataFrame(data.get("price", []))
            broker_data = data.get("broker", [])

            if not price_df.empty:
                price_df["date"] = pd.to_datetime(price_df["date"])
                price_fig = go.Figure(
                    go.Candlestick(
                        x=price_df["date"], open=price_df["open"], high=price_df["high"],
                        low=price_df["low"], close=price_df["close"], name=code,
                    )
                )
                price_fig.update_layout(height=350, xaxis_rangeslider_visible=False, margin=dict(t=20, b=10))
                st.plotly_chart(price_fig, use_container_width=True)

            if broker_data:
                inv_fig = go.Figure()
                for b in broker_data:
                    bdf = pd.DataFrame(b.get("data", []))
                    if bdf.empty:
                        continue
                    bdf["date"] = pd.to_datetime(bdf["date"])
                    inv_fig.add_trace(go.Scatter(x=bdf["date"], y=bdf["value"], mode="lines", name=b.get("broker", "?")))
                inv_fig.update_layout(height=400, margin=dict(t=20, b=10), yaxis_title=f"Kumulatif ({scope})")
                st.plotly_chart(inv_fig, use_container_width=True)
            else:
                st.info("Tidak ada data broker pada rentang ini.")

with tab_sankey:
    c1, c2, c3, c4, c5 = st.columns(5)
    date_s = c1.date_input("Tanggal", value=last_trading_day(), key="sankey_date")
    type_s = c2.selectbox("Tipe", ["value", "volume"], key="sankey_type")
    buyer = c3.selectbox("Buyer", ["ALL", "F", "D"], key="sankey_buyer")
    seller = c4.selectbox("Seller", ["ALL", "F", "D"], key="sankey_seller")
    market_s = c5.selectbox("Market", ["RG", "NG", "TN"], key="sankey_market")

    if st.button("Muat Sankey", key="run_sankey"):
        try:
            with st.spinner("Memuat..."):
                data = client.sankey_chart(code, date_s.isoformat(), type_s, buyer, seller, market_s)
        except InvezgoAPIError as e:
            st.error(e.message)
            data = None

        if data and data.get("links"):
            nodes = [n["name"] for n in data.get("nodes", [])]
            node_idx = {name: i for i, name in enumerate(nodes)}
            links = data.get("links", [])
            fig = go.Figure(
                go.Sankey(
                    node=dict(label=nodes, pad=15, thickness=15),
                    link=dict(
                        source=[node_idx[l["source"]] for l in links],
                        target=[node_idx[l["target"]] for l in links],
                        value=[l["value"] for l in links],
                    ),
                )
            )
            fig.update_layout(height=500, margin=dict(t=20, b=10))
            st.plotly_chart(fig, use_container_width=True)
        elif data is not None:
            st.info("Tidak ada aliran transaksi crossing pada tanggal ini.")

with tab_stalker:
    c1, c2, c3, c4 = st.columns(4)
    frm_st = c1.date_input("Dari", value=days_ago(30), key="stalk_from")
    to_st = c2.date_input("Sampai", value=last_trading_day(), key="stalk_to")
    investor_st = c3.selectbox("Investor", ["all", "f", "d"], key="stalk_investor",
                                format_func=lambda x: {"all": "Semua", "f": "Asing", "d": "Domestik"}[x])
    market_st = c4.selectbox("Market", ["RG", "NG", "TN"], key="stalk_market")

    if st.button("Muat Stalker", key="run_stalker"):
        try:
            with st.spinner("Memuat..."):
                data = client.stalker_list(code, frm_st.isoformat(), to_st.isoformat(), investor_st, market_st)
        except InvezgoAPIError as e:
            st.error(e.message)
            data = None

        if data:
            summary = data.get("summary", {})
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Net", compact_number(summary.get("total_net")))
            m2.metric("Total Volume", compact_number(summary.get("total_volume")))
            m3.metric("Konsentrasi", f"{summary.get('concentration', '-')}%")
            m4.metric("Buy Dominance", f"{summary.get('buy_dom', '-')}%")

            listing = data.get("list", [])
            if listing:
                df = pd.DataFrame(listing)
                if "value" in df:
                    df["value"] = df["value"].apply(compact_number)
                if "volume" in df:
                    df["volume"] = df["volume"].apply(compact_number)
                st.dataframe(df, hide_index=True, use_container_width=True)
