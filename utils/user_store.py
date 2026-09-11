"""Persistent, hashed multi-user credential store backing utils/auth.py.

Passwords are never stored in plaintext: PBKDF2-HMAC-SHA256 with a random
per-user salt (stdlib only, no extra dependency). Stored at `.data/users.json`
(gitignored) — same persistence caveat as utils/key_store.py: survives
reruns/sleep-wake, wiped by a fresh redeploy on Streamlit Community Cloud.

On first access (no store file yet) a default Admin account is seeded so the
app is usable immediately; the account's own password can be changed from
the sidebar once logged in.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

STORE_DIR = Path(__file__).resolve().parent.parent / ".data"
STORE_PATH = STORE_DIR / "users.json"

DEFAULT_ADMIN_USERNAME = "sofyandisedar"
DEFAULT_ADMIN_PASSWORD = "Saya1234!"

_PBKDF2_ITERATIONS = 260_000


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS).hex()


def _make_record(password: str, role: str) -> dict:
    salt = os.urandom(16)
    return {"salt": salt.hex(), "hash": _hash_password(password, salt), "role": role}


def _write(users: dict) -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _seed_default() -> dict:
    users = {DEFAULT_ADMIN_USERNAME: _make_record(DEFAULT_ADMIN_PASSWORD, "admin")}
    _write(users)
    return users


def load_users() -> dict:
    if not STORE_PATH.exists():
        return _seed_default()
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _seed_default()


def verify_credentials(username: str, password: str) -> dict | None:
    record = load_users().get(username)
    if not record:
        return None
    if _hash_password(password, bytes.fromhex(record["salt"])) == record["hash"]:
        return {"username": username, "role": record["role"]}
    return None


def user_exists(username: str) -> bool:
    return username in load_users()


def add_user(username: str, password: str, role: str = "user") -> None:
    users = load_users()
    users[username] = _make_record(password, role)
    _write(users)


def remove_user(username: str) -> bool:
    """Returns False (no-op) if the user doesn't exist or would remove the
    last remaining admin account — checked here too, not just in the UI, so
    the app can never be left with zero admins."""
    users = load_users()
    if username not in users:
        return False
    if users[username]["role"] == "admin":
        admin_total = sum(1 for r in users.values() if r["role"] == "admin")
        if admin_total <= 1:
            return False
    users.pop(username)
    _write(users)
    return True


def change_password(username: str, new_password: str) -> bool:
    users = load_users()
    if username not in users:
        return False
    users[username] = _make_record(new_password, users[username]["role"])
    _write(users)
    return True


def list_users() -> list[dict]:
    return [{"username": u, "role": r["role"]} for u, r in sorted(load_users().items())]
