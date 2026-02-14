"""Tests for state module (LocalStateBackend)."""

import json
import os
import pytest
from apy_ops.state import LocalStateBackend, STATE_VERSION


class TestLocalStateBackend:
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

    def test_read_missing_file_returns_none(self, tmp_path):
        backend = LocalStateBackend(str(tmp_path / "nope.json"))
        assert backend.read() is None

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

    def test_init_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "deep" / "nested" / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        assert os.path.isfile(path)

    def test_lock_creates_lock_file(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        assert os.path.isfile(path + ".lock")
        backend.unlock()

    def test_double_lock_raises(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        with pytest.raises(RuntimeError, match="locked"):
            backend.lock()
        backend.unlock()

    def test_unlock_removes_lock(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.init("s", "r", "a")
        backend.lock()
        backend.unlock()
        assert not os.path.isfile(path + ".lock")

    def test_unlock_idempotent(self, tmp_path):
        path = str(tmp_path / "state.json")
        backend = LocalStateBackend(path)
        backend.unlock()  # no error even without lock

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
