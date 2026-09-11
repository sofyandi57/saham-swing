from __future__ import annotations

import streamlit as st

from invezgo import InvezgoClient


def get_api_key() -> str | None:
    key = st.session_state.get("invezgo_api_key")
    if key:
        return key
    try:
        secret_key = st.secrets.get("INVEZGO_API_KEY")
    except Exception:
        secret_key = None
    return secret_key or None


def get_client() -> InvezgoClient | None:
    key = get_api_key()
    if not key:
        return None
    if st.session_state.get("_client_key") != key:
        st.session_state["_client"] = InvezgoClient(key)
        st.session_state["_client_key"] = key
    return st.session_state["_client"]


def require_client() -> InvezgoClient:
    client = get_client()
    if client is None:
        st.warning("Masukkan Invezgo API Key Anda di halaman **Home** terlebih dahulu.")
        st.page_link("app.py", label="Ke halaman Home", icon="🏠")
        st.stop()
    return client
