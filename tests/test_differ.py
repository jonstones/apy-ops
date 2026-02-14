"""Tests for differ module."""

from apy_ops.differ import diff, CREATE, UPDATE, DELETE, NOOP


def _artifact(type_, id_, hash_, props=None):
    return {
        "type": type_,
        "id": id_,
        "hash": hash_,
        "properties": props or {"displayName": id_},
    }


class TestDiff:
    def test_empty_both(self):
        assert diff({}, {}) == []

    def test_new_artifact_is_create(self):
        local = {"api:echo": _artifact("api", "echo", "h1")}
        changes = diff(local, {})
        assert len(changes) == 1
        assert changes[0]["action"] == CREATE
        assert changes[0]["key"] == "api:echo"

    def test_removed_artifact_is_delete(self):
        state = {"api:echo": _artifact("api", "echo", "h1")}
        changes = diff({}, state)
        assert len(changes) == 1
        assert changes[0]["action"] == DELETE

    def test_same_hash_is_noop(self):
        art = _artifact("api", "echo", "h1")
        changes = diff({"api:echo": art}, {"api:echo": art})
        assert len(changes) == 1
        assert changes[0]["action"] == NOOP

    def test_different_hash_is_update(self):
        local = {"api:echo": _artifact("api", "echo", "h2", {"displayName": "echo", "path": "/new"})}
        state = {"api:echo": _artifact("api", "echo", "h1", {"displayName": "echo", "path": "/old"})}
        changes = diff(local, state)
        assert len(changes) == 1
        assert changes[0]["action"] == UPDATE
        assert "path" in changes[0]["detail"]

    def test_mixed_scenario(self):
        local = {
            "api:kept": _artifact("api", "kept", "same"),
            "api:new": _artifact("api", "new", "h1"),
            "api:changed": _artifact("api", "changed", "h2"),
        }
        state = {
            "api:kept": _artifact("api", "kept", "same"),
            "api:old": _artifact("api", "old", "h1"),
            "api:changed": _artifact("api", "changed", "h1"),
        }
        changes = diff(local, state)
        actions = {c["key"]: c["action"] for c in changes}
        assert actions["api:kept"] == NOOP
        assert actions["api:new"] == CREATE
        assert actions["api:old"] == DELETE
        assert actions["api:changed"] == UPDATE

    def test_update_detail_shows_changed_fields(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": 1, "b": 2})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": 1, "b": 99})}
        changes = diff(local, state)
        assert "b" in changes[0]["detail"]

    def test_update_detail_shows_added_field(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": 1, "b": 2})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": 1})}
        changes = diff(local, state)
        assert "added b" in changes[0]["detail"]
