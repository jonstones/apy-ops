"""Tests for extractor module error paths."""

from unittest.mock import MagicMock, patch

from apy_ops.extractor import extract


class TestExtractErrorHandling:
    # Tests that extract continues on read_live error and prints ERROR.
    def test_read_live_exception_continues(self, capsys):
        """When read_live raises, extract should print ERROR and continue to next module."""
        client = MagicMock()

        # Make a module that raises on read_live
        failing_mod = MagicMock()
        failing_mod.ARTIFACT_TYPE = "named_value"
        failing_mod.read_live.side_effect = Exception("connection refused")

        # Make a module that succeeds
        ok_mod = MagicMock()
        ok_mod.ARTIFACT_TYPE = "tag"
        ok_mod.read_live.return_value = {
            "tag:t1": {"type": "tag", "id": "t1", "hash": "sha256:abc", "properties": {"displayName": "t1"}}
        }

        with patch("apy_ops.extractor.DEPLOY_ORDER", [failing_mod, ok_mod]):
            result = extract(client, "/tmp/out")

        captured = capsys.readouterr()
        assert "ERROR: connection refused" in captured.out
        # Should still have extracted the tag
        assert "tag:t1" in result
        ok_mod.write_local.assert_called_once()

    # Tests that extract updates state file when backend is provided.
    def test_extract_update_state(self):
        """When backend and state are provided, extract should update state."""
        client = MagicMock()
        backend = MagicMock()
        state = {"artifacts": {}, "last_applied": None}

        mod = MagicMock()
        mod.ARTIFACT_TYPE = "named_value"
        mod.read_live.return_value = {
            "named_value:k1": {
                "type": "named_value", "id": "k1",
                "hash": "sha256:abc", "properties": {"displayName": "k1", "value": "v"},
            }
        }

        with patch("apy_ops.extractor.DEPLOY_ORDER", [mod]):
            extract(client, "/tmp/out", backend=backend, state=state)

        # State should have been updated
        assert "named_value:k1" in state["artifacts"]
        assert state["last_applied"] is not None
        backend.write.assert_called_once_with(state)

    # Tests that extract does not write state when backend is not provided.
    def test_extract_without_state_does_not_write(self):
        """When no backend/state provided, extract should not call backend.write."""
        client = MagicMock()

        mod = MagicMock()
        mod.ARTIFACT_TYPE = "named_value"
        mod.read_live.return_value = {}

        with patch("apy_ops.extractor.DEPLOY_ORDER", [mod]):
            extract(client, "/tmp/out")

    # Tests that extract respects only filter to process specific artifact types.
    def test_extract_only_filter(self):
        """Extract with only filter should skip non-matching modules."""
        client = MagicMock()

        mod_nv = MagicMock()
        mod_nv.ARTIFACT_TYPE = "named_value"
        mod_nv.read_live.return_value = {}

        mod_tag = MagicMock()
        mod_tag.ARTIFACT_TYPE = "tag"
        mod_tag.read_live.return_value = {}

        with patch("apy_ops.extractor.DEPLOY_ORDER", [mod_nv, mod_tag]):
            extract(client, "/tmp/out", only=["tag"])

        mod_nv.read_live.assert_not_called()
        mod_tag.read_live.assert_called_once()
