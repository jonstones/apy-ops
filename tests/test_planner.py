"""Tests for planner module."""

import json
import os
from apy_ops.planner import generate_plan, order_changes, print_plan, save_plan, load_plan
from apy_ops.differ import CREATE, UPDATE, DELETE, NOOP


def _make_source(tmp_path, artifacts):
    """Create a minimal APIOps source directory with named values."""
    nv_dir = tmp_path / "namedValues"
    nv_dir.mkdir()
    for name, props in artifacts.items():
        (nv_dir / f"{name}.json").write_text(json.dumps(props))
    return str(tmp_path)


class TestGeneratePlan:
    # Tests that generate_plan marks all artifacts as CREATE when state is empty.
    def test_empty_state_all_creates(self, tmp_path):
        source = _make_source(tmp_path, {
            "key1": {"id": "/namedValues/key1", "displayName": "key1", "value": "v1"},
        })
        state = {"artifacts": {}}
        plan = generate_plan(source, state)
        assert plan["summary"]["create"] == 1
        assert plan["summary"]["update"] == 0
        assert plan["summary"]["delete"] == 0

    # Tests that generate_plan marks all artifacts as NOOP when state matches local.
    def test_matching_state_all_noops(self, tmp_path):
        props = {"id": "/namedValues/key1", "displayName": "key1", "value": "v1"}
        source = _make_source(tmp_path, {"key1": props})

        # Read local to get the hash
        from apy_ops.artifacts.named_values import read_local
        local = read_local(str(tmp_path))
        key, art = next(iter(local.items()))

        state = {"artifacts": {key: art}}
        plan = generate_plan(str(tmp_path), state)
        assert plan["summary"]["noop"] == 1
        assert plan["summary"]["create"] == 0

    # Tests that generate_plan respects only filter to plan specific artifact types.
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

    # Tests that generate_plan summary counts match total changes.
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
    # Tests that order_changes places all creates before all deletes.
    def test_creates_before_deletes(self):
        changes = [
            {"action": DELETE, "type": "named_value", "key": "nv:old"},
            {"action": CREATE, "type": "api", "key": "api:new"},
        ]
        ordered = order_changes(changes)
        assert ordered[0]["action"] == CREATE
        assert ordered[1]["action"] == DELETE

    # Tests that order_changes sorts creates in deployment order.
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

    # Tests that order_changes sorts deletes in reverse deployment order.
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


class TestPrintPlan:
    # Tests that print_plan displays "No changes" when only noops exist.
    def test_print_plan_no_changes(self, capsys):
        plan = {
            "summary": {"create": 0, "update": 0, "delete": 0, "noop": 5},
            "changes": [
                {"action": NOOP, "type": "named_value", "display_name": "k1", "detail": "unchanged"},
            ],
        }
        print_plan(plan)
        captured = capsys.readouterr()
        assert "No changes" in captured.out
        assert "0 to create" in captured.out

    # Tests that print_plan displays summary counts and changes.
    def test_print_plan_with_changes(self, capsys):
        plan = {
            "summary": {"create": 1, "update": 1, "delete": 0, "noop": 0},
            "changes": [
                {"action": CREATE, "type": "named_value", "display_name": "k1", "detail": "new"},
                {"action": UPDATE, "type": "backend", "display_name": "b1", "detail": "changed url"},
            ],
        }
        print_plan(plan)
        captured = capsys.readouterr()
        assert "1 to create" in captured.out
        assert "1 to update" in captured.out
        assert '"k1"' in captured.out
        assert '"b1"' in captured.out

    # Tests that print_plan in verbose mode displays noop artifacts.
    def test_print_plan_verbose_shows_noop(self, capsys):
        plan = {
            "summary": {"create": 1, "update": 0, "delete": 0, "noop": 1},
            "changes": [
                {"action": CREATE, "type": "tag", "display_name": "t1", "detail": "new"},
                {"action": NOOP, "type": "tag", "display_name": "t2", "detail": "unchanged"},
            ],
        }
        print_plan(plan, verbose=True)
        captured = capsys.readouterr()
        assert '"t2"' in captured.out  # noop shown in verbose mode

    # Tests that print_plan hides noop artifacts by default.
    def test_print_plan_hides_noop_by_default(self, capsys):
        plan = {
            "summary": {"create": 1, "update": 0, "delete": 0, "noop": 1},
            "changes": [
                {"action": CREATE, "type": "tag", "display_name": "t1", "detail": "new"},
                {"action": NOOP, "type": "tag", "display_name": "t2", "detail": "unchanged"},
            ],
        }
        print_plan(plan, verbose=False)
        captured = capsys.readouterr()
        assert '"t1"' in captured.out
        assert '"t2"' not in captured.out


class TestSaveLoadPlan:
    # Tests that save_plan and load_plan roundtrip plan data correctly.
    def test_save_and_load_roundtrip(self, tmp_path):
        plan = {
            "generated_at": "2025-01-01T00:00:00",
            "source_dir": "/tmp/src",
            "summary": {"create": 1, "update": 0, "delete": 0, "noop": 0},
            "changes": [
                {"action": CREATE, "type": "named_value", "key": "nv:a",
                 "id": "a", "display_name": "a", "detail": "new",
                 "old": None, "new": {"type": "named_value", "id": "a"}},
            ],
        }
        path = str(tmp_path / "plan.json")
        save_plan(plan, path)
        assert os.path.isfile(path)
        loaded = load_plan(path)
        assert loaded["summary"]["create"] == 1
        assert loaded["changes"][0]["key"] == "nv:a"
