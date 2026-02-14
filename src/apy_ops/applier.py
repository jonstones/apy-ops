"""Execute plan against APIM REST API, update state after each success."""

import sys
from datetime import datetime, timezone

from apy_ops.artifacts import ARTIFACT_TYPES
from apy_ops.artifacts.apis import to_operation_payloads
from apy_ops.differ import CREATE, UPDATE, DELETE
from apy_ops.planner import order_changes

# Console symbols
CHECK = "\u2713"
CROSS = "\u2717"


def apply_plan(plan, client, backend, state, force=False, source_dir=None, only=None):
    """Execute all changes in the plan.

    Args:
        plan: Plan dict from planner.generate_plan() (ignored when force=True)
        client: ApimClient instance
        backend: State backend instance
        state: Current state dict
        force: If True, push all artifacts regardless of diff (uses source_dir, only)
        source_dir: Path to APIOps directory (required when force=True)
        only: Optional list of artifact type names to include (when force=True)

    Returns:
        (success_count, total_count, error_message or None)
    """
    if force:
        success, total, errors = apply_force(source_dir, client, backend, state, only=only)
        return (success, total, "; ".join(errors) if errors else None)

    changes = [c for c in plan["changes"] if c["action"] in (CREATE, UPDATE, DELETE)]
    if not changes:
        print("\nNo changes to apply.\n")
        return 0, 0, None

    ordered = order_changes(changes)
    total = len(ordered)
    success = 0

    print(f"\nApplying changes...\n")

    for i, change in enumerate(ordered, 1):
        action = change["action"]
        type_name = change["type"].replace("_", " ")
        name = change["display_name"]
        prefix = f"  [{i}/{total}]"
        symbol = "+" if action == CREATE else "~" if action == UPDATE else "-"

        print(f"{prefix} {symbol} {type_name} \"{name}\"", end="", flush=True)

        try:
            _apply_change(change, client)
            _update_state(change, state)
            backend.write(state)
            print(f"  {CHECK}")
            success += 1
        except Exception as e:
            error_msg = str(e)
            print(f"  {CROSS} ERROR: {error_msg}")
            print(f"\nApply failed. {success} of {total} changes applied successfully.")
            print("State file updated. Re-run 'plan' to see remaining changes.\n")
            return success, total, error_msg

    state["last_applied"] = datetime.now(timezone.utc).isoformat()
    backend.write(state)
    print(f"\nApply complete! {success} changes applied successfully.\n")
    return success, total, None


def _apply_change(change, client):
    """Execute a single change against the APIM REST API."""
    action = change["action"]
    artifact_type = change["type"]
    mod = ARTIFACT_TYPES[artifact_type]

    if action in (CREATE, UPDATE):
        artifact = change["new"]
        path = mod.resource_path(artifact["id"])
        payload = mod.to_rest_payload(artifact)
        client.put(path, payload)

        # For APIs, also push operations
        if artifact_type == "api" and hasattr(mod, "to_operation_payloads"):
            for op_id, op_payload in to_operation_payloads(artifact):
                client.put(f"/apis/{artifact['id']}/operations/{op_id}", op_payload)

    elif action == DELETE:
        artifact = change["old"]
        path = mod.resource_path(artifact["id"])
        client.delete(path)


def _update_state(change, state):
    """Update the state dict after a successful change."""
    key = change["key"]
    action = change["action"]

    if action in (CREATE, UPDATE):
        artifact = change["new"]
        state["artifacts"][key] = {
            "type": artifact["type"],
            "id": artifact["id"],
            "hash": artifact["hash"],
            "properties": artifact["properties"],
        }
    elif action == DELETE:
        state["artifacts"].pop(key, None)


def apply_force(source_dir, client, backend, state, only=None):
    """Force mode: push ALL local artifacts to APIM, rebuild state from scratch.

    Ignores state diff entirely. Used when state is stale due to manual APIM changes.
    """
    from apy_ops.artifacts import DEPLOY_ORDER

    state["artifacts"] = {}
    total = 0
    success = 0
    errors = []

    print("\nForce apply: pushing ALL artifacts...\n")

    for mod in DEPLOY_ORDER:
        if only and mod.ARTIFACT_TYPE not in only:
            continue
        artifacts = mod.read_local(source_dir)
        for key, artifact in artifacts.items():
            total += 1
            type_name = artifact["type"].replace("_", " ")
            name = artifact["properties"].get("displayName") or artifact["id"]
            print(f"  + {type_name} \"{name}\"", end="", flush=True)

            try:
                path = mod.resource_path(artifact["id"])
                payload = mod.to_rest_payload(artifact)
                client.put(path, payload)

                # For APIs, also push operations
                if mod.ARTIFACT_TYPE == "api":
                    for op_id, op_payload in to_operation_payloads(artifact):
                        client.put(f"/apis/{artifact['id']}/operations/{op_id}", op_payload)

                state["artifacts"][key] = {
                    "type": artifact["type"],
                    "id": artifact["id"],
                    "hash": artifact["hash"],
                    "properties": artifact["properties"],
                }
                backend.write(state)
                print(f"  {CHECK}")
                success += 1
            except Exception as e:
                print(f"  {CROSS} ERROR: {e}")
                errors.append(f"{type_name} \"{name}\": {e}")

    state["last_applied"] = datetime.now(timezone.utc).isoformat()
    backend.write(state)

    if errors:
        print(f"\nForce apply completed with errors. {success}/{total} succeeded.")
        for err in errors:
            print(f"  - {err}")
    else:
        print(f"\nForce apply complete! {success} artifacts pushed.\n")

    return success, total, errors
