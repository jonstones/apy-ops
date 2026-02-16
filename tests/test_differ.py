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
    # Tests that diff returns empty list when both local and state are empty.
    def test_empty_both(self):
        assert diff({}, {}) == []

    # Tests that diff marks artifact in local but not state as CREATE.
    def test_new_artifact_is_create(self):
        local = {"api:echo": _artifact("api", "echo", "h1")}
        changes = diff(local, {})
        assert len(changes) == 1
        assert changes[0]["action"] == CREATE
        assert changes[0]["key"] == "api:echo"

    # Tests that diff marks artifact in state but not local as DELETE.
    def test_removed_artifact_is_delete(self):
        state = {"api:echo": _artifact("api", "echo", "h1")}
        changes = diff({}, state)
        assert len(changes) == 1
        assert changes[0]["action"] == DELETE

    # Tests that diff marks artifact with same hash as NOOP.
    def test_same_hash_is_noop(self):
        art = _artifact("api", "echo", "h1")
        changes = diff({"api:echo": art}, {"api:echo": art})
        assert len(changes) == 1
        assert changes[0]["action"] == NOOP

    # Tests that diff marks artifact with different hash as UPDATE.
    def test_different_hash_is_update(self):
        local = {"api:echo": _artifact("api", "echo", "h2", {"displayName": "echo", "path": "/new"})}
        state = {"api:echo": _artifact("api", "echo", "h1", {"displayName": "echo", "path": "/old"})}
        changes = diff(local, state)
        assert len(changes) == 1
        assert changes[0]["action"] == UPDATE
        assert "path" in changes[0]["detail"]

    # Tests that diff correctly categorizes mixed scenario of creates, updates, deletes, and noops.
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

    # Tests that update detail message includes changed fields.
    def test_update_detail_shows_changed_fields(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": 1, "b": 2})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": 1, "b": 99})}
        changes = diff(local, state)
        assert "b" in changes[0]["detail"]

    # Tests that update detail message includes newly added fields.
    def test_update_detail_shows_added_field(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": 1, "b": 2})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": 1})}
        changes = diff(local, state)
        assert "added b" in changes[0]["detail"]

    # Tests that update detail message includes removed fields.
    def test_update_detail_shows_removed_field(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": 1})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": 1, "b": 2})}
        changes = diff(local, state)
        assert "removed b" in changes[0]["detail"]

    # Tests that update detail message includes changed complex values like lists.
    def test_update_detail_shows_changed_complex_value(self):
        local = {"t:x": _artifact("t", "x", "h2", {"a": [1, 2, 3]})}
        state = {"t:x": _artifact("t", "x", "h1", {"a": [1]})}
        changes = diff(local, state)
        assert "changed a" in changes[0]["detail"]
