"""Tests for state module (LocalStateBackend, get_backend)."""

import json
import os
from types import SimpleNamespace

import pytest

from apy_ops.state import LocalStateBackend, get_backend, STATE_VERSION


class TestLocalStateBackend:
    # Tests that init creates state file with correct structure and metadata.
    def test_init_creates_file(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        state = backend.init("sub-1", "rg-1", "apim-1")
        assert os.path.isfile(path)
        assert state["version"] == STATE_VERSION
        assert state["apim_service"] == "apim-1"
        assert state["resource_group"] == "rg-1"
        assert state["subscription_id"] == "sub-1"
        assert state["artifacts"] == {}

    # Tests that read returns None when state file does not exist.
    def test_read_missing_file_returns_none(self, tmp_path):
        backend = LocalStateBackend(str(tmp_path / "nope.json"))
        assert backend.read() is None

    # Tests that write and read roundtrip state data correctly.
    def test_write_read_roundtrip(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        state = backend.init("s", "r", "a")
        state["artifacts"]["api:echo"] = {
            "type": "api", "id": "echo",
            "hash": "sha256:abc", "properties": {"displayName": "Echo"},
        }
        backend.write(state)
        loaded = backend.read()
        assert loaded["artifacts"]["api:echo"]["id"] == "echo"

    # Tests that init creates nested parent directories if needed.
    def test_init_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        assert os.path.isfile(path)

    # Tests that lock creates lock file.
    def test_lock_creates_lock_file(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        assert os.path.isfile(path + ".lock")
        backend.unlock()

    # Tests that lock raises when already locked.
    def test_double_lock_raises(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        with pytest.raises(RuntimeError, match="locked"):
            backend.lock()
        backend.unlock()

    # Tests that unlock removes lock file.
    def test_unlock_removes_lock(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        backend.unlock()
        assert not os.path.isfile(path + ".lock")

    # Tests that unlock is idempotent even without existing lock.
    def test_unlock_idempotent(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.unlock()  # no error even without lock

    # Tests that force_unlock removes lock without checking ownership.
    def test_force_unlock(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        backend.force_unlock()
        assert not os.path.isfile(path + ".lock")
        # Can lock again after force unlock
        backend.lock()
        backend.unlock()


class TestGetBackendAzureValidation:
    """Test that get_backend(backend=azure) requires storage params."""

    # Tests that get_backend raises when Azure backend parameters are missing.
    def test_azure_backend_raises_when_params_missing(self, monkeypatch):
        monkeypatch.delenv("APIM_STATE_STORAGE_ACCOUNT", raising=False)
        monkeypatch.delenv("APIM_STATE_CONTAINER", raising=False)
        monkeypatch.delenv("APIM_STATE_BLOB", raising=False)
        args = SimpleNamespace(
            backend="azure",
            backend_storage_account=None,
            backend_container=None,
            backend_blob=None,
            client_id=None,
            client_secret=None,
            tenant_id=None,
        )
        with pytest.raises(ValueError, match="Azure state backend requires"):
            get_backend(args)

    # Tests that get_backend error message lists all missing Azure backend parameters.
    def test_azure_backend_raises_lists_missing_params(self, monkeypatch):
        monkeypatch.delenv("APIM_STATE_STORAGE_ACCOUNT", raising=False)
        monkeypatch.delenv("APIM_STATE_CONTAINER", raising=False)
        monkeypatch.delenv("APIM_STATE_BLOB", raising=False)
        args = SimpleNamespace(
            backend="azure",
            backend_storage_account=None,
            backend_container=None,
            backend_blob=None,
            client_id=None,
            client_secret=None,
            tenant_id=None,
        )
        with pytest.raises(ValueError) as exc_info:
            get_backend(args)
        msg = str(exc_info.value)
        assert "backend-storage-account" in msg or "APIM_STATE_STORAGE_ACCOUNT" in msg
        assert "backend-container" in msg or "APIM_STATE_CONTAINER" in msg
        assert "backend-blob" in msg or "APIM_STATE_BLOB" in msg

    # Tests that get_backend returns LocalStateBackend for local backend type.
    def test_local_backend_unchanged(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        args = SimpleNamespace(
            backend="local",
            state_file=state_file,
        )
        backend = get_backend(args)
        assert isinstance(backend, LocalStateBackend)
        assert backend.state_file == state_file

    # Tests that get_backend raises when local backend state-file is not specified.
    def test_local_backend_no_state_file_raises(self, monkeypatch):
        monkeypatch.delenv("APIM_STATE_FILE", raising=False)
        args = SimpleNamespace(
            backend="local",
            state_file=None,
        )
        with pytest.raises(ValueError, match="state-file"):
            get_backend(args)
