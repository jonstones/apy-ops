"""Subscriptions artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "subscription"
SOURCE_SUBDIR = "subscriptions"
INFORMATION_FILE = "subscriptionInformation.json"
REST_PATH_PREFIX = "subscriptions"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        entry_path = os.path.join(base, entry)
        if not os.path.isdir(entry_path):
            continue
        info_path = os.path.join(entry_path, INFORMATION_FILE)
        if not os.path.isfile(info_path):
            continue
        props = read_json(info_path)
        props = resolve_refs(props, entry_path)
        sub_id = extract_id_from_path(props.get("id", entry))
        key = f"{ARTIFACT_TYPE}:{sub_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": sub_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    items = client.list("/subscriptions")
    artifacts = {}
    for item in items:
        sub_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{sub_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": sub_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        artifact_id = artifact["id"]
        artifact_dir = os.path.join(base, artifact_id)
        os.makedirs(artifact_dir, exist_ok=True)
        props = dict(artifact["properties"])
        props["id"] = f"/{REST_PATH_PREFIX}/{artifact_id}"
        info_path = os.path.join(artifact_dir, INFORMATION_FILE)
        with open(info_path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id: str) -> str:
    return f"/subscriptions/{artifact_id}"
