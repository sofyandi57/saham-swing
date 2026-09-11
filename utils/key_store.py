"""Persistent storage for the Invezgo API key, written by the Admin panel so
the key survives across sessions/users without every viewer re-entering it.

Storage: a local file (`.data/api_key.enc`, gitignored) encrypted with a key
derived from the `APP_SECRET_KEY` secret. If `APP_SECRET_KEY` isn't
configured, we still persist the key (better than forcing re-entry every
run) but only lightly obfuscated — `is_encrypted()` reports which mode is
active so the UI can warn the admin.

Note on Streamlit Community Cloud: this file persists across reruns and
sleep/wake, but a fresh deploy (new git clone) wipes it — set
`INVEZGO_API_KEY` in Streamlit secrets too as a durable fallback baseline
(`utils/state.py` falls back to it automatically when this store is empty).
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import streamlit as st

STORE_DIR = Path(__file__).resolve().parent.parent / ".data"
STORE_PATH = STORE_DIR / "api_key.enc"

_OBFUSCATION_MARKER = b"PLAIN:"


def _get_app_secret() -> str | None:
    try:
        return st.secrets.get("APP_SECRET_KEY") or None
    except Exception:
        return None


def is_encrypted() -> bool:
    return _get_app_secret() is not None


def _fernet():
    secret = _get_app_secret()
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def save_api_key(plain_key: str) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    fernet = _fernet()
    if fernet:
        payload = fernet.encrypt(plain_key.encode("utf-8"))
    else:
        payload = _OBFUSCATION_MARKER + base64.b64encode(plain_key.encode("utf-8"))
    STORE_PATH.write_bytes(payload)


def load_api_key() -> str | None:
    if not STORE_PATH.exists():
        return None
    try:
        payload = STORE_PATH.read_bytes()
    except OSError:
        return None
    if not payload:
        return None

    if payload.startswith(_OBFUSCATION_MARKER):
        try:
            return base64.b64decode(payload[len(_OBFUSCATION_MARKER):]).decode("utf-8")
        except Exception:
            return None

    fernet = _fernet()
    if not fernet:
        return None
    try:
        return fernet.decrypt(payload).decode("utf-8")
    except Exception:
        return None


def clear_api_key() -> None:
    if STORE_PATH.exists():
        STORE_PATH.unlink()


def is_configured() -> bool:
    return STORE_PATH.exists()
