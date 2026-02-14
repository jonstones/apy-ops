"""API-level Diagnostics artifact module."""

import json
import os
from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api_diagnostic"
SOURCE_SUBDIR = "apis"


def read_local(source_dir):
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        api_dir = os.path.join(base, entry)
        if not os.path.isdir(api_dir):
            continue
        info_path = os.path.join(api_dir, "apiInformation.json")
        if not os.path.isfile(info_path):
            info_path = os.path.join(api_dir, "configuration.json")
        if not os.path.isfile(info_path):
            continue
        api_info = read_json(info_path)
        api_id = extract_id_from_path(api_info.get("id", entry))

        diag_dir = os.path.join(api_dir, "diagnostics")
        if not os.path.isdir(diag_dir):
            continue
        for diag_entry in sorted(os.listdir(diag_dir)):
            if not diag_entry.endswith(".json"):
                continue
            diag_path = os.path.join(diag_dir, diag_entry)
            props = read_json(diag_path)
            props = resolve_refs(props, diag_dir)
            diag_id = extract_id_from_path(props.get("id", diag_entry.replace(".json", "")))
            key = f"{ARTIFACT_TYPE}:{api_id}/{diag_id}"
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{api_id}/{diag_id}",
                "hash": compute_hash(props),
                "properties": props,
            }
    return artifacts


def read_live(client):
    artifacts = {}
    try:
        apis = client.list("/apis")
    except Exception:
        return artifacts
    for api in apis:
        api_id = api["name"]
        try:
            diags = client.list(f"/apis/{api_id}/diagnostics")
            for diag in diags:
                diag_id = diag["name"]
                props = diag.get("properties", {})
                key = f"{ARTIFACT_TYPE}:{api_id}/{diag_id}"
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{api_id}/{diag_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    for artifact in artifacts.values():
        api_id, diag_id = artifact["id"].split("/", 1)
        api_dir = _find_api_dir(base, api_id)
        if not api_dir:
            api_dir = os.path.join(base, api_id)
        diag_dir = os.path.join(api_dir, "diagnostics")
        os.makedirs(diag_dir, exist_ok=True)
        props = dict(artifact["properties"])
        props["id"] = f"/apis/{api_id}/diagnostics/{diag_id}"
        path = os.path.join(diag_dir, f"{diag_id}.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def _find_api_dir(base, api_id):
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        if entry == api_id or entry.endswith(f"_{api_id}"):
            path = os.path.join(base, entry)
            if os.path.isdir(path):
                return path
    return None


def to_rest_payload(artifact):
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id):
    api_id, diag_id = artifact_id.split("/", 1)
    return f"/apis/{api_id}/diagnostics/{diag_id}"
