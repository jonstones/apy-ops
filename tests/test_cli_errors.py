"""Tests for CLI error paths and command functions."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


def run_cli(*args):
    """Run apy-ops CLI as a subprocess and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "apy_ops.cli", *args],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


class TestPlanErrors:
    def test_plan_missing_state_exits_1(self, tmp_path):
        state_file = str(tmp_path / "nonexistent.json")
        rc, out, err = run_cli(
            "plan", "--backend", "local", "--state-file", state_file,
            "--source-dir", str(tmp_path),
        )
        assert rc == 1
        assert "State file not found" in err

    def test_plan_with_changes_exits_2(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        source_dir = str(tmp_path / "source")
        nv_dir = os.path.join(source_dir, "namedValues")
        os.makedirs(nv_dir)
        with open(os.path.join(nv_dir, "k.json"), "w") as f:
            json.dump({"id": "/namedValues/k", "displayName": "k", "value": "v"}, f)
        run_cli("init", "--backend", "local", "--state-file", state_file)
        rc, out, err = run_cli(
            "plan", "--source-dir", source_dir,
            "--backend", "local", "--state-file", state_file,
        )
        assert rc == 2


class TestApplyErrors:
    def test_apply_missing_state_exits_1(self, tmp_path):
        state_file = str(tmp_path / "nonexistent.json")
        rc, out, err = run_cli(
            "apply", "--backend", "local", "--state-file", state_file,
            "--source-dir", str(tmp_path), "--auto-approve",
        )
        assert rc == 1
        assert "State file not found" in err

    def test_apply_missing_plan_file_errors(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        run_cli("init", "--backend", "local", "--state-file", state_file)
        rc, out, err = run_cli(
            "apply", "--backend", "local", "--state-file", state_file,
            "--plan", str(tmp_path / "nonexistent_plan.json"),
            "--auto-approve",
        )
        assert rc != 0


class TestRequireApimArgs:
    def test_require_apim_args_exits_with_message(self, tmp_path, monkeypatch):
        """When APIM args are missing, apply should exit 1 with helpful message."""
        monkeypatch.delenv("APIM_SUBSCRIPTION_ID", raising=False)
        monkeypatch.delenv("APIM_RESOURCE_GROUP", raising=False)
        monkeypatch.delenv("APIM_SERVICE_NAME", raising=False)

        state_file = str(tmp_path / "state.json")
        source_dir = str(tmp_path / "source")
        nv_dir = os.path.join(source_dir, "namedValues")
        os.makedirs(nv_dir)
        with open(os.path.join(nv_dir, "k.json"), "w") as f:
            json.dump({"id": "/namedValues/k", "displayName": "k", "value": "v"}, f)

        # Init state without APIM details
        run_cli("init", "--backend", "local", "--state-file", state_file)

        # Apply should fail because APIM args are missing
        rc, out, err = run_cli(
            "apply", "--source-dir", source_dir,
            "--backend", "local", "--state-file", state_file,
            "--auto-approve",
        )
        assert rc == 1
        assert "--subscription-id" in err
        assert "--resource-group" in err
        assert "--service-name" in err


class TestResolveApimArgs:
    def test_resolve_from_env(self, monkeypatch):
        from apy_ops.cli import _resolve_apim_args
        monkeypatch.setenv("APIM_SUBSCRIPTION_ID", "env-sub")
        monkeypatch.setenv("APIM_RESOURCE_GROUP", "env-rg")
        monkeypatch.setenv("APIM_SERVICE_NAME", "env-svc")
        args = SimpleNamespace(subscription_id=None, resource_group=None, service_name=None)
        _resolve_apim_args(args)
        assert args.subscription_id == "env-sub"
        assert args.resource_group == "env-rg"
        assert args.service_name == "env-svc"

    def test_resolve_flag_overrides_env(self, monkeypatch):
        from apy_ops.cli import _resolve_apim_args
        monkeypatch.setenv("APIM_SUBSCRIPTION_ID", "env-sub")
        args = SimpleNamespace(subscription_id="flag-sub", resource_group=None, service_name=None)
        _resolve_apim_args(args)
        assert args.subscription_id == "flag-sub"

    def test_resolve_from_state(self, monkeypatch):
        from apy_ops.cli import _resolve_apim_args
        monkeypatch.delenv("APIM_SUBSCRIPTION_ID", raising=False)
        monkeypatch.delenv("APIM_RESOURCE_GROUP", raising=False)
        monkeypatch.delenv("APIM_SERVICE_NAME", raising=False)
        state = {"subscription_id": "st-sub", "resource_group": "st-rg", "apim_service": "st-svc"}
        args = SimpleNamespace(subscription_id=None, resource_group=None, service_name=None)
        _resolve_apim_args(args, state)
        assert args.subscription_id == "st-sub"
        assert args.resource_group == "st-rg"
        assert args.service_name == "st-svc"

    def test_resolve_priority_flag_env_state(self, monkeypatch):
        from apy_ops.cli import _resolve_apim_args
        monkeypatch.setenv("APIM_SUBSCRIPTION_ID", "env-sub")
        state = {"subscription_id": "st-sub", "resource_group": "st-rg", "apim_service": "st-svc"}
        args = SimpleNamespace(subscription_id="flag-sub", resource_group=None, service_name=None)
        _resolve_apim_args(args, state)
        assert args.subscription_id == "flag-sub"  # flag wins
        assert args.resource_group == "st-rg"  # falls through to state
        assert args.service_name == "st-svc"


class TestCmdInit:
    def test_cmd_init_creates_state(self, tmp_path):
        from apy_ops.cli import cmd_init
        state_file = str(tmp_path / "state.json")
        args = SimpleNamespace(
            backend="local", state_file=state_file,
            subscription_id="sub-1", resource_group="rg-1", service_name="apim-1",
            backend_storage_account=None, backend_container=None, backend_blob=None,
            client_id=None, client_secret=None, tenant_id=None,
        )
        cmd_init(args)
        assert os.path.isfile(state_file)
        with open(state_file) as f:
            data = json.load(f)
        assert data["subscription_id"] == "sub-1"

    def test_cmd_init_default_empty_strings(self, tmp_path):
        from apy_ops.cli import cmd_init
        state_file = str(tmp_path / "state.json")
        args = SimpleNamespace(
            backend="local", state_file=state_file,
            subscription_id=None, resource_group=None, service_name=None,
            backend_storage_account=None, backend_container=None, backend_blob=None,
            client_id=None, client_secret=None, tenant_id=None,
        )
        cmd_init(args)
        with open(state_file) as f:
            data = json.load(f)
        assert data["subscription_id"] == ""


class TestCmdForceUnlock:
    def test_force_unlock_removes_lock(self, tmp_path):
        from apy_ops.cli import cmd_force_unlock
        state_file = str(tmp_path / "state.json")
        # Create state and lock
        with open(state_file, "w") as f:
            json.dump({"version": 1, "artifacts": {}}, f)
        with open(state_file + ".lock", "w") as f:
            f.write("1234")
        args = SimpleNamespace(
            backend="local", state_file=state_file,
            backend_storage_account=None, backend_container=None, backend_blob=None,
            client_id=None, client_secret=None, tenant_id=None,
        )
        cmd_force_unlock(args)
        assert not os.path.isfile(state_file + ".lock")


class TestCmdPlan:
    def test_cmd_plan_no_changes_exits_0(self, tmp_path):
        """Plan with no changes exits 0."""
        state_file = str(tmp_path / "state.json")
        run_cli("init", "--backend", "local", "--state-file", state_file)
        rc, out, err = run_cli(
            "plan", "--backend", "local", "--state-file", state_file,
            "--source-dir", str(tmp_path),
        )
        assert rc == 0

    def test_cmd_plan_saves_to_file(self, tmp_path):
        state_file = str(tmp_path / "state.json")
        plan_file = str(tmp_path / "plan.json")
        nv_dir = tmp_path / "source" / "namedValues"
        nv_dir.mkdir(parents=True)
        (nv_dir / "k.json").write_text(json.dumps({
            "id": "/namedValues/k", "displayName": "k", "value": "v",
        }))
        run_cli("init", "--backend", "local", "--state-file", state_file)
        rc, out, err = run_cli(
            "plan", "--backend", "local", "--state-file", state_file,
            "--source-dir", str(tmp_path / "source"), "--out", plan_file,
        )
        assert rc == 2  # changes exist
        assert os.path.isfile(plan_file)
        with open(plan_file) as f:
            plan = json.load(f)
        assert plan["summary"]["create"] >= 1


class TestRequireApimArgs:
    def test_require_exits_when_missing(self):
        from apy_ops.cli import _require_apim_args
        args = SimpleNamespace(subscription_id=None, resource_group=None, service_name=None)
        with pytest.raises(SystemExit):
            _require_apim_args(args)

    def test_require_passes_when_present(self):
        from apy_ops.cli import _require_apim_args
        args = SimpleNamespace(subscription_id="s", resource_group="r", service_name="n")
        _require_apim_args(args)  # should not raise
