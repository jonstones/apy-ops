"""Reads APIOps git-extracted directory structure, resolves cross-references, computes hashes."""

import hashlib
import json
import os


def resolve_refs(props, base_dir):
    """Recursively resolve $ref-* keys in a properties dict.

    $ref-policy → read XML file content
    $ref-description / $ref-body → read HTML file content
    $refs-groups / $refs-apis → read JSON array of IDs
    $ref-Original / $ref-Production / $ref-Preview → read file content
    """
    if not isinstance(props, dict):
        return props

    resolved = {}
    for key, value in props.items():
        if key.startswith("$ref-"):
            ref_name = key[5:]  # strip "$ref-"
            ref_path = os.path.join(base_dir, value) if isinstance(value, str) else None
            if ref_path and os.path.isfile(ref_path):
                with open(ref_path, "r") as f:
                    resolved[ref_name] = f.read()
            else:
                resolved[ref_name] = value
        elif key.startswith("$refs-"):
            ref_name = key[6:]  # strip "$refs-"
            ref_path = os.path.join(base_dir, value) if isinstance(value, str) else None
            if ref_path and os.path.isfile(ref_path):
                with open(ref_path, "r") as f:
                    resolved[ref_name] = json.load(f)
            else:
                resolved[ref_name] = value
        elif isinstance(value, dict):
            resolved[key] = resolve_refs(value, base_dir)
        elif isinstance(value, list):
            resolved[key] = [
                resolve_refs(item, base_dir) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def compute_hash(properties):
    """Compute SHA256 hash of normalized (sorted-keys) JSON representation."""
    canonical = json.dumps(properties, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read_json(path):
    """Read and parse a JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def find_artifact_dirs(source_dir, subdir):
    """Find all artifact directories/files under source_dir/subdir.

    Returns list of (name, path) tuples.
    """
    base = os.path.join(source_dir, subdir)
    if not os.path.isdir(base):
        return []
    results = []
    for entry in sorted(os.listdir(base)):
        full = os.path.join(base, entry)
        results.append((entry, full))
    return results


def extract_id_from_path(id_path):
    """Extract the short ID from an APIOps id path.

    "/apis/echo-api" → "echo-api"
    "/products/starter" → "starter"
    "/apis/echo-api/operations/get-op" → "get-op"
    """
    return id_path.rstrip("/").rsplit("/", 1)[-1]
