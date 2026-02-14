"""Plan generation: read local artifacts, load state, diff, produce ordered plan."""

import json
from datetime import datetime, timezone

from apy_ops.artifacts import DEPLOY_ORDER, ARTIFACT_TYPES
from apy_ops.differ import diff, CREATE, UPDATE, DELETE, NOOP

# Symbols for plan output
SYMBOLS = {CREATE: "+", UPDATE: "~", DELETE: "-", NOOP: "."}
COLORS = {CREATE: "\033[32m", UPDATE: "\033[33m", DELETE: "\033[31m", NOOP: "\033[90m"}
RESET = "\033[0m"


def generate_plan(source_dir, state, only=None):
    """Generate a plan by diffing local artifacts against state.

    Args:
        source_dir: Path to APIOps directory
        state: State dict (from backend.read())
        only: Optional list of artifact type names to include

    Returns:
        Plan dict with changes list and summary
    """
    state_artifacts = state.get("artifacts", {}) if state else {}

    # Read all local artifacts in deployment order
    local_artifacts = {}
    modules_used = []
    for mod in DEPLOY_ORDER:
        if only and mod.ARTIFACT_TYPE not in only:
            continue
        modules_used.append(mod)
        artifacts = mod.read_local(source_dir)
        local_artifacts.update(artifacts)

    # Filter state artifacts to only included types
    if only:
        state_artifacts = {
            k: v for k, v in state_artifacts.items()
            if v.get("type") in only
        }

    # Diff
    changes = diff(local_artifacts, state_artifacts)

    # Separate by action
    creates = [c for c in changes if c["action"] == CREATE]
    updates = [c for c in changes if c["action"] == UPDATE]
    deletes = [c for c in changes if c["action"] == DELETE]
    noops = [c for c in changes if c["action"] == NOOP]

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": source_dir,
        "summary": {
            "create": len(creates),
            "update": len(updates),
            "delete": len(deletes),
            "noop": len(noops),
        },
        "changes": changes,
    }
    return plan


def order_changes(changes):
    """Order changes for execution: creates/updates in deploy order, deletes in reverse."""
    # Build type order index
    type_order = {mod.ARTIFACT_TYPE: i for i, mod in enumerate(DEPLOY_ORDER)}

    creates_updates = [c for c in changes if c["action"] in (CREATE, UPDATE)]
    deletes = [c for c in changes if c["action"] == DELETE]

    # Sort creates/updates by deployment order
    creates_updates.sort(key=lambda c: type_order.get(c["type"], 999))
    # Sort deletes in reverse deployment order
    deletes.sort(key=lambda c: type_order.get(c["type"], 999), reverse=True)

    return creates_updates + deletes


def print_plan(plan, verbose=False):
    """Print plan to console in Terraform-style format."""
    summary = plan["summary"]
    changes = plan["changes"]

    print(f"\nPlan: {summary['create']} to create, {summary['update']} to update, "
          f"{summary['delete']} to delete, {summary['noop']} unchanged.\n")

    if summary["create"] == 0 and summary["update"] == 0 and summary["delete"] == 0:
        print("No changes. Infrastructure is up-to-date.\n")
        return

    # Group and print changes
    for change in changes:
        action = change["action"]
        if action == NOOP and not verbose:
            continue
        symbol = SYMBOLS[action]
        color = COLORS[action]
        type_name = change["type"].replace("_", " ")
        name = change["display_name"]
        detail = change["detail"]
        print(f"  {color}{symbol} {type_name:<20} \"{name}\"  ({detail}){RESET}")

    print()


def save_plan(plan, path):
    """Save plan to a JSON file."""
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)
        f.write("\n")
    print(f"Plan saved to {path}")


def load_plan(path):
    """Load a plan from a JSON file."""
    with open(path, "r") as f:
        return json.load(f)
