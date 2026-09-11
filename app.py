import datetime as dt

import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from utils import auth, invite_store, key_store, user_store
from utils.formatting import last_trading_day, pct, rupiah
from utils.state import get_client

st.set_page_config(page_title="Swing Saham - Invezgo", page_icon="📈", layout="wide")

current_user = auth.require_login()

st.title("📈 Swing Saham — powered by Invezgo API")
st.caption(
    "Aplikasi bantu riset swing trading saham IDX: screener, chart + support/resistance, "
    "bandarmologi (broker flow), watchlist & alert. **Bukan rekomendasi/ajakan jual-beli — "
    "murni alat bantu riset & edukasi.**"
)

if auth.is_admin():
    st.divider()
    st.subheader("🔐 Panel Admin — Invezgo API Key")
    st.caption(
        "Key ini dipakai bersama oleh semua pengguna aplikasi — mereka tidak pernah melihat "
        "atau perlu mengisi key ini sendiri."
    )

    if key_store.is_configured():
        st.success("API Key aktif dan tersimpan.")
    else:
        st.warning("Belum ada API Key tersimpan. Aplikasi tidak akan berfungsi untuk pengguna sampai diisi.")

    if not key_store.is_encrypted():
        st.warning(
            "⚠️ `APP_SECRET_KEY` belum diset di Streamlit secrets — key tersimpan tanpa enkripsi kuat. "
            "Disarankan set `APP_SECRET_KEY` (string acak bebas) untuk keamanan lebih baik."
        )

    with st.form("update_key_form", clear_on_submit=True):
        new_key = st.text_input("API Key baru", type="password", placeholder="ivz_xxx...")
        col_a, col_b = st.columns(2)
        save_clicked = col_a.form_submit_button("💾 Simpan", use_container_width=True)
        clear_clicked = col_b.form_submit_button("🗑️ Hapus Key Tersimpan", use_container_width=True)

    if save_clicked:
        if new_key.strip():
            key_store.save_api_key(new_key.strip())
            st.session_state.pop("_client", None)
            st.session_state.pop("_client_key", None)
            st.success("API Key disimpan.")
            st.rerun()
        else:
            st.warning("Isi API Key terlebih dahulu.")

    if clear_clicked:
        key_store.clear_api_key()
        st.session_state.pop("_client", None)
        st.session_state.pop("_client_key", None)
        st.info("API Key dihapus dari penyimpanan lokal (kembali ke `INVEZGO_API_KEY` di secrets, jika ada).")
        st.rerun()

    st.caption(
        "Catatan persistensi: key tersimpan di berkas lokal terenkripsi dan bertahan lintas sesi/pengguna "
        "selama container aplikasi tidak di-*redeploy*. Untuk persistensi permanen (bertahan lintas redeploy), "
        "set juga `INVEZGO_API_KEY` di Streamlit Cloud secrets sebagai cadangan — key dari panel ini akan "
        "dipakai duluan kalau ada, lalu jatuh ke secrets kalau tidak."
    )

    st.divider()
    st.subheader("👥 Kelola User")
    st.caption("Buat akun untuk orang lain supaya mereka bisa login sebagai User (tanpa akses API Key).")

    users = user_store.list_users()
    users_df = pd.DataFrame(users).rename(columns={"username": "Username", "role": "Role"})
    st.dataframe(users_df, hide_index=True, use_container_width=True)

    with st.expander("➕ Tambah User Baru"):
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input("Username baru")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["user", "admin"])
            submit_add = st.form_submit_button("Tambah User")
        if submit_add:
            new_username_clean = new_username.strip()
            if not new_username_clean or not new_password:
                st.warning("Isi username dan password.")
            elif user_store.user_exists(new_username_clean):
                st.error("Username sudah dipakai.")
            elif len(new_password) < 8:
                st.error("Password minimal 8 karakter.")
            else:
                user_store.add_user(new_username_clean, new_password, new_role)
                st.success(f"User '{new_username_clean}' ditambahkan dengan role {new_role}.")
                st.rerun()

    with st.expander("🗑️ Hapus User"):
        removable = [u["username"] for u in users if u["username"] != current_user["username"]]
        if removable:
            to_remove = st.selectbox("Pilih user", removable)
            if st.button("Hapus User Ini", key="remove_user_btn"):
                if user_store.remove_user(to_remove):
                    st.success(f"User '{to_remove}' dihapus.")
                    st.rerun()
                else:
                    st.error("Tidak bisa menghapus user ini (mungkin admin terakhir).")
        else:
            st.caption("Tidak ada user lain untuk dihapus.")

    st.divider()
    st.subheader("🎟️ Kode Registrasi")
    st.caption(
        "Bagikan kode ini ke teman yang ingin daftar akun sendiri lewat tab **Daftar** di halaman login "
        "— mereka selalu mendapat role User, tidak pernah Admin."
    )

    if invite_store.is_configured():
        st.success("Registrasi aktif — bagikan kode di bawah ini.")
        st.code(invite_store.get_code(), language=None)
    else:
        st.info("Registrasi belum aktif. Buat kode untuk mengaktifkannya.")

    col_gen, col_clear = st.columns(2)
    if col_gen.button("🎲 Generate Kode Baru", use_container_width=True):
        invite_store.set_code(invite_store.generate_code())
        st.rerun()
    if col_clear.button(
        "🚫 Nonaktifkan Registrasi", use_container_width=True, disabled=not invite_store.is_configured()
    ):
        invite_store.clear_code()
        st.rerun()

    with st.expander("Atau set kode custom"):
        with st.form("custom_code_form", clear_on_submit=True):
            custom_code = st.text_input("Kode custom")
            submit_custom = st.form_submit_button("Simpan Kode")
        if submit_custom:
            if custom_code.strip():
                invite_store.set_code(custom_code.strip())
                st.success("Kode disimpan.")
                st.rerun()
            else:
                st.warning("Isi kode terlebih dahulu.")

st.divider()

st.subheader("Navigasi")
c1, c2, c3, c4, c5 = st.columns(5)
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
with c5:
    st.page_link("pages/5_Strategy_Screener.py", label="🧠 Strategy Screener", icon="🧠")
    st.caption("11 strategi swing + bandarmologi siap pakai, plus ranking komposit multi-saham.")

st.divider()

client = get_client()
if client is None:
    if auth.is_admin():
        st.info("👆 Isi API Key di panel Admin di atas untuk mengaktifkan aplikasi.")
    else:
        st.info("Aplikasi belum dikonfigurasi oleh admin. Silakan hubungi admin aplikasi ini.")
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
