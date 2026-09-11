"""Offline smoke test for utils/key_store.py — save/load/clear round-trip,
both with and without APP_SECRET_KEY (encrypted vs obfuscated mode)."""
import sys
import types


class FakeSecrets(dict):
    def get(self, key, default=None):
        return super().get(key, default)


fake_st = types.SimpleNamespace(secrets=FakeSecrets())
sys.modules["streamlit"] = fake_st

from utils import key_store  # noqa: E402

print("=== Mode: no APP_SECRET_KEY (obfuscated) ===")
key_store.clear_api_key()
assert key_store.load_api_key() is None
assert not key_store.is_configured()
assert not key_store.is_encrypted()

key_store.save_api_key("ivz_test_secret_12345")
assert key_store.is_configured()
loaded = key_store.load_api_key()
print("loaded:", loaded)
assert loaded == "ivz_test_secret_12345", f"round-trip failed: {loaded!r}"

raw = key_store.STORE_PATH.read_bytes()
assert b"ivz_test_secret_12345" not in raw, "plaintext key leaked into stored file!"
print("raw file does not contain plaintext key: OK")

key_store.clear_api_key()
assert not key_store.is_configured()
assert key_store.load_api_key() is None
print("clear works: OK")

print("\n=== Mode: with APP_SECRET_KEY (encrypted) ===")
fake_st.secrets["APP_SECRET_KEY"] = "super-random-secret-for-testing"
assert key_store.is_encrypted()

key_store.save_api_key("ivz_another_key_67890")
loaded2 = key_store.load_api_key()
print("loaded:", loaded2)
assert loaded2 == "ivz_another_key_67890"

raw2 = key_store.STORE_PATH.read_bytes()
assert b"ivz_another_key_67890" not in raw2
print("raw encrypted file does not contain plaintext key: OK")

# Wrong secret should fail to decrypt (simulating a changed APP_SECRET_KEY)
fake_st.secrets["APP_SECRET_KEY"] = "a-completely-different-secret"
loaded_wrong = key_store.load_api_key()
print("loaded with wrong secret:", loaded_wrong)
assert loaded_wrong is None, "decrypted successfully with WRONG secret — bug!"
print("wrong-secret decrypt correctly fails: OK")

key_store.clear_api_key()
print("\nAll key_store checks passed.")
