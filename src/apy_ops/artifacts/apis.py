"""APIs artifact module — atomic unit (API + spec + operations)."""
from __future__ import annotations

import json
import os
from typing import Any

import yaml
from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "api"
SOURCE_SUBDIR = "apis"

# OpenAPI format mapping for the REST API 'format' field
SPEC_FORMAT_MAP = {
    ("json", 2): "swagger-json",
    ("json", 3): "openapi+json",
    ("yaml", 2): "swagger-link-json",
    ("yaml", 3): "openapi",
}


def _detect_spec_format(spec_path: str) -> tuple[str, str]:
    """Detect the spec file type and OpenAPI version, return (format_str, content)."""
    ext = os.path.splitext(spec_path)[1].lower()
    with open(spec_path, "r") as f:
        content = f.read()

    if ext == ".wsdl":
        return "wsdl", content
    if ext == ".wadl":
        return "wadl", content
    if ext == ".graphql":
        return "graphql", content

    # Detect OpenAPI/Swagger version
    if ext in (".yaml", ".yml"):
        try:
            parsed = yaml.safe_load(content)
        except Exception:
            return "openapi", content
        version = 3
        if parsed and (parsed.get("swagger") or "").startswith("2"):
            version = 2
        return SPEC_FORMAT_MAP.get(("yaml", version), "openapi"), content
    else:
        # JSON
        try:
            parsed = json.loads(content)
        except Exception:
            return "openapi+json", content
        version = 3
        if parsed and (parsed.get("swagger") or "").startswith("2"):
            version = 2
        return SPEC_FORMAT_MAP.get(("json", version), "openapi+json"), content


def _find_spec_file(api_dir: str) -> str | None:
    """Find the specification file in an API directory."""
    for name in ["specification.json", "specification.yaml", "specification.yml",
                  "specification.wsdl", "specification.wadl", "specification.graphql"]:
        path = os.path.join(api_dir, name)
        if os.path.isfile(path):
            return path
    return None


def _read_operations(api_dir: str) -> dict[str, dict[str, Any]]:
    """Read operations from separate files in the API directory.

    Handles the old format (operation.json files directly in api_dir)
    and new format (operations/{opId}/ directories with policy.xml).
    """
    ops = {}
    # Check for new format: operations/ subdirectory
    ops_dir = os.path.join(api_dir, "operations")
    if os.path.isdir(ops_dir):
        for entry in sorted(os.listdir(ops_dir)):
            op_path = os.path.join(ops_dir, entry)
            if not os.path.isdir(op_path):
                continue
            # Operation ID is the directory name
            # Operation properties are not stored locally in this format
            # (they come from the spec or are fetched live)
            ops[entry] = {"id": f"/apis/{os.path.basename(api_dir)}/operations/{entry}"}
        return ops

    # Old format: JSON files directly in api_dir
    for entry in sorted(os.listdir(api_dir)):
        if not entry.endswith(".json"):
            continue
        if entry in ("apiInformation.json", "configuration.json", "tags.json"):
            continue
        if entry.startswith("specification."):
            continue
        path = os.path.join(api_dir, entry)
        if not os.path.isfile(path):
            continue
        op_props = read_json(path)
        # Skip non-dict JSON files (e.g., tags.json which is a list)
        if not isinstance(op_props, dict):
            continue
        op_props = resolve_refs(op_props, api_dir)
        op_id = extract_id_from_path(op_props.get("id", entry.replace(".json", "")))
        ops[op_id] = op_props
    return ops


def read_local(source_dir: str) -> dict[str, dict[str, Any]]:
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        api_dir = os.path.join(base, entry)
        if not os.path.isdir(api_dir):
            continue

        # Read API info (new format: apiInformation.json, old: configuration.json)
        info_path = os.path.join(api_dir, "apiInformation.json")
        if not os.path.isfile(info_path):
            info_path = os.path.join(api_dir, "configuration.json")
        if not os.path.isfile(info_path):
            continue

        props = read_json(info_path)
        props = resolve_refs(props, api_dir)
        api_id = extract_id_from_path(props.get("id", entry))

        # Read spec file
        spec_path = _find_spec_file(api_dir)
        spec_data = None
        if spec_path:
            fmt, content = _detect_spec_format(spec_path)
            spec_data = {"format": fmt, "content": content, "path": os.path.basename(spec_path)}

        # Read operations (from separate files, not inline in configuration.json)
        operations = _read_operations(api_dir)

        # Build composite properties for hashing (atomic unit)
        composite = {
            "apiInfo": props,
            "spec": spec_data,
            "operations": operations,
        }

        key = f"{ARTIFACT_TYPE}:{api_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": api_id,
            "hash": compute_hash(composite),
            "properties": props,
            "spec": spec_data,
            "operations": operations,
        }
    return artifacts


def read_live(client: Any) -> dict[str, dict[str, Any]]:
    items = client.list("/apis")
    artifacts = {}
    for item in items:
        api_id = item["name"]
        props = item.get("properties", {})

        # Fetch operations for this API
        operations = {}
        try:
            ops = client.list(f"/apis/{api_id}/operations")
            for op in ops:
                op_id = op["name"]
                operations[op_id] = op.get("properties", {})
        except Exception:
            pass

        composite = {
            "apiInfo": props,
            "spec": None,
            "operations": operations,
        }

        key = f"{ARTIFACT_TYPE}:{api_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": api_id,
            "hash": compute_hash(composite),
            "properties": props,
            "spec": None,
            "operations": operations,
        }
    return artifacts


def write_local(output_dir: str, artifacts: dict[str, dict[str, Any]]) -> None:
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        api_id = artifact["id"]
        display = artifact["properties"].get("displayName", api_id)
        dir_name = f"{display}_{api_id}" if display != api_id else api_id
        # Sanitize directory name
        dir_name = dir_name.replace("/", "_").replace("\\", "_")
        api_dir = os.path.join(base, dir_name)
        os.makedirs(api_dir, exist_ok=True)

        # Write apiInformation.json
        props = dict(artifact["properties"])
        props["id"] = f"/apis/{api_id}"
        info_path = os.path.join(api_dir, "apiInformation.json")
        with open(info_path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")

        # Write operations
        for op_id, op_props in artifact.get("operations", {}).items():
            op_props_out = dict(op_props)
            op_props_out["id"] = f"/apis/{api_id}/operations/{op_id}"
            op_path = os.path.join(api_dir, f"{op_id}.json")
            with open(op_path, "w") as f:
                json.dump(op_props_out, f, indent=2)
                f.write("\n")


def to_rest_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    """Build the PUT body for the API resource.

    If a spec file is present, include it as an import payload.
    """
    props = dict(artifact["properties"])
    props.pop("id", None)
    payload = {"properties": props}

    spec = artifact.get("spec")
    if spec:
        payload["properties"]["format"] = spec["format"]
        payload["properties"]["value"] = spec["content"]

    return payload


def to_operation_payloads(artifact: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return list of (op_id, payload) for each operation to PUT."""
    results = []
    for op_id, op_props in artifact.get("operations", {}).items():
        props = dict(op_props)
        props.pop("id", None)
        results.append((op_id, {"properties": props}))
    return results


def resource_path(artifact_id: str) -> str:
    return f"/apis/{artifact_id}"
