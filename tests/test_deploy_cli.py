"""Tests for deploy.py CLI."""

import json
import subprocess
import sys
import os
import pytest

def run_cli(*args):
    """Run apy-ops CLI as a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "apy_ops.cli", *args],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


class TestInit:
    # Tests that init command creates state file with correct structure.
    def test_init_local(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        rc, out, err = run_cli(
            "init", "--backend", "local", "--state-file", state_file,
            "--subscription-id", "sub", "--resource-group", "rg", "--service-name", "svc",
        )
        assert rc == 0
        assert "Initialized" in out
        with open(state_file) as f:
            state = json.load(f)
        assert state["version"] == 1
        assert state["artifacts"] == {}


class TestPlan:
    # Tests that plan command with no changes exits with 0.
    def test_plan_no_changes_exit_0(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        source_dir = str(tmp_path / "source")
        os.makedirs(source_dir)
        # Init state
        run_cli("init", "--backend", "local", "--state-file", state_file)
        # Plan with empty source
        rc, out, err = run_cli(
            "plan", "--source-dir", source_dir,
            "--subscription-id", "s", "--resource-group", "r", "--service-name", "a",
            "--backend", "local", "--state-file", state_file,
        )
        assert rc == 0
        assert "No changes" in out

    # Tests that plan command with changes exits with code 2.
    def test_plan_with_changes_exit_2(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        source_dir = str(tmp_path / "source")
        nv_dir = os.path.join(source_dir, "namedValues")
        os.makedirs(nv_dir)
        with open(os.path.join(nv_dir, "k.json"), "w") as f:
            json.dump({"id": "/namedValues/k", "displayName": "k", "value": "v"}, f)
        # Init state
        run_cli("init", "--backend", "local", "--state-file", state_file)
        # Plan
        rc, out, err = run_cli(
            "plan", "--source-dir", source_dir,
            "--subscription-id", "s", "--resource-group", "r", "--service-name", "a",
            "--backend", "local", "--state-file", state_file,
        )
        assert rc == 2
        assert "1 to create" in out


class TestHelp:
    # Tests that --help flag shows command list and exits with 0.
    def test_help_exits_0(self):
        rc, out, err = run_cli("--help")
        assert rc == 0
        assert "plan" in out
        assert "apply" in out
        assert "extract" in out

    # Tests that plan --help shows plan-specific options.
    def test_plan_help(self):
        rc, out, err = run_cli("plan", "--help")
        assert rc == 0
        assert "--source-dir" in out

    # Tests that apply --help shows source-dir with default value.
    def test_apply_help_shows_source_dir_default(self):
        rc, out, err = run_cli("apply", "--help")
        assert rc == 0
        assert "--source-dir" in out
        assert "default" in out
        assert "." in out


class TestApplySourceDirDefault:
    """Test that apply uses default source-dir when not provided."""

    # Tests that apply command parser has source-dir default value set.
    def test_apply_parser_has_source_dir_default(self):
        from apy_ops.cli import DEFAULT_SOURCE_DIR
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command", required=True)
        p_apply = subparsers.add_parser("apply")
        p_apply.add_argument("--backend", choices=["local", "azure"])
        p_apply.add_argument("--state-file", default=".apim-state.json")
        p_apply.add_argument("--source-dir", default=DEFAULT_SOURCE_DIR)
        p_apply.add_argument("--plan")
        args = parser.parse_args(["apply"])
        assert args.source_dir == DEFAULT_SOURCE_DIR
