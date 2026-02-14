"""Backends artifact module."""

import json
import os
from artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "backend"
SOURCE_SUBDIR = "backends"


def read_local(source_dir):
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
        be_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{be_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": be_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client):
    items = client.list("/backends")
    artifacts = {}
    for item in items:
        be_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{be_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": be_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        props = dict(artifact["properties"])
        props["id"] = f"/backends/{artifact['id']}"
        path = os.path.join(base, f"{artifact['id']}.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact):
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id):
    return f"/backends/{artifact_id}"
