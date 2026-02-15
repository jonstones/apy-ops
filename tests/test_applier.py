"""Tests for applier module."""

import pytest
from unittest.mock import patch, MagicMock

from apy_ops.applier import apply_plan, apply_force


class TestApplyPlanForce:
    """Test that apply_plan(force=True) delegates to apply_force and returns correct shape."""

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
