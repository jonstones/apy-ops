"""API Tags (association) artifact module."""

import json
import os
from apy_ops.artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api_tag"
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

        # Tags can be in a tags.json file or $refs-tags reference
        tags_path = os.path.join(api_dir, "tags.json")
        if os.path.isfile(tags_path):
            tag_ids = read_json(tags_path)
        elif "tags" in api_info and isinstance(api_info["tags"], list):
            tag_ids = api_info["tags"]
        else:
            continue

        for tag_id in tag_ids:
            if isinstance(tag_id, dict):
                tag_id = extract_id_from_path(tag_id.get("id", ""))
            key = f"{ARTIFACT_TYPE}:{api_id}/{tag_id}"
            props = {"apiId": api_id, "tagId": tag_id}
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{api_id}/{tag_id}",
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
            tags = client.list(f"/apis/{api_id}/tags")
            for tag in tags:
                tag_id = tag["name"]
                key = f"{ARTIFACT_TYPE}:{api_id}/{tag_id}"
                props = {"apiId": api_id, "tagId": tag_id}
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{api_id}/{tag_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    # Group tags by API
    by_api = {}
    for artifact in artifacts.values():
        api_id = artifact["properties"]["apiId"]
        tag_id = artifact["properties"]["tagId"]
        by_api.setdefault(api_id, []).append(tag_id)
    for api_id, tag_ids in by_api.items():
        api_dir = _find_api_dir(base, api_id)
        if not api_dir:
            api_dir = os.path.join(base, api_id)
            os.makedirs(api_dir, exist_ok=True)
        path = os.path.join(api_dir, "tags.json")
        with open(path, "w") as f:
            json.dump(sorted(tag_ids), f, indent=2)
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
    return {}  # PUT with empty body creates the association


def resource_path(artifact_id):
    api_id, tag_id = artifact_id.split("/", 1)
    return f"/apis/{api_id}/tags/{tag_id}"
