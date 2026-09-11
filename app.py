import datetime as dt

import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from utils.formatting import last_trading_day, pct, rupiah
from utils.state import get_client, get_api_key

st.set_page_config(page_title="Swing Saham - Invezgo", page_icon="📈", layout="wide")

with st.sidebar:
    st.header("🔑 Invezgo API Key")
    st.caption(
        "Key hanya disimpan di sesi browser Anda saat ini (tidak ditulis ke kode/repo). "
        "Dapatkan key di [invezgo.com/id/setting/api](https://invezgo.com/id/setting/api)."
    )
    existing = st.session_state.get("invezgo_api_key", "")
    api_key_input = st.text_input("API Key", value=existing, type="password", placeholder="ivz_xxx...")
    col_a, col_b = st.columns(2)
    if col_a.button("Simpan", use_container_width=True):
        st.session_state["invezgo_api_key"] = api_key_input.strip()
        st.rerun()
    if col_b.button("Hapus", use_container_width=True):
        st.session_state.pop("invezgo_api_key", None)
        st.session_state.pop("_client", None)
        st.session_state.pop("_client_key", None)
        st.rerun()

    if get_api_key():
        st.success("API Key aktif untuk sesi ini.")
    else:
        st.info("Belum ada API Key. Fitur data akan terkunci sampai key diisi.")

st.title("📈 Swing Saham — powered by Invezgo API")
st.caption(
    "Aplikasi bantu riset swing trading saham IDX: screener, chart + support/resistance, "
    "bandarmologi (broker flow), watchlist & alert. **Bukan rekomendasi/ajakan jual-beli — "
    "murni alat bantu riset & edukasi.**"
)

st.divider()

st.subheader("Navigasi")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.page_link("pages/1_Screener.py", label="🔍 Screener", icon="🔍")
    st.caption("Top gainers/losers, akumulasi asing/ritel, & custom formula screener.")
with c2:
    st.page_link("pages/2_Analisa_Saham.py", label="📊 Analisa Saham", icon="📊")
    st.caption("Candlestick, support/resistance otomatis, dan trading plan swing.")
with c3:
    st.page_link("pages/3_Bandarmologi.py", label="🕵️ Bandarmologi", icon="🕵️")
    st.caption("Broker summary, inventory (akumulasi), dan sankey aliran dana.")
with c4:
    st.page_link("pages/4_Watchlist_Alert.py", label="⭐ Watchlist & Alert", icon="⭐")
    st.caption("Kelola watchlist pribadi dan alert formula real-time.")

st.divider()

client = get_client()
if client is None:
    st.info("👈 Masukkan API Key di sidebar untuk melihat ringkasan pasar hari ini.")
else:
    st.subheader("Ringkasan Pasar")
    default_date = last_trading_day()
    date_str = st.date_input("Tanggal data", value=default_date, max_value=dt.date.today()).isoformat()

    try:
        with st.spinner("Mengambil data top movers..."):
            top_change = client.top_change(date=date_str)
    except InvezgoAPIError as e:
        st.error(f"Gagal ambil data: {e.message}")
        top_change = None

    if top_change:
        col_gain, col_loss = st.columns(2)

        def render_top(container, items, title, positive: bool):
            with container:
                st.markdown(f"**{title}**")
                if not items:
                    st.caption("Tidak ada data.")
                    return
                df = pd.DataFrame(items)[["code", "name", "price", "change", "value"]]
                df["price"] = df["price"].apply(rupiah)
                df["change"] = df["change"].apply(pct)
                df["value"] = df["value"].apply(lambda v: rupiah(v))
                df.columns = ["Kode", "Nama", "Harga", "Perubahan", "Nilai Transaksi"]
                st.dataframe(df, hide_index=True, use_container_width=True)

        render_top(col_gain, top_change.get("gain", [])[:10], "🚀 Top Gainers", True)
        render_top(col_loss, top_change.get("loss", [])[:10], "🔻 Top Losers", False)
