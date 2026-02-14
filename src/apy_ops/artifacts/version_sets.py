"""API Version Sets artifact module."""

import json
import os
from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "version_set"
SOURCE_SUBDIR = "apiVersionSets"


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
        vs_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{vs_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": vs_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client):
    items = client.list("/apiVersionSets")
    artifacts = {}
    for item in items:
        vs_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{vs_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": vs_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        props = dict(artifact["properties"])
        props["id"] = f"/apiVersionSets/{artifact['id']}"
        path = os.path.join(base, f"{artifact['id']}.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact):
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id):
    return f"/apiVersionSets/{artifact_id}"
