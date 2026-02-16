"""Tests for applier module."""

import json
import os

import pytest
from unittest.mock import patch, MagicMock

from apy_ops.applier import apply_plan, apply_force, _apply_change, _update_state
from apy_ops.differ import CREATE, UPDATE, DELETE


class TestApplyPlanForce:
    """Test that apply_plan(force=True) delegates to apply_force and returns correct shape."""

    # Tests that apply_plan with force=True delegates to apply_force and returns correct shape.
    def test_force_true_calls_apply_force_with_args(self):
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}
        source_dir = "/tmp/source"
        only = ["api", "product"]

        with patch("apy_ops.applier.apply_force") as mock_force:
            mock_force.return_value = (5, 5, [])
            result = apply_plan(
                None, client, backend, state,
                force=True, source_dir=source_dir, only=only,
            )

        mock_force.assert_called_once_with(
            source_dir, client, backend, state, only=only,
        )
        assert result == (5, 5, None)

    # Tests that apply_plan with force=True returns error string when apply_force has errors.
    def test_force_true_returns_error_string_when_apply_force_has_errors(self):
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        with patch("apy_ops.applier.apply_force") as mock_force:
            mock_force.return_value = (2, 3, ["err1", "err2"])
            result = apply_plan(
                None, client, backend, state,
                force=True, source_dir="/tmp", only=None,
            )

        assert result[0] == 2
        assert result[1] == 3
        assert result[2] == "err1; err2"


class TestApplyPlanErrorPath:
    """Test apply_plan stops on first error and returns error info."""

    # Tests that apply_plan stops on first error and returns error info.
    def test_apply_stops_on_first_error(self):
        from apy_ops.differ import CREATE
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        plan = {
            "summary": {"create": 2, "update": 0, "delete": 0, "noop": 0},
            "changes": [
                {
                    "action": CREATE, "type": "named_value", "key": "nv:a",
                    "id": "a", "display_name": "a", "detail": "new",
                    "old": None,
                    "new": {"type": "named_value", "id": "a", "hash": "sha256:x",
                            "properties": {"displayName": "a"}},
                },
                {
                    "action": CREATE, "type": "named_value", "key": "nv:b",
                    "id": "b", "display_name": "b", "detail": "new",
                    "old": None,
                    "new": {"type": "named_value", "id": "b", "hash": "sha256:y",
                            "properties": {"displayName": "b"}},
                },
            ],
        }

        # First PUT succeeds, second fails
        client.put.side_effect = [MagicMock(), Exception("400 Bad Request")]
        success, total, error = apply_plan(plan, client, backend, state)
        assert success == 1
        assert total == 2
        assert error is not None
        assert "400 Bad Request" in error

    # Tests that apply_plan with empty changes returns zero counts.
    def test_apply_empty_changes_returns_zero(self):
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        plan = {
            "summary": {"create": 0, "update": 0, "delete": 0, "noop": 3},
            "changes": [
                {"action": "noop", "type": "named_value", "key": "nv:a",
                 "id": "a", "display_name": "a", "detail": "unchanged",
                 "old": None, "new": None},
            ],
        }

        success, total, error = apply_plan(plan, client, backend, state)
        assert success == 0
        assert total == 0
        assert error is None


class TestApplyChange:
    """Test _apply_change dispatches correctly to APIM REST API."""

    # Tests that _apply_change for CREATE calls client.put with correct path.
    def test_create_calls_put(self):
        client = MagicMock()
        change = {
            "action": CREATE, "type": "named_value", "key": "nv:a",
            "new": {"type": "named_value", "id": "a", "hash": "sha256:x",
                    "properties": {"displayName": "a", "value": "v"}},
        }
        _apply_change(change, client)
        client.put.assert_called_once()
        call_args = client.put.call_args
        assert "/namedValues/a" == call_args[0][0]

    # Tests that _apply_change for UPDATE calls client.put with correct path.
    def test_update_calls_put(self):
        client = MagicMock()
        change = {
            "action": UPDATE, "type": "backend", "key": "backend:b1",
            "new": {"type": "backend", "id": "b1", "hash": "sha256:x",
                    "properties": {"displayName": "B1", "url": "https://b1"}},
        }
        _apply_change(change, client)
        client.put.assert_called_once()
        assert "/backends/b1" == client.put.call_args[0][0]

    # Tests that _apply_change for DELETE calls client.delete with correct path.
    def test_delete_calls_delete(self):
        client = MagicMock()
        change = {
            "action": DELETE, "type": "tag", "key": "tag:t1",
            "old": {"type": "tag", "id": "t1", "hash": "sha256:x",
                    "properties": {"displayName": "T1"}},
        }
        _apply_change(change, client)
        client.delete.assert_called_once_with("/tags/t1")

    # Tests that _apply_change for API also pushes all operations.
    def test_create_api_also_pushes_operations(self):
        client = MagicMock()
        change = {
            "action": CREATE, "type": "api", "key": "api:echo",
            "new": {
                "type": "api", "id": "echo", "hash": "sha256:x",
                "properties": {"displayName": "Echo", "path": "echo"},
                "spec": None,
                "operations": {
                    "get-echo": {"method": "GET", "urlTemplate": "/echo"},
                },
            },
        }
        _apply_change(change, client)
        # Should have called put for the API + the operation
        assert client.put.call_count == 2
        paths = [call[0][0] for call in client.put.call_args_list]
        assert "/apis/echo" in paths
        assert "/apis/echo/operations/get-echo" in paths


