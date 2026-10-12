"""API keys in the Windows Credential Manager (DPAPI) — runs on Windows only."""
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_credential_manager_roundtrip():
    from arc_backend.online.secrets import WindowsCredentialStore, create_secret_store

    store = create_secret_store()
    assert isinstance(store, WindowsCredentialStore) and store.persistent
    name = "arc-ci-test"
    try:
        assert store.get(name) is None
        store.set(name, "first-value-123")
        assert store.get(name) == "first-value-123"
        store.set(name, "second-value-123")  # overwrite in place
        assert store.get(name) == "second-value-123"
        assert WindowsCredentialStore().get(name) == "second-value-123"  # persisted, not cached
    finally:
        store.delete(name)
    assert store.get(name) is None
    assert store.delete(name) is False
