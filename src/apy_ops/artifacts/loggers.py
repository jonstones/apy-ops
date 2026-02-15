"""Loggers artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "logger"
SOURCE_SUBDIR = "loggers"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        if not entry.endswith(".json") or not os.path.isfile(path):
            continue
        props = read_json(path)
        props = resolve_refs(props, base)
        lg_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{lg_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": lg_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    items = client.list("/loggers")
    artifacts = {}
    for item in items:
        lg_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{lg_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": lg_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        props = dict(artifact["properties"])
        props["id"] = f"/loggers/{artifact['id']}"
        path = os.path.join(base, f"{artifact['id']}.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id: str) -> str:
    return f"/loggers/{artifact_id}"
