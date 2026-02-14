"""Policy Fragments artifact module."""

import json
import os
from apy_ops.artifact_reader import read_json, resolve_refs, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "policy_fragment"
SOURCE_SUBDIR = "policyFragments"


def read_local(source_dir):
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        entry_path = os.path.join(base, entry)
        if os.path.isdir(entry_path):
            info_path = os.path.join(entry_path, "policyFragmentInformation.json")
            if not os.path.isfile(info_path):
                continue
            props = read_json(info_path)
            props = resolve_refs(props, entry_path)
        elif entry.endswith(".json"):
            props = read_json(entry_path)
            props = resolve_refs(props, base)
        else:
            continue
        pf_id = extract_id_from_path(props.get("id", entry.replace(".json", "")))
        key = f"{ARTIFACT_TYPE}:{pf_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": pf_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def read_live(client):
    items = client.list("/policyFragments")
    artifacts = {}
    for item in items:
        pf_id = item["name"]
        props = item.get("properties", {})
        key = f"{ARTIFACT_TYPE}:{pf_id}"
        artifacts[key] = {
            "type": ARTIFACT_TYPE,
            "id": pf_id,
            "hash": compute_hash(props),
            "properties": props,
        }
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    for artifact in artifacts.values():
        pf_id = artifact["id"]
        pf_dir = os.path.join(base, pf_id)
        os.makedirs(pf_dir, exist_ok=True)
        props = dict(artifact["properties"])
        # Write policy XML separately if present
        policy_content = props.pop("policy", None)
        props["id"] = f"/policyFragments/{pf_id}"
        if policy_content:
            policy_path = os.path.join(pf_dir, "policy.xml")
            with open(policy_path, "w") as f:
                f.write(policy_content)
            props["$ref-policy"] = "policy.xml"
        info_path = os.path.join(pf_dir, "policyFragmentInformation.json")
        with open(info_path, "w") as f:
            json.dump(props, f, indent=2)
            f.write("\n")


def to_rest_payload(artifact):
    props = dict(artifact["properties"])
    props.pop("id", None)
    return {"properties": props}


def resource_path(artifact_id):
    return f"/policyFragments/{artifact_id}"
