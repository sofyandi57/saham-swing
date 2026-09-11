from __future__ import annotations

import streamlit as st

from invezgo import InvezgoClient
from utils import auth, key_store


def get_api_key() -> str | None:
    """Resolve the shared Invezgo API key. Admin-configured persistent
    storage takes precedence; `INVEZGO_API_KEY` in secrets is the durable
    fallback baseline (survives redeploys that wipe the local key store).
    Regular Users never supply a key themselves — this is the only source.
    """
    stored = key_store.load_api_key()
    if stored:
        return stored
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
        if auth.is_admin():
            st.warning("API Key belum dikonfigurasi. Isi di panel Admin pada halaman **Home**.")
            st.page_link("app.py", label="Ke halaman Home", icon="🏠")
        else:
            st.info("Aplikasi belum dikonfigurasi oleh admin. Silakan hubungi admin aplikasi ini.")
        st.stop()
    return client
