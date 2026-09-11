import pandas as pd
import streamlit as st

from invezgo import InvezgoAPIError
from utils import auth
from utils.state import require_client

st.set_page_config(page_title="Watchlist & Alert - Swing Saham", page_icon="⭐", layout="wide")
auth.require_login()
st.title("⭐ Watchlist & Alert")

client = require_client()


def item_id(item: dict) -> str:
    return str(item.get("id") or item.get("_id") or "")


tab_watchlist, tab_alert = st.tabs(["📌 Watchlist", "🔔 Alert"])

with tab_watchlist:
    st.subheader("Grup Watchlist")

    try:
        with st.spinner("Memuat grup..."):
            groups = client.watchlist_groups() or []
    except InvezgoAPIError as e:
        st.error(e.message)
        groups = []

    with st.form("new_group_form", clear_on_submit=True):
        new_group_name = st.text_input("Nama grup baru", placeholder="mis. Swing Watchlist")
        if st.form_submit_button("Buat Grup"):
            if new_group_name.strip():
                try:
                    client.create_watchlist_group(new_group_name.strip())
                    st.success("Grup dibuat.")
                    st.cache_data.clear()
                    st.rerun()
                except InvezgoAPIError as e:
                    st.error(e.message)
            else:
                st.warning("Nama grup tidak boleh kosong.")

    if not groups:
        st.info("Belum ada grup watchlist. Buat grup terlebih dahulu di atas.")
    else:
        group_options = {item_id(g): g.get("name", item_id(g)) for g in groups}
        selected_group = st.selectbox(
            "Pilih grup", list(group_options.keys()), format_func=lambda gid: group_options.get(gid, gid)
        )

        st.divider()
        st.markdown("**Tambah saham ke watchlist**")
        with st.form("add_watchlist_form", clear_on_submit=True):
            wc1, wc2, wc3 = st.columns(3)
            code = wc1.text_input("Kode Saham (mis. BBCA)").upper().strip()
            price = wc2.number_input("Harga acuan/target (Rp)", min_value=1.0, value=1000.0, step=1.0)
            note = wc3.text_input("Catatan (opsional)", max_chars=150)
            if st.form_submit_button("Tambah ke Watchlist"):
                if not code:
                    st.warning("Isi kode saham.")
                else:
                    try:
                        client.add_watchlist_item(selected_group, code, price, scope=["private"], note=note or None)
                        st.success(f"{code} ditambahkan ke watchlist.")
                        st.rerun()
                    except InvezgoAPIError as e:
                        st.error(e.message)

        st.divider()
        try:
            with st.spinner("Memuat watchlist..."):
                items = client.watchlist_items(selected_group) or []
        except InvezgoAPIError as e:
            st.error(e.message)
            items = []

        if not items:
            st.caption("Watchlist grup ini masih kosong.")
        else:
            df = pd.DataFrame(items)
            display_cols = [c for c in ["code", "price", "note", "createdAt"] if c in df.columns]
            st.dataframe(df[display_cols] if display_cols else df, hide_index=True, use_container_width=True)

            ids = [item_id(it) for it in items]
            labels = {item_id(it): f"{it.get('code', '?')} ({item_id(it)[:6]}...)" for it in items}
            to_delete = st.multiselect("Pilih item untuk dihapus", ids, format_func=lambda i: labels.get(i, i))
            if st.button("Hapus item terpilih", disabled=not to_delete):
                try:
                    client.delete_watchlist_items(to_delete)
                    st.success("Item dihapus.")
                    st.rerun()
                except InvezgoAPIError as e:
                    st.error(e.message)

with tab_alert:
    st.subheader("Alert Formula")
    st.caption(
        "Alert dijalankan otomatis oleh sistem Invezgo sesuai interval yang dipilih, dan "
        "notifikasi dikirim lewat channel yang terhubung ke akun Invezgo Anda (app/website Invezgo)."
    )

    EVERY_OPTIONS = [
        "FOURTY_FIVE_SECONDS", "ONE_MINUTE", "FIVE_MINUTES", "TEN_MINUTES",
        "THIRTY_MINUTES", "ONE_HOUR", "END_SESSION", "END_OF_DAY",
    ]
    SEND_OPTIONS = ["IN_OUT", "IN", "OUT"]

    with st.form("new_alert_form"):
        name = st.text_input("Nama Alert", placeholder="mis. Breakout Volume BBCA")
        description = st.text_area("Deskripsi (opsional)", max_chars=300)
        formula = st.text_input("Formula", placeholder="change > 3 and volume > 10000000")
        c1, c2 = st.columns(2)
        every = c1.selectbox("Interval cek", EVERY_OPTIONS, index=EVERY_OPTIONS.index("END_OF_DAY"))
        send = c2.selectbox("Kirim saat", SEND_OPTIONS, format_func=lambda x: {
            "IN_OUT": "Masuk & Keluar kriteria", "IN": "Masuk kriteria saja", "OUT": "Keluar kriteria saja",
        }[x])

        test_col, submit_col = st.columns(2)
        do_test = test_col.form_submit_button("🧪 Uji Formula")
        do_submit = submit_col.form_submit_button("Buat Alert", type="primary")

        if do_test:
            if not formula.strip():
                st.warning("Isi formula terlebih dahulu.")
            else:
                try:
                    result = client.test_alert(formula.strip())
                    n = len(result) if isinstance(result, list) else "?"
                    st.success(f"Formula valid — cocok untuk {n} saham saat ini.")
                    if isinstance(result, list) and result:
                        st.dataframe(pd.DataFrame(result[:20]), hide_index=True, use_container_width=True)
                except InvezgoAPIError as e:
                    st.error(e.message)

        if do_submit:
            if not (name.strip() and formula.strip()):
                st.warning("Nama dan formula wajib diisi.")
            else:
                try:
                    client.create_alert(name.strip(), formula.strip(), every, send, description.strip() or None)
                    st.success("Alert berhasil dibuat.")
                    st.rerun()
                except InvezgoAPIError as e:
                    st.error(e.message)

    st.divider()
    st.markdown("**Alert Aktif**")
    try:
        with st.spinner("Memuat alert..."):
            alerts = client.alerts_list() or []
    except InvezgoAPIError as e:
        st.error(e.message)
        alerts = []

    if not alerts:
        st.caption("Belum ada alert.")
    else:
        for a in alerts:
            aid = item_id(a)
            with st.container(border=True):
                ac1, ac2 = st.columns([4, 1])
                with ac1:
                    st.markdown(f"**{a.get('name', '-')}**")
                    st.caption(a.get("formula", "-"))
                    st.caption(f"Interval: {a.get('every', '-')} • Kirim: {a.get('send', '-')}")
                with ac2:
                    if st.button("Hapus", key=f"del_alert_{aid}"):
                        try:
                            client.delete_alert(aid)
                            st.success("Alert dihapus.")
                            st.rerun()
                        except InvezgoAPIError as e:
                            st.error(e.message)
