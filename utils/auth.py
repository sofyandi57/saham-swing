"""Admin/User role gate. There is no per-user account system — just one
shared Admin password (from secrets) that unlocks the API key management
panel. Everyone else is a regular User: full app access, zero visibility
into the API key.
"""
from __future__ import annotations

import streamlit as st

SESSION_KEY = "is_admin"


def get_admin_password() -> str | None:
    try:
        return st.secrets.get("ADMIN_PASSWORD") or None
    except Exception:
        return None


def is_admin() -> bool:
    return bool(st.session_state.get(SESSION_KEY, False))


def login(password: str) -> bool:
    configured = get_admin_password()
    if not configured:
        return False
    if password == configured:
        st.session_state[SESSION_KEY] = True
        return True
    return False


def logout() -> None:
    st.session_state[SESSION_KEY] = False


def render_sidebar_widget() -> None:
    """Small admin login/status widget — call from every page's sidebar."""
    admin_password_set = get_admin_password() is not None

    with st.sidebar:
        st.divider()
        if is_admin():
            st.success("🔐 Masuk sebagai Admin")
            if st.button("Logout Admin", use_container_width=True):
                logout()
                st.rerun()
        else:
            with st.expander("🔐 Admin Login"):
                if not admin_password_set:
                    st.caption(
                        "Login admin belum dikonfigurasi. Set `ADMIN_PASSWORD` di Streamlit secrets terlebih dahulu."
                    )
                else:
                    pwd = st.text_input("Password Admin", type="password", key="admin_pwd_input")
                    if st.button("Login", key="admin_login_btn"):
                        if login(pwd):
                            st.rerun()
                        else:
                            st.error("Password salah.")
