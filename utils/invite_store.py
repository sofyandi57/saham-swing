"""Persistent registration-invite code, so friends can self-register as
plain Users (never Admin — that role can only be granted from the Admin
panel) without the Admin manually creating each account.

Stored at `.data/registration_code.json` (gitignored). Unlike the API key,
this is meant to be read back and shared by the Admin, so it's kept in
plain text rather than encrypted — it isn't a credential to the Invezgo
API, just a shared gate on the registration form.
"""
from __future__ import annotations

import json
import secrets as pysecrets
from pathlib import Path

STORE_DIR = Path(__file__).resolve().parent.parent / ".data"
STORE_PATH = STORE_DIR / "registration_code.json"

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no ambiguous chars (0/O, 1/I/l)


def get_code() -> str | None:
    if not STORE_PATH.exists():
        return None
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get("code") or None


def set_code(code: str) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps({"code": code}), encoding="utf-8")


def clear_code() -> None:
    if STORE_PATH.exists():
        STORE_PATH.unlink()


def is_configured() -> bool:
    return get_code() is not None


def generate_code(length: int = 8) -> str:
    return "".join(pysecrets.choice(_ALPHABET) for _ in range(length))
