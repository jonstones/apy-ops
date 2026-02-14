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
    def test_help_exits_0(self):
        rc, out, err = run_cli("--help")
        assert rc == 0
        assert "plan" in out
        assert "apply" in out
        assert "extract" in out

    def test_plan_help(self):
        rc, out, err = run_cli("plan", "--help")
        assert rc == 0
        assert "--source-dir" in out
