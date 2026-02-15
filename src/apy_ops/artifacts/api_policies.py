"""API-level policy artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api_policy"
SOURCE_SUBDIR = "apis"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        api_dir = os.path.join(base, entry)
        if not os.path.isdir(api_dir):
            continue
        # Read API info to get API ID
        info_path = os.path.join(api_dir, "apiInformation.json")
        if not os.path.isfile(info_path):
            info_path = os.path.join(api_dir, "configuration.json")
        if not os.path.isfile(info_path):
            continue
        api_info = read_json(info_path)
        api_id = extract_id_from_path(api_info.get("id", entry))

        # Look for policy.xml in the API directory
        policy_path = os.path.join(api_dir, "policy.xml")
        if not os.path.isfile(policy_path):
            continue
        with open(policy_path, "r") as f:
            content = f.read()
        props = {"format": "rawxml", "value": content}
        key = f"{ARTIFACT_TYPE}:{api_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": api_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    from apy_ops.artifacts.apis import read_live as read_apis_live
    # We need to list APIs first, then check each for a policy
    artifacts = {}
    try:
        apis = client.list("/apis")
    except Exception:
        return artifacts
    for api in apis:
        api_id = api["name"]
        try:
            data = client.get(f"/apis/{api_id}/policies/policy")
            props = data.get("properties", {})
            key = f"{ARTIFACT_TYPE}:{api_id}"
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": api_id,
                "hash": compute_hash(props),
                "properties": props,
            }
        except Exception:
            pass  # No policy for this API
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    for artifact in artifacts.values():
        api_id = artifact["id"]
        # Find the API directory (may have display name prefix)
        api_dir = _find_api_dir(base, api_id)
        if not api_dir:
            api_dir = os.path.join(base, api_id)
            os.makedirs(api_dir, exist_ok=True)
        content = artifact["properties"].get("value", "")
        path = os.path.join(api_dir, "policy.xml")
        with open(path, "w") as f:
            f.write(content)


def _find_api_dir(base: str, api_id: str) -> str | None:
    """Find the API directory that matches the given API ID."""
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        if entry == api_id or entry.endswith(f"_{api_id}"):
            path = os.path.join(base, entry)
            if os.path.isdir(path):
                return path
    return None


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {"properties": artifact["properties"]}


def resource_path(artifact_id: str) -> str:
    return f"/apis/{artifact_id}/policies/policy"
