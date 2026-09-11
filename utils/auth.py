"""App-wide login gate + role check. Two roles, both requiring an account:
Admin (manages the shared API key and user accounts) and User (full feature
access, zero visibility into the API key). Backed by utils/user_store.py.
"""
from __future__ import annotations

import streamlit as st

from utils import user_store

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


def _render_login_form() -> None:
    st.title("📈 Swing Saham")
    st.caption("Masuk untuk mengakses aplikasi.")
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Masuk", use_container_width=True)
        if submitted:
            if login(username, password):
                st.rerun()
            else:
                st.error("Username atau password salah.")


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
