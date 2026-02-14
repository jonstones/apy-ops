"""Product-Tag associations artifact module."""

import json
import os
from artifact_reader import read_json, compute_hash, extract_id_from_path

ARTIFACT_TYPE = "product_tag"
SOURCE_SUBDIR = "products"


def read_local(source_dir):
    base = os.path.join(source_dir, SOURCE_SUBDIR)
    if not os.path.isdir(base):
        return {}
    artifacts = {}
    for entry in sorted(os.listdir(base)):
        prod_dir = os.path.join(base, entry)
        if not os.path.isdir(prod_dir):
            continue
        info_path = os.path.join(prod_dir, "productInformation.json")
        if not os.path.isfile(info_path):
            continue
        prod_info = read_json(info_path)
        prod_id = extract_id_from_path(prod_info.get("id", entry))

        tags_path = os.path.join(prod_dir, "tags.json")
        if os.path.isfile(tags_path):
            tag_ids = read_json(tags_path)
        elif "tags" in prod_info and isinstance(prod_info["tags"], list):
            tag_ids = prod_info["tags"]
        else:
            continue

        for tag_id in tag_ids:
            if isinstance(tag_id, dict):
                tag_id = extract_id_from_path(tag_id.get("id", ""))
            key = f"{ARTIFACT_TYPE}:{prod_id}/{tag_id}"
            props = {"productId": prod_id, "tagId": tag_id}
            artifacts[key] = {
                "type": ARTIFACT_TYPE,
                "id": f"{prod_id}/{tag_id}",
                "hash": compute_hash(props),
                "properties": props,
            }
    return artifacts


def read_live(client):
    artifacts = {}
    try:
        products = client.list("/products")
    except Exception:
        return artifacts
    for prod in products:
        prod_id = prod["name"]
        try:
            tags = client.list(f"/products/{prod_id}/tags")
            for tag in tags:
                tag_id = tag["name"]
                key = f"{ARTIFACT_TYPE}:{prod_id}/{tag_id}"
                props = {"productId": prod_id, "tagId": tag_id}
                artifacts[key] = {
                    "type": ARTIFACT_TYPE,
                    "id": f"{prod_id}/{tag_id}",
                    "hash": compute_hash(props),
                    "properties": props,
                }
        except Exception:
            pass
    return artifacts


def write_local(output_dir, artifacts):
    base = os.path.join(output_dir, SOURCE_SUBDIR)
    by_prod = {}
    for artifact in artifacts.values():
        prod_id = artifact["properties"]["productId"]
        tag_id = artifact["properties"]["tagId"]
        by_prod.setdefault(prod_id, []).append(tag_id)
    for prod_id, tag_ids in by_prod.items():
        prod_dir = os.path.join(base, prod_id)
        os.makedirs(prod_dir, exist_ok=True)
        path = os.path.join(prod_dir, "tags.json")
        with open(path, "w") as f:
            json.dump(sorted(tag_ids), f, indent=2)
            f.write("\n")


def to_rest_payload(artifact):
    return {}


def resource_path(artifact_id):
    prod_id, tag_id = artifact_id.split("/", 1)
    return f"/products/{prod_id}/tags/{tag_id}"
