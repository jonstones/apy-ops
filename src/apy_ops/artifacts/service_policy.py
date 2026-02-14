"""Service (global) policy artifact module."""

import json
import os
from apy_ops.artifact_reader import compute_hash

ARTIFACT_TYPE = "service_policy"
SOURCE_SUBDIR = "policy"


def read_local(source_dir):
    # Global policy is at <source>/policy/policy.xml or <source>/policy.xml
    artifacts = {}
    for candidate in [
        os.path.join(source_dir, "policy", "policy.xml"),
        os.path.join(source_dir, "policy.xml"),
    ]:
        if os.path.isfile(candidate):
            with open(candidate, "r") as f:
                content = f.read()
            props = {"format": "rawxml", "value": content}
            key = f"{ARTIFACT_TYPE}:policy"
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": "policy",
                "hash": compute_hash(props),
                "properties": props,
            }
            break
    return artifacts


def read_live(client):
    artifacts = {}
    try:
        data = client.get("/policies/policy")
        props = data.get("properties", {})
        key = f"{ARTIFACT_TYPE}:policy"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": "policy",
            "hash": compute_hash(props),
            "properties": props,
        }
    except Exception:
        pass  # No global policy set
    return artifacts


def write_local(output_dir, artifacts):
    for artifact in artifacts.values():
        policy_dir = os.path.join(output_dir, "policy")
        os.makedirs(policy_dir, exist_ok=True)
        content = artifact["properties"].get("value", "")
        path = os.path.join(policy_dir, "policy.xml")
        with open(path, "w") as f:
            f.write(content)


def to_rest_payload(artifact):
    return {"properties": artifact["properties"]}


def resource_path(artifact_id):
    return "/policies/policy"
