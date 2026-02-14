"""Gateways artifact module."""

import json
import os
from artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "gateway"
SOURCE_SUBDIR = "gateways"


def read_local(source_dir):
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        entry_path = os.path.join(base, entry)
        # Gateway can be a directory with gatewayInformation.json or a .json file
        if os.path.isdir(entry_path):
            info_path = os.path.join(entry_path, "gatewayInformation.json")
            if not os.path.isfile(info_path):
                continue
            props = read_json(info_path)
            props = resolve_refs(props, entry_path)
        elif entry.endswith(".json"):
            props = read_json(entry_path)
            props = resolve_refs(props, base)
        else:
            continue
        gw_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{gw_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": gw_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client):
    items = client.list("/gateways")
    artifacts = {}
    for item in items:
        gw_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{gw_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": gw_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        props = dict(artifact["properties"])
        props["id"] = f"/gateways/{artifact['id']}"
        path = os.path.join(base, f"{artifact['id']}.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact):
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id):
    return f"/gateways/{artifact_id}"
