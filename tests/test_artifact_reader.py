"""Tests for artifact_reader module."""

import json
import os
import pytest
from apy_ops.artifact_reader import resolve_refs, compute_hash, extract_id_from_path


class TestResolveRefs:
    def test_ref_policy_reads_xml_file(self, tmp_path):
        xml_content = "<policies><inbound /></policies>"
        (tmp_path / "policy.xml").write_text(xml_content)
        props = {"$ref-policy": "policy.xml", "name": "test"}
        result = resolve_refs(props, str(tmp_path))
        assert result["policy"] == xml_content
        assert result["name"] == "test"
        assert "$ref-policy" not in result

    def test_ref_description_reads_html_file(self, tmp_path):
        html = "<p>My API</p>"
        (tmp_path / "desc.html").write_text(html)
        props = {"$ref-description": "desc.html"}
        result = resolve_refs(props, str(tmp_path))
        assert result["description"] == html

    def test_refs_groups_reads_json_array(self, tmp_path):
        groups = ["developers", "admins"]
        (tmp_path / "groups.json").write_text(json.dumps(groups))
        props = {"$refs-groups": "groups.json"}
        result = resolve_refs(props, str(tmp_path))
        assert result["groups"] == ["developers", "admins"]

    def test_nested_dict_resolved(self, tmp_path):
        (tmp_path / "inner.xml").write_text("<policy/>")
        props = {"outer": {"$ref-policy": "inner.xml"}}
        result = resolve_refs(props, str(tmp_path))
        assert result["outer"]["policy"] == "<policy/>"

    def test_list_with_dicts_resolved(self, tmp_path):
        (tmp_path / "p.xml").write_text("<x/>")
        props = {"items": [{"$ref-policy": "p.xml"}, "plain"]}
        result = resolve_refs(props, str(tmp_path))
        assert result["items"][0]["policy"] == "<x/>"
        assert result["items"][1] == "plain"

    def test_missing_ref_file_keeps_value(self, tmp_path):
        props = {"$ref-policy": "nonexistent.xml"}
        result = resolve_refs(props, str(tmp_path))
        assert result["policy"] == "nonexistent.xml"

    def test_non_dict_input_returned_as_is(self):
        assert resolve_refs("hello", "/tmp") == "hello"
        assert resolve_refs(42, "/tmp") == 42


class TestComputeHash:
    def test_deterministic(self):
        props = {"a": 1, "b": "two"}
        assert compute_hash(props) == compute_hash(props)

    def test_key_order_irrelevant(self):
        h1 = compute_hash({"a": 1, "b": 2})
        h2 = compute_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_values_different_hash(self):
        h1 = compute_hash({"a": 1})
        h2 = compute_hash({"a": 2})
        assert h1 != h2

    def test_hash_prefix(self):
        h = compute_hash({"x": "y"})
        assert h.startswith("sha256:")
        assert len(h) == 7 + 64  # "sha256:" + 64 hex chars


class TestExtractIdFromPath:
    def test_api_path(self):
        assert extract_id_from_path("/apis/echo-api") == "echo-api"

    def test_product_path(self):
        assert extract_id_from_path("/products/starter") == "starter"

    def test_operation_path(self):
        assert extract_id_from_path("/apis/echo-api/operations/get-op") == "get-op"

    def test_trailing_slash_ignored(self):
        assert extract_id_from_path("/apis/echo-api/") == "echo-api"

    def test_simple_id(self):
        assert extract_id_from_path("my-id") == "my-id"
