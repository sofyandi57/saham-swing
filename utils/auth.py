"""App-wide login gate + role check. Two roles, both requiring an account:
Admin (manages the shared API key and user accounts) and User (full feature
access, zero visibility into the API key). Backed by utils/user_store.py.
"""
from __future__ import annotations

import streamlit as st

from utils import invite_store, user_store

SESSION_KEY = "current_user"


def current_user() -> dict | None:
    return st.session_state.get(SESSION_KEY)


def is_authenticated() -> bool:
    return current_user() is not None


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == "admin")


def login(username: str, password: str) -> bool:
    user = user_store.verify_credentials(username.strip(), password)
    if user:
        st.session_state[SESSION_KEY] = user
        return True
    return False


def logout() -> None:
    st.session_state.pop(SESSION_KEY, None)


def register(username: str, password: str, invite_code: str) -> tuple[bool, str]:
    """Self-registration always creates a plain "user" account — never
    "admin". That role can only be granted from the Admin panel."""
    configured_code = invite_store.get_code()
    if not configured_code:
        return False, "Registrasi belum diaktifkan oleh admin."
    if invite_code != configured_code:
        return False, "Kode undangan salah."

    username = username.strip()
    if not username:
        return False, "Username tidak boleh kosong."
    if user_store.user_exists(username):
        return False, "Username sudah dipakai."
    if len(password) < 8:
        return False, "Password minimal 8 karakter."

    user_store.add_user(username, password, role="user")
    return True, ""


def _render_login_form() -> None:
    st.title("📈 Swing Saham")
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        tab_login, tab_register = st.tabs(["Masuk", "Daftar"])

        with tab_login:
            st.caption("Masuk untuk mengakses aplikasi.")
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                submitted = st.form_submit_button("Masuk", use_container_width=True)
            if submitted:
                if login(username, password):
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

        with tab_register:
            st.caption("Daftar akun User baru — butuh kode undangan dari admin aplikasi ini.")
            with st.form("register_form", clear_on_submit=True):
                new_username = st.text_input("Username", key="reg_username")
                new_password = st.text_input("Password", type="password", key="reg_password")
                new_password2 = st.text_input("Ulangi Password", type="password", key="reg_password2")
                invite_code = st.text_input("Kode Undangan", key="reg_code")
                submitted_reg = st.form_submit_button("Daftar", use_container_width=True)
            if submitted_reg:
                if new_password != new_password2:
                    st.error("Konfirmasi password tidak cocok.")
                else:
                    ok, message = register(new_username, new_password, invite_code)
                    if ok:
                        login(new_username, new_password)
                        st.rerun()
                    else:
                        st.error(message)


def require_login() -> dict:
    """Call right after st.set_page_config() on every page. Blocks the rest
    of the page (via st.stop) until someone is logged in."""
    if not is_authenticated():
        _render_login_form()
        st.stop()
    render_sidebar_status()
    return current_user()


def render_sidebar_status() -> None:
    user = current_user()
    with st.sidebar:
        st.divider()
        role_label = "Admin" if user["role"] == "admin" else "User"
        st.success(f"👤 {user['username']} ({role_label})")
        if st.button("Logout", use_container_width=True, key="logout_btn"):
            logout()
            st.rerun()

        with st.expander("🔑 Ganti Password Saya"):
            with st.form("change_own_password_form", clear_on_submit=True):
                old_pwd = st.text_input("Password lama", type="password", key="old_pwd")
                new_pwd = st.text_input("Password baru", type="password", key="new_pwd")
                new_pwd2 = st.text_input("Ulangi password baru", type="password", key="new_pwd2")
                submit_pwd = st.form_submit_button("Ganti Password")
            if submit_pwd:
                if not user_store.verify_credentials(user["username"], old_pwd):
                    st.error("Password lama salah.")
                elif len(new_pwd) < 8:
                    st.error("Password baru minimal 8 karakter.")
                elif new_pwd != new_pwd2:
                    st.error("Konfirmasi password baru tidak cocok.")
                else:
                    user_store.change_password(user["username"], new_pwd)
                    st.success("Password berhasil diganti.")
