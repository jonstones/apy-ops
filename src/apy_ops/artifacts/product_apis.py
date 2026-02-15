"""Product-API associations artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "product_api"
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

        apis_path = os.path.join(prod_dir, "apis.json")
        if os.path.isfile(apis_path):
            api_ids = read_json(apis_path)
        elif "apis" in prod_info and isinstance(prod_info["apis"], list):
            api_ids = prod_info["apis"]
        else:
            continue

        for api_id in api_ids:
            if isinstance(api_id, dict):
                api_id = extract_id_from_path(api_id.get("id", ""))
            key = f"{ARTIFACT_TYPE}:{prod_id}/{api_id}"
            props = {"productId": prod_id, "apiId": api_id}
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{prod_id}/{api_id}",
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
            apis = client.list(f"/products/{prod_id}/apis")
            for api in apis:
                api_id = api["name"]
                key = f"{ARTIFACT_TYPE}:{prod_id}/{api_id}"
                props = {"productId": prod_id, "apiId": api_id}
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{prod_id}/{api_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    by_prod = {}
    for artifact in artifacts.values():
        prod_id = artifact["properties"]["productId"]
        api_id = artifact["properties"]["apiId"]
        by_prod.setdefault(prod_id, []).append(api_id)
    for prod_id, api_ids in by_prod.items():
        prod_dir = os.path.join(base, prod_id)
        os.makedirs(prod_dir, exist_ok=True)
        path = os.path.join(prod_dir, "apis.json")
        with open(path, "w") as f:
            json.dump(sorted(api_ids), f, indent=2)
            f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {}


def resource_path(artifact_id: str) -> str:
    prod_id, api_id = artifact_id.split("/", 1)
    return f"/products/{prod_id}/apis/{api_id}"
