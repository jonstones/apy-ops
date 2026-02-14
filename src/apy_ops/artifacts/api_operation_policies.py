"""API Operation-level policy artifact module."""

import json
import os
from apy_ops.artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api_operation_policy"
SOURCE_SUBDIR = "apis"


def read_local(source_dir):
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        api_dir = os.path.join(base, entry)
        if not os.path.isdir(api_dir):
            continue
        info_path = os.path.join(api_dir, "apiInformation.json")
        if not os.path.isfile(info_path):
            info_path = os.path.join(api_dir, "configuration.json")
        if not os.path.isfile(info_path):
            continue
        api_info = read_json(info_path)
        api_id = extract_id_from_path(api_info.get("id", entry))

        # Look for operation policy files in operations/ or directly in api dir
        # Pattern: <operationId>/policy.xml or operationId.policy.xml
        ops_dir = api_dir
        for op_entry in sorted(os.listdir(ops_dir)):
            op_dir = os.path.join(ops_dir, op_entry)
            if os.path.isdir(op_dir):
                policy_path = os.path.join(op_dir, "policy.xml")
                if os.path.isfile(policy_path):
                    op_id = op_entry
                    with open(policy_path, "r") as f:
                        content = f.read()
                    props = {"format": "rawxml", "value": content}
                    key = f"{ARTIFACT_TYPE}:{api_id}/{op_id}"
                    artifacts[key] = {
                        "type": ARTIFACT_TYPE,
                        "id": f"{api_id}/{op_id}",
                        "hash": compute_hash(props),
                        "properties": props,
                    }
    return artifacts


def read_live(client):
    artifacts = {}
    try:
        apis = client.list("/apis")
    except Exception:
        return artifacts
    for api in apis:
        api_id = api["name"]
        try:
            ops = client.list(f"/apis/{api_id}/operations")
        except Exception:
            continue
        for op in ops:
            op_id = op["name"]
            try:
                data = client.get(f"/apis/{api_id}/operations/{op_id}/policies/policy")
                props = data.get("properties", {})
                key = f"{ARTIFACT_TYPE}:{api_id}/{op_id}"
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{api_id}/{op_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
            except Exception:
                pass
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    for artifact in artifacts.values():
        api_id, op_id = artifact["id"].split("/", 1)
        api_dir = _find_api_dir(base, api_id)
        if not api_dir:
            api_dir = os.path.join(base, api_id)
        op_dir = os.path.join(api_dir, op_id)
        os.makedirs(op_dir, exist_ok=True)
        content = artifact["properties"].get("value", "")
        path = os.path.join(op_dir, "policy.xml")
        with open(path, "w") as f:
            f.write(content)


def _find_api_dir(base, api_id):
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        if entry == api_id or entry.endswith(f"_{api_id}"):
            path = os.path.join(base, entry)
            if os.path.isdir(path):
                return path
    return None


def to_rest_payload(artifact):
    return {"properties": artifact["properties"]}


def resource_path(artifact_id):
    api_id, op_id = artifact_id.split("/", 1)
    return f"/apis/{api_id}/operations/{op_id}/policies/policy"
