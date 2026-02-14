"""Tests for planner module."""

import json
import os
from planner import generate_plan, order_changes
from differ import CREATE, UPDATE, DELETE, NOOP


def _make_source(tmp_path, artifacts):
    """Create a minimal APIOps source directory with named values."""
    nv_dir = tmp_path / "namedValues"
    nv_dir.mkdir()
    for name, props in artifacts.items():
        (nv_dir / f"{name}.json").write_text(json.dumps(props))
    return str(tmp_path)


class TestGeneratePlan:
    def test_empty_state_all_creates(self, tmp_path):
        source = _make_source(tmp_path, {
            "key1": {"id": "/namedValues/key1", "displayName": "key1", "value": "v1"},
        })
        state = {"artifacts": {}}
        plan = generate_plan(source, state)
        assert plan["summary"]["create"] == 1
        assert plan["summary"]["update"] == 0
        assert plan["summary"]["delete"] == 0

    def test_matching_state_all_noops(self, tmp_path):
        props = {"id": "/namedValues/key1", "displayName": "key1", "value": "v1"}
        source = _make_source(tmp_path, {"key1": props})

        # Read local to get the hash
        from artifacts.named_values import read_local
        local = read_local(str(tmp_path))
        key, art = next(iter(local.items()))

        state = {"artifacts": {key: art}}
        plan = generate_plan(str(tmp_path), state)
        assert plan["summary"]["noop"] == 1
        assert plan["summary"]["create"] == 0

    def test_only_filter(self, tmp_path):
        # Create both named values and tags
        nv_dir = tmp_path / "namedValues"
        nv_dir.mkdir()
        (nv_dir / "k.json").write_text(json.dumps({"id": "/namedValues/k", "displayName": "k"}))
        tag_dir = tmp_path / "tags"
        tag_dir.mkdir()
        (tag_dir / "t.json").write_text(json.dumps({"id": "/tags/t", "displayName": "t"}))

        state = {"artifacts": {}}
        plan = generate_plan(str(tmp_path), state, only=["named_value"])
        # Should only include named_value, not tag
        types = {c["type"] for c in plan["changes"]}
        assert "named_value" in types
        assert "tag" not in types

    def test_plan_summary_counts(self, tmp_path):
        source = _make_source(tmp_path, {
            "a": {"id": "/namedValues/a", "displayName": "a", "value": "1"},
            "b": {"id": "/namedValues/b", "displayName": "b", "value": "2"},
        })
        state = {"artifacts": {}}
        plan = generate_plan(source, state)
        total = sum(plan["summary"].values())
        assert total == len(plan["changes"])


class TestOrderChanges:
    def test_creates_before_deletes(self):
        changes = [
            {"action": DELETE, "type": "named_value", "key": "nv:old"},
            {"action": CREATE, "type": "api", "key": "api:new"},
        ]
        ordered = order_changes(changes)
        assert ordered[0]["action"] == CREATE
        assert ordered[1]["action"] == DELETE

    def test_creates_in_deploy_order(self):
        changes = [
            {"action": CREATE, "type": "api", "key": "api:x"},
            {"action": CREATE, "type": "named_value", "key": "nv:x"},
            {"action": CREATE, "type": "tag", "key": "tag:x"},
        ]
        ordered = order_changes(changes)
        types = [c["type"] for c in ordered]
        assert types.index("named_value") < types.index("tag")
        assert types.index("tag") < types.index("api")

    def test_deletes_in_reverse_deploy_order(self):
        changes = [
            {"action": DELETE, "type": "named_value", "key": "nv:x"},
            {"action": DELETE, "type": "api", "key": "api:x"},
            {"action": DELETE, "type": "tag", "key": "tag:x"},
        ]
        ordered = order_changes(changes)
        types = [c["type"] for c in ordered]
        # Reverse order: api before tag before named_value
        assert types.index("api") < types.index("tag")
        assert types.index("tag") < types.index("named_value")
