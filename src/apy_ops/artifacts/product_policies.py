"""Product-level policy artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "product_policy"
SOURCE_SUBDIR = "products"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        prod_dir = os.path.join(base, entry)
        if not os.path.isdir(prod_dir):
            continue
        info_path = os.path.join(prod_dir, "productInformation.json")
        if not os.path.isfile(info_path):
            continue
        prod_info = read_json(info_path)
        prod_id = extract_id_from_path(prod_info.get("id", entry))

        policy_path = os.path.join(prod_dir, "policy.xml")
        if not os.path.isfile(policy_path):
            continue
        with open(policy_path, "r") as f:
            content = f.read()
        props = {"format": "rawxml", "value": content}
        key = f"{ARTIFACT_TYPE}:{prod_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": prod_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    artifacts = {}
    try:
        products = client.list("/products")
    except Exception:
        return artifacts
    for prod in products:
        prod_id = prod["name"]
        try:
            data = client.get(f"/products/{prod_id}/policies/policy")
            props = data.get("properties", {})
            key = f"{ARTIFACT_TYPE}:{prod_id}"
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": prod_id,
                "hash": compute_hash(props),
                "properties": props,
            }
        except Exception:
            pass
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    for artifact in artifacts.values():
        prod_id = artifact["id"]
        prod_dir = os.path.join(base, prod_id)
        os.makedirs(prod_dir, exist_ok=True)
        content = artifact["properties"].get("value", "")
        path = os.path.join(prod_dir, "policy.xml")
        with open(path, "w") as f:
            f.write(content)


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {"properties": artifact["properties"]}


def resource_path(artifact_id: str) -> str:
    return f"/products/{artifact_id}/policies/policy"