class TestUpdateState:
    """Test _update_state correctly modifies the state dict."""

    # Tests that _update_state for CREATE adds artifact to state.
    def test_create_adds_to_state(self):
        state = {"artifacts": {}}
        change = {
            "action": CREATE, "key": "nv:a",
            "new": {"type": "named_value", "id": "a", "hash": "sha256:x",
                    "properties": {"displayName": "a"}},
        }
        _update_state(change, state)
        assert "nv:a" in state["artifacts"]
        assert state["artifacts"]["nv:a"]["hash"] == "sha256:x"

    # Tests that _update_state for UPDATE replaces artifact in state.
    def test_update_replaces_in_state(self):
        state = {"artifacts": {
            "nv:a": {"type": "named_value", "id": "a", "hash": "sha256:old",
                     "properties": {"displayName": "a"}},
        }}
        change = {
            "action": UPDATE, "key": "nv:a",
            "new": {"type": "named_value", "id": "a", "hash": "sha256:new",
                    "properties": {"displayName": "a-updated"}},
        }
        _update_state(change, state)
        assert state["artifacts"]["nv:a"]["hash"] == "sha256:new"

    # Tests that _update_state for DELETE removes artifact from state.
    def test_delete_removes_from_state(self):
        state = {"artifacts": {
            "nv:a": {"type": "named_value", "id": "a", "hash": "sha256:x",
                     "properties": {"displayName": "a"}},
        }}
        change = {"action": DELETE, "key": "nv:a", "old": state["artifacts"]["nv:a"]}
        _update_state(change, state)
        assert "nv:a" not in state["artifacts"]


class TestApplyPlanSuccess:
    """Test apply_plan happy path with state updates and backend writes."""

    # Tests that apply_plan successfully applies changes and updates state.
    def test_successful_apply_updates_state(self):
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        plan = {
            "summary": {"create": 1, "update": 0, "delete": 0, "noop": 0},
            "changes": [
                {
                    "action": CREATE, "type": "named_value", "key": "nv:a",
                    "id": "a", "display_name": "a", "detail": "new",
                    "old": None,
                    "new": {"type": "named_value", "id": "a", "hash": "sha256:x",
                            "properties": {"displayName": "a"}},
                },
            ],
        }

        success, total, error = apply_plan(plan, client, backend, state)
        assert success == 1
        assert total == 1
        assert error is None
        assert "nv:a" in state["artifacts"]
        # backend.write should be called: once per change + once for last_applied
        assert backend.write.call_count == 2

    # Tests that apply_plan successfully deletes artifact and removes from state.
    def test_delete_removes_from_state(self):
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {
            "nv:a": {"type": "named_value", "id": "a", "hash": "sha256:x",
                     "properties": {"displayName": "a"}},
        }}

        plan = {
            "summary": {"create": 0, "update": 0, "delete": 1, "noop": 0},
            "changes": [
                {
                    "action": DELETE, "type": "named_value", "key": "nv:a",
                    "id": "a", "display_name": "a", "detail": "removed",
                    "old": state["artifacts"]["nv:a"],
                    "new": None,
                },
            ],
        }

        success, total, error = apply_plan(plan, client, backend, state)
        assert success == 1
        assert error is None
        assert "nv:a" not in state["artifacts"]
        client.delete.assert_called_once()


class TestApplyForce:
    """Test apply_force pushes all local artifacts."""

    # Tests that apply_force reads and pushes all local artifacts.
    def test_force_reads_and_pushes_all(self, tmp_path):
        nv_dir = tmp_path / "namedValues"
        nv_dir.mkdir()
        (nv_dir / "k1.json").write_text(json.dumps({
            "id": "/namedValues/k1", "displayName": "k1", "value": "v",
        }))

        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        success, total, errors = apply_force(str(tmp_path), client, backend, state)
        assert total >= 1
        assert success >= 1
        assert errors == []
        assert "named_value:k1" in state["artifacts"]
        client.put.assert_called()

    # Tests that apply_force continues processing on error and returns error list.
    def test_force_continues_on_error(self, tmp_path):
        nv_dir = tmp_path / "namedValues"
        nv_dir.mkdir()
        (nv_dir / "k1.json").write_text(json.dumps({
            "id": "/namedValues/k1", "displayName": "k1", "value": "v",
        }))
        (nv_dir / "k2.json").write_text(json.dumps({
            "id": "/namedValues/k2", "displayName": "k2", "value": "v",
        }))

        client = MagicMock()
        client.put.side_effect = [Exception("fail"), MagicMock()]
        backend = MagicMock()
        state = {"artifacts": {}}

        success, total, errors = apply_force(str(tmp_path), client, backend, state)
        assert success == 1
        assert total == 2
        assert len(errors) == 1

    # Tests that apply_force respects only filter to process specific artifact types.
    def test_force_only_filter(self, tmp_path):
        nv_dir = tmp_path / "namedValues"
        nv_dir.mkdir()
        (nv_dir / "k1.json").write_text(json.dumps({
            "id": "/namedValues/k1", "displayName": "k1", "value": "v",
        }))
        tag_dir = tmp_path / "tags"
        tag_dir.mkdir()
        (tag_dir / "t1.json").write_text(json.dumps({
            "id": "/tags/t1", "displayName": "t1",
        }))

        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}}

        success, total, errors = apply_force(
            str(tmp_path), client, backend, state, only=["tag"],
        )
        assert total == 1
        assert "tag:t1" in state["artifacts"]
        assert "named_value:k1" not in state["artifacts"]
