"""API Revisions artifact module."""
from __future__ import annotations

import json
import os
from typing import Any

from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api_revision"
SOURCE_SUBDIR = "apis"


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
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

        releases_dir = os.path.join(api_dir, "releases")
        if not os.path.isdir(releases_dir):
            continue
        for release_entry in sorted(os.listdir(releases_dir)):
            release_dir = os.path.join(releases_dir, release_entry)
            if not os.path.isdir(release_dir):
                continue
            # Warn about clearly foreign files inside the release directory.
            for file_name in sorted(os.listdir(release_dir)):
                file_path = os.path.join(release_dir, file_name)
                if os.path.isfile(file_path) and not (
                    file_name.endswith(".json") or file_name.endswith(".xml")
                ):
                    print(
                        "WARNING: foreign file ignored in API release directory "
                        f"{release_dir}: {file_path}"
                    )
            info_file = os.path.join(release_dir, "apiReleaseInformation.json")
            if not os.path.isfile(info_file):
                continue
            props = read_json(info_file)
            props = resolve_refs(props, release_dir)
            release_id = extract_id_from_path(props.get("id", release_entry))
            key = f"{ARTIFACT_TYPE}:{api_id}/{release_id}"
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{api_id}/{release_id}",
                "hash": compute_hash(props),
                "properties": props,
            }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    artifacts = {}
    try:
        apis = client.list("/apis")
    except Exception:
        return artifacts
    for api in apis:
        api_id = api["name"]
        try:
            releases = client.list(f"/apis/{api_id}/releases")
            for release in releases:
                release_id = release["name"]
                props = release.get("properties", {})
                key = f"{ARTIFACT_TYPE}:{api_id}/{release_id}"
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{api_id}/{release_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    for artifact in artifacts.values():
        api_id, release_id = artifact["id"].split("/", 1)
        api_dir = _find_api_dir(base, api_id)
        if not api_dir:
            api_dir = os.path.join(base, api_id)
        releases_dir = os.path.join(api_dir, "releases")
        release_dir = os.path.join(releases_dir, release_id)
        os.makedirs(release_dir, exist_ok=True)
        props = dict(artifact["properties"])
        props["id"] = f"/apis/{api_id}/releases/{release_id}"
        path = os.path.join(release_dir, "apiReleaseInformation.json")
        with open(path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def _find_api_dir(base: str, api_id: str) -> str | None:
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        if entry == api_id or entry.endswith(f"_{api_id}"):
            path = os.path.join(base, entry)
            if os.path.isdir(path):
                return path
    return None


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id: str) -> str:
    api_id, release_id = artifact_id.split("/", 1)
    return f"/apis/{api_id}/releases/{release_id}"
