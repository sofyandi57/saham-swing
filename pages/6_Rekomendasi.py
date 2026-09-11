import datetime as dt

import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from screening import engine
from screening.condition_tree import FieldError
from screening.universe import LIQUID_DEFAULT
from utils import auth
from utils.formatting import compact_number, days_ago, last_trading_day, pct, rupiah
from utils.state import require_client

st.set_page_config(page_title="Rekomendasi - Swing Saham", page_icon="💡", layout="wide")
auth.require_login()
st.title("💡 Rekomendasi")
st.caption(
    "Tiga jenis rekomendasi siap pakai di atas engine Strategy Screener. "
    "Alat bantu penyaringan awal — bukan sinyal beli otomatis, selalu lakukan analisa sendiri sebelum entry."
)

client = require_client()
strategies = engine.load_all_strategies()

MAX_UNIVERSE = 60


@st.cache_data(ttl=3600, show_spinner=False)
def load_stock_list(_client):
    return _client.list_stock()


try:
    stocks = load_stock_list(client)
except InvezgoAPIError as e:
    st.error(f"Gagal memuat daftar saham: {e.message}")
    st.stop()

code_to_name = {s["code"]: s["name"] for s in stocks}
all_codes = sorted(code_to_name.keys())


def universe_picker(key_prefix: str) -> list[str]:
    default_universe = [c for c in LIQUID_DEFAULT if c in code_to_name] or all_codes[:30]
    with st.expander("⚙️ Sesuaikan universe saham (opsional)"):
        universe = st.multiselect(
            f"Universe (maks {MAX_UNIVERSE})", all_codes, default=default_universe,
            format_func=lambda c: f"{c} — {code_to_name.get(c, '')}", key=f"{key_prefix}_universe",
        )
    if len(universe) > MAX_UNIVERSE:
        st.warning(f"Terlalu banyak ({len(universe)}). Hanya {MAX_UNIVERSE} saham pertama diproses.")
        universe = universe[:MAX_UNIVERSE]
    return universe or default_universe


def run_with_progress(fn, *args, **kwargs):
    progress = st.progress(0.0, text="Memulai...")

    def on_progress(i, total, code):
        progress.progress((i + 1) / total, text=f"Memproses {code} ({i + 1}/{total})...")

    try:
        result = fn(*args, progress_cb=on_progress, **kwargs)
    finally:
        progress.empty()
    return result


tab_swing, tab_bpjs, tab_value = st.tabs(["📈 Swing", "⏱️ BPJS", "💎 Under Value"])

with tab_swing:
    st.subheader("📈 Rekomendasi Swing")
    st.caption(
        "Skor komposit multi-saham (`composite_ranking`): tren (30%) + konviksi broker (35%) + "
        "momentum (20%) + volume (15%), dinormalisasi sebagai percentile lintas universe hari itu. "
        "Skor 80 selalu berarti top-20% hari itu, apa pun kondisi pasar."
    )
    universe = universe_picker("swing")
    frm = days_ago(400)
    to = last_trading_day()

    if st.button("🚀 Cari Rekomendasi Swing", type="primary", disabled=not universe, key="run_swing"):
        strategy = strategies["composite_ranking"]
        result = run_with_progress(engine.run_ranking, client, strategy, universe, frm.isoformat(), to.isoformat())
        ranking = result["ranking"]
        if not ranking:
            st.warning("Tidak ada saham yang lolos universe_filter (likuiditas/histori data).")
        else:
            st.success(f"Top {len(ranking)} rekomendasi swing hari ini.")
            rows = []
            for r in ranking:
                row = {"Kode": r["code"], "Nama": code_to_name.get(r["code"], ""), "Harga": rupiah(r["last_close"]), "Skor": r["score_total"]}
                row.update({k.replace("_", " ").title(): v for k, v in r["sub_scores"].items()})
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if result["skipped"]:
            with st.expander(f"{len(result['skipped'])} saham dilewati"):
                st.dataframe(pd.DataFrame(result["skipped"]), hide_index=True, use_container_width=True)

