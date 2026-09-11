"""Offline smoke test for utils/user_store.py — seeding, login verification,
add/remove/change-password, and the last-admin removal guard."""
import shutil

from utils import user_store

# Isolate from any real .data/users.json on disk for this test run.
if user_store.STORE_DIR.exists():
    shutil.rmtree(user_store.STORE_DIR)

print("=== Default admin seeding ===")
users = user_store.load_users()
assert user_store.DEFAULT_ADMIN_USERNAME in users
print("Seeded users:", list(users.keys()))

result = user_store.verify_credentials(user_store.DEFAULT_ADMIN_USERNAME, user_store.DEFAULT_ADMIN_PASSWORD)
assert result == {"username": user_store.DEFAULT_ADMIN_USERNAME, "role": "admin"}, result
print("Default admin login: OK")

wrong = user_store.verify_credentials(user_store.DEFAULT_ADMIN_USERNAME, "wrong-password")
assert wrong is None
print("Wrong password correctly rejected: OK")

raw = user_store.STORE_PATH.read_text(encoding="utf-8")
assert user_store.DEFAULT_ADMIN_PASSWORD not in raw, "plaintext password leaked into users.json!"
print("Stored file does not contain plaintext password: OK")

print("\n=== add_user / verify / list_users ===")
user_store.add_user("budi", "PasswordBudi1!", role="user")
assert user_store.user_exists("budi")
assert user_store.verify_credentials("budi", "PasswordBudi1!")["role"] == "user"
assert user_store.verify_credentials("budi", "wrong") is None
listing = user_store.list_users()
print("list_users:", listing)
assert {"username": "budi", "role": "user"} in listing
assert {"username": user_store.DEFAULT_ADMIN_USERNAME, "role": "admin"} in listing

print("\n=== change_password ===")
assert user_store.change_password("budi", "NewPasswordBudi2!")
assert user_store.verify_credentials("budi", "NewPasswordBudi2!") is not None
assert user_store.verify_credentials("budi", "PasswordBudi1!") is None
print("change_password round-trip: OK")
assert user_store.change_password("nobody", "x") is False
print("change_password on nonexistent user returns False: OK")

print("\n=== remove_user + last-admin guard ===")
assert user_store.remove_user("budi") is True
assert not user_store.user_exists("budi")
print("remove_user on a regular user: OK")

# Only one admin exists (the seeded default) — must refuse to remove it.
assert user_store.remove_user(user_store.DEFAULT_ADMIN_USERNAME) is False
assert user_store.user_exists(user_store.DEFAULT_ADMIN_USERNAME)
print("last-admin removal correctly refused: OK")

# Add a second admin — now removing one of the two should succeed.
user_store.add_user("second_admin", "SecondAdmin1!", role="admin")
assert user_store.remove_user(user_store.DEFAULT_ADMIN_USERNAME) is True
assert user_store.user_exists("second_admin")
assert not user_store.user_exists(user_store.DEFAULT_ADMIN_USERNAME)
print("removal succeeds when another admin remains: OK")

assert user_store.remove_user("ghost") is False
print("remove_user on nonexistent user returns False: OK")

shutil.rmtree(user_store.STORE_DIR)
print("\nAll user_store checks passed.")
