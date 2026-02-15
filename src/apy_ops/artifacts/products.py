"""Products artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "product"
SOURCE_SUBDIR = "products"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        entry_path = os.path.join(base, entry)
        if os.path.isdir(entry_path):
            info_path = os.path.join(entry_path, "productInformation.json")
            if not os.path.isfile(info_path):
                continue
            props = read_json(info_path)
            props = resolve_refs(props, entry_path)
        elif entry.endswith(".json"):
            props = read_json(entry_path)
            props = resolve_refs(props, base)
        else:
            continue
        prod_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{prod_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": prod_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    items = client.list("/products")
    artifacts = {}
    for item in items:
        prod_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{prod_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": prod_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        prod_id = artifact["id"]
        prod_dir = os.path.join(base, prod_id)
        os.makedirs(prod_dir, exist_ok=True)
        props = dict(artifact["properties"])
        props["id"] = f"/products/{prod_id}"
        info_path = os.path.join(prod_dir, "productInformation.json")
        with open(info_path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    props = dict(artifact["properties"])
    props.pop("id", None)
    # Remove cross-ref fields that aren't part of the REST payload
    props.pop("groups", None)
    props.pop("apis", None)
    return {"properties": props}


def resource_path(artifact_id: str) -> str:
    return f"/products/{artifact_id}"