with tab_bpjs:
    st.subheader("⏱️ Rekomendasi BPJS (Beli Pagi Jual Sore)")
    st.info(
        "**BPJS** = istilah trader retail untuk day trading: beli begitu market buka, jual sore hari yang sama. "
        "Karena Invezgo hanya punya data intraday *live* (bukan histori intraday untuk backtest), kandidat di "
        "bawah ini disaring dari data EOD: momentum kuat hari ini, volume abnormal, volatilitas harian cukup "
        "besar untuk profit intraday, dan broker top-5 net buy hari ini. **Jalankan pagi/awal sesi untuk hasil "
        "paling relevan** — data akan basi kalau dijalankan setelah market tutup."
    )
    universe_b = universe_picker("bpjs")
    frm_b = days_ago(60)
    to_b = last_trading_day()

    if st.button("🚀 Cari Kandidat BPJS", type="primary", disabled=not universe_b, key="run_bpjs"):
        strategy = strategies["bpjs_intraday"]
        try:
            results = run_with_progress(engine.run_screening, client, strategy, universe_b, frm_b.isoformat(), to_b.isoformat())
        except FieldError as e:
            st.error(str(e))
            results = []
        passed = [r for r in results if r.get("lolos")]
        st.success(f"{len(passed)} dari {len(universe_b)} saham lolos kriteria BPJS.")
        if passed:
            rows = []
            for r in passed:
                actual = {t["leaf"]["field"]: t["actual"] for t in r.get("trace", [])}
                rows.append({
                    "Kode": r["code"], "Nama": code_to_name.get(r["code"], ""),
                    "Harga": rupiah(r["last_close"]),
                    "Perubahan Hari Ini": pct(actual.get("change_pct_1d")),
                    "Volume Spike": f"{actual.get('volume_spike_ratio', 0):.2f}x" if actual.get("volume_spike_ratio") is not None else "-",
                    "ATR %": f"{actual.get('atr_pct', 0):.1f}%" if actual.get("atr_pct") is not None else "-",
                    "Broker Top-5 Hari Ini": compact_number(actual.get("broker_net_value_top5")),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.caption("Tidak ada kandidat yang lolos hari ini pada universe ini.")

with tab_value:
    st.subheader("💎 Rekomendasi Under Value")
    st.warning(
        "⚠️ **Data fundamental (PER/PBV/ROE) di sini bersifat best-effort.** Endpoint fundamental Invezgo belum "
        "terdokumentasi lengkap soal nama statistik yang valid, jadi hasil di bawah **wajib diverifikasi manual** "
        "(cek laporan keuangan langsung) sebelum dipakai keputusan apa pun."
    )
    st.caption(
        "Gaya value investing ala Lo Kheng Hong (\"Rule of 9\"): PER < 10, PBV < 1.5, PER × PBV < 9, ROE > 0 "
        "(supaya bukan value trap)."
    )
    universe_v = universe_picker("value")
    frm_v = days_ago(120)
    to_v = last_trading_day()

    if st.button("🚀 Cari Saham Under Value", type="primary", disabled=not universe_v, key="run_value"):
        strategy = strategies["under_value"]
        try:
            results = run_with_progress(engine.run_screening, client, strategy, universe_v, frm_v.isoformat(), to_v.isoformat())
        except FieldError as e:
            st.error(str(e))
            results = []
        passed = [r for r in results if r.get("lolos")]
        no_fundamentals = [
            r for r in results
            if not r.get("lolos") and not r.get("error") and r.get("universe_ok")
            and all(t["actual"] is None for t in r.get("trace", []) if t["leaf"]["field"] in ("per", "pbv", "roe"))
        ]
        st.success(f"{len(passed)} dari {len(universe_v)} saham lolos kriteria Under Value.")
        if passed:
            rows = []
            for r in passed:
                actual = {t["leaf"]["field"]: t["actual"] for t in r.get("trace", [])}
                rows.append({
                    "Kode": r["code"], "Nama": code_to_name.get(r["code"], ""),
                    "Harga": rupiah(r["last_close"]),
                    "PER": f"{actual.get('per'):.1f}" if actual.get("per") is not None else "-",
                    "PBV": f"{actual.get('pbv'):.2f}" if actual.get("pbv") is not None else "-",
                    "ROE": f"{actual.get('roe'):.1f}%" if actual.get("roe") is not None else "-",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.caption("Tidak ada saham yang lolos kriteria pada universe ini.")
        if no_fundamentals:
            st.caption(
                f"ℹ️ {len(no_fundamentals)} saham dilewati karena data PER/PBV/ROE tidak tersedia dari API "
                "untuk saham tersebut."
            )
