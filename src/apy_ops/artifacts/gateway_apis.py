"""Gateway-API associations artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "gateway_api"
SOURCE_SUBDIR = "gateways"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        gw_dir = os.path.join(base, entry)
        if not os.path.isdir(gw_dir):
            continue
        # Gateway ID from directory name or info file
        info_path = os.path.join(gw_dir, "gatewayInformation.json")
        if os.path.isfile(info_path):
            gw_info = read_json(info_path)
            gw_id = extract_id_from_path(gw_info.get("id", entry))
        else:
            gw_id = entry

        apis_path = os.path.join(gw_dir, "apis.json")
        if not os.path.isfile(apis_path):
            continue
        api_ids = read_json(apis_path)
        for api_id in api_ids:
            if isinstance(api_id, dict):
                api_id = extract_id_from_path(api_id.get("id", ""))
            key = f"{ARTIFACT_TYPE}:{gw_id}/{api_id}"
            props = {"gatewayId": gw_id, "apiId": api_id}
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{gw_id}/{api_id}",
                "hash": compute_hash(props),
                "properties": props,
            }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    artifacts = {}
    try:
        gateways = client.list("/gateways")
    except Exception:
        return artifacts
    for gw in gateways:
        gw_id = gw["name"]
        try:
            apis = client.list(f"/gateways/{gw_id}/apis")
            for api in apis:
                api_id = api["name"]
                key = f"{ARTIFACT_TYPE}:{gw_id}/{api_id}"
                props = {"gatewayId": gw_id, "apiId": api_id}
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{gw_id}/{api_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    by_gw = {}
    for artifact in artifacts.values():
        gw_id = artifact["properties"]["gatewayId"]
        api_id = artifact["properties"]["apiId"]
        by_gw.setdefault(gw_id, []).append(api_id)
    for gw_id, api_ids in by_gw.items():
        gw_dir = os.path.join(base, gw_id)
        os.makedirs(gw_dir, exist_ok=True)
        path = os.path.join(gw_dir, "apis.json")
        with open(path, "w") as f:
            json.dump(sorted(api_ids), f, indent=2)
            f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {"properties": {"provisioningState": "created"}}


def resource_path(artifact_id: str) -> str:
    gw_id, api_id = artifact_id.split("/", 1)
    return f"/gateways/{gw_id}/apis/{api_id}"
