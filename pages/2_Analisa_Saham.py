import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from invezgo import InvezgoAPIError
from utils import auth
from utils.formatting import compact_number, days_ago, last_trading_day, pct, rupiah
from utils.indicators import build_trading_plan, position_size
from utils.state import require_client

st.set_page_config(page_title="Analisa Saham - Swing Saham", page_icon="📊", layout="wide")
auth.render_sidebar_widget()
st.title("📊 Analisa Saham & Trading Plan")

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

col_pick, col_range = st.columns([1, 2])
with col_pick:
    default_idx = options.index("BBCA") if "BBCA" in options else 0
    code = st.selectbox(
        "Kode Saham", options, index=default_idx,
        format_func=lambda c: f"{c} — {code_to_name.get(c, '')}",
    )
with col_range:
    c1, c2 = st.columns(2)
    frm = c1.date_input("Dari", value=days_ago(180), max_value=dt.date.today())
    to = c2.date_input("Sampai", value=last_trading_day(), max_value=dt.date.today())

with st.expander("⚙️ Parameter Support/Resistance & ATR"):
    sw_col, tol_col, atr_col = st.columns(3)
    swing_window = sw_col.slider("Sensitivitas swing (bar)", 2, 10, 3)
    tolerance_pct = tol_col.slider("Toleransi cluster level (%)", 0.5, 5.0, 1.5, step=0.5)
    atr_period = atr_col.slider("Periode ATR", 5, 30, 14)

if st.button("Analisa", type="primary"):
    try:
        with st.spinner("Mengambil data candlestick..."):
            candles = client.chart_stock(code, frm.isoformat(), to.isoformat())
        with st.spinner("Mengambil profil perusahaan..."):
            info = client.information(code)
    except InvezgoAPIError as e:
        st.error(e.message)
        st.stop()

    if not candles:
        st.warning("Tidak ada data candlestick pada rentang tanggal ini.")
        st.stop()

    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].astype(float)
    df = df.sort_values("date").reset_index(drop=True)

    if len(df) < (swing_window * 2 + 5):
        st.warning("Data terlalu sedikit untuk deteksi support/resistance yang andal — perpanjang rentang tanggal.")
        st.stop()

    plan = build_trading_plan(df, atr_period=atr_period, swing_window=swing_window, tolerance_pct=tolerance_pct)

    notation_list = (info or {}).get("notation") or []
    if notation_list:
        codes = ", ".join(n.get("notation", "?") for n in notation_list)
        st.warning(f"⚠️ Saham ini memiliki notasi khusus: **{codes}**. Cek detail di bawah sebelum bertransaksi.")

    header_l, header_r = st.columns([3, 1])
    with header_l:
        st.subheader(f"{code} — {code_to_name.get(code, '')}")
        st.caption(f"Sektor: {info.get('sector', '-')}  •  Papan: {info.get('board', '-')}")
    with header_r:
        st.metric("Harga Terakhir", rupiah(plan["entry"]))

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name=code, increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        )
    )
    for lv in plan["supports"]:
        fig.add_hline(y=lv["level"], line_dash="dot", line_color="#2e7d32", opacity=0.6,
                       annotation_text=f"S {rupiah(lv['level'])}", annotation_position="right")
    for lv in plan["resistances"]:
        fig.add_hline(y=lv["level"], line_dash="dot", line_color="#c62828", opacity=0.6,
                       annotation_text=f"R {rupiah(lv['level'])}", annotation_position="right")
    fig.add_hline(y=plan["stop"], line_color="#c62828", line_width=2,
                  annotation_text=f"Stop {rupiah(plan['stop'])}", annotation_position="left")
    fig.add_hline(y=plan["target1"], line_color="#2e7d32", line_width=2,
                  annotation_text=f"TP1 {rupiah(plan['target1'])}", annotation_position="left")
    fig.update_layout(
        height=550, xaxis_rangeslider_visible=False, margin=dict(t=30, b=10),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)

    vol_fig = go.Figure(go.Bar(x=df["date"], y=df["volume"], marker_color="#90a4ae"))
    vol_fig.update_layout(height=180, margin=dict(t=10, b=10), yaxis_title="Volume")
    st.plotly_chart(vol_fig, use_container_width=True)

    st.subheader("📋 Trading Plan (swing, berbasis ATR + Support/Resistance)")
    st.caption(
        "Perhitungan rule-based dari struktur harga historis — **bukan sinyal beli/jual**. "
        "Selalu validasi dengan analisa Anda sendiri dan manajemen risiko pribadi."
    )
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Entry (acuan)", rupiah(plan["entry"]))
    p2.metric("Stop Loss", rupiah(plan["stop"]), delta=f"-{(plan['entry']-plan['stop'])/plan['entry']*100:.1f}%", delta_color="inverse")
    p3.metric("Target 1", rupiah(plan["target1"]), delta=f"R:R {plan['rr1']:.2f}" if plan["rr1"] else None)
    p4.metric("Target 2", rupiah(plan["target2"]), delta=f"R:R {plan['rr2']:.2f}" if plan["rr2"] else None)
    if plan["atr"]:
        st.caption(f"ATR({atr_period}): {rupiah(plan['atr'])}")

    st.markdown("**Level Support**")
    if plan["supports"]:
        st.dataframe(
            pd.DataFrame(plan["supports"]).rename(columns={"level": "Harga", "touches": "Jumlah Sentuhan"}).assign(
                Harga=lambda d: d["Harga"].apply(rupiah)
            )[["Harga", "Jumlah Sentuhan"]],
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("Tidak terdeteksi support signifikan di rentang ini.")

    st.markdown("**Level Resistance**")
    if plan["resistances"]:
        st.dataframe(
            pd.DataFrame(plan["resistances"]).rename(columns={"level": "Harga", "touches": "Jumlah Sentuhan"}).assign(
                Harga=lambda d: d["Harga"].apply(rupiah)
            )[["Harga", "Jumlah Sentuhan"]],
            hide_index=True, use_container_width=True,
        )
    else:
        st.caption("Tidak terdeteksi resistance signifikan di rentang ini.")

    st.divider()
    st.subheader("🧮 Kalkulator Lot Sizing")
    lc1, lc2 = st.columns(2)
    capital = lc1.number_input("Modal (Rp)", min_value=100_000, value=10_000_000, step=100_000)
    risk_pct = lc2.slider("Risiko per transaksi (%)", 0.25, 5.0, 1.0, step=0.25)
    sizing = position_size(capital, risk_pct, plan["entry"], plan["stop"])
    s1, s2, s3 = st.columns(3)
    s1.metric("Jumlah Lot", f"{sizing['lots']} lot")
    s2.metric("Estimasi Biaya", rupiah(sizing["cost"]))
    s3.metric("Risiko Aktual", rupiah(sizing["actual_risk"]))

    st.session_state["last_analyzed_code"] = code
