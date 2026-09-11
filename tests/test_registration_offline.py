"""Offline smoke test for self-registration (utils/invite_store.py +
utils/auth.register) — invite code gating, always-"user"-role enforcement,
duplicate/short-password rejection."""
import shutil
import sys
import types


class FakeSessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name, value):
        self[name] = value


class FakeSecrets(dict):
    def get(self, key, default=None):
        return super().get(key, default)


fake_st = types.SimpleNamespace(secrets=FakeSecrets(), session_state=FakeSessionState())
sys.modules["streamlit"] = fake_st

from utils import auth, invite_store, user_store  # noqa: E402

if user_store.STORE_DIR.exists():
    shutil.rmtree(user_store.STORE_DIR)
user_store.load_users()  # seed default admin
invite_store.clear_code()

print("=== Registration blocked when no invite code configured ===")
ok, msg = auth.register("temanA", "PasswordA1!", "whatever")
assert ok is False and "belum diaktifkan" in msg, (ok, msg)
print("OK:", msg)

print("\n=== Admin activates registration ===")
code = invite_store.generate_code()
invite_store.set_code(code)
print("Generated code:", code)
assert invite_store.is_configured()

print("\n=== Wrong invite code rejected ===")
ok, msg = auth.register("temanA", "PasswordA1!", "WRONGCODE")
assert ok is False and "salah" in msg, (ok, msg)
print("OK:", msg)

print("\n=== Successful registration always gets role=user ===")
ok, msg = auth.register("temanA", "PasswordA1!", code)
assert ok is True, msg
record = user_store.verify_credentials("temanA", "PasswordA1!")
assert record == {"username": "temanA", "role": "user"}, record
print("OK: registered as", record)

print("\n=== Duplicate username rejected ===")
ok, msg = auth.register("temanA", "AnotherPass1!", code)
assert ok is False and "sudah dipakai" in msg, (ok, msg)
print("OK:", msg)

print("\n=== Short password rejected ===")
ok, msg = auth.register("temanB", "short1", code)
assert ok is False and "minimal 8" in msg, (ok, msg)
assert not user_store.user_exists("temanB")
print("OK:", msg)

print("\n=== Registration cannot grant admin role (register() has no role param) ===")
import inspect  # noqa: E402
sig = inspect.signature(auth.register)
assert "role" not in sig.parameters
print("OK: register() signature has no role parameter — always 'user'.")

shutil.rmtree(user_store.STORE_DIR)
print("\nAll registration checks passed.")
