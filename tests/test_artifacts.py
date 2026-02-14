"""Tests for artifact modules' read_local functions."""

import json
import os
import pytest


class TestNamedValues:
    def test_read_local(self, tmp_path):
        from artifacts.named_values import read_local
        nv_dir = tmp_path / "namedValues"
        nv_dir.mkdir()
        (nv_dir / "my-key.json").write_text(json.dumps({
            "id": "/namedValues/my-key",
            "displayName": "my-key",
            "value": "hello",
        }))
        result = read_local(str(tmp_path))
        assert "named_value:my-key" in result
        art = result["named_value:my-key"]
        assert art["type"] == "named_value"
        assert art["id"] == "my-key"
        assert art["hash"].startswith("sha256:")

    def test_read_local_empty_dir(self, tmp_path):
        from artifacts.named_values import read_local
        assert read_local(str(tmp_path)) == {}


class TestTags:
    def test_read_local(self, tmp_path):
        from artifacts.tags import read_local
        tag_dir = tmp_path / "tags"
        tag_dir.mkdir()
        (tag_dir / "env-prod.json").write_text(json.dumps({
            "id": "/tags/env-prod",
            "displayName": "Production",
        }))
        result = read_local(str(tmp_path))
        assert "tag:env-prod" in result
        assert result["tag:env-prod"]["properties"]["displayName"] == "Production"


class TestServicePolicy:
    def test_read_local_from_policy_dir(self, tmp_path):
        from artifacts.service_policy import read_local
        policy_dir = tmp_path / "policy"
        policy_dir.mkdir()
        (policy_dir / "policy.xml").write_text("<policies><inbound/></policies>")
        result = read_local(str(tmp_path))
        assert "service_policy:policy" in result
        assert "<policies>" in result["service_policy:policy"]["properties"]["value"]

    def test_read_local_no_policy(self, tmp_path):
        from artifacts.service_policy import read_local
        assert read_local(str(tmp_path)) == {}


class TestApis:
    def test_read_local_new_format(self, tmp_path):
        from artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "Echo API_echo-api"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo-api",
            "displayName": "Echo API",
            "path": "echo",
            "protocols": ["https"],
        }))
        (api_dir / "specification.json").write_text(json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "Echo", "version": "1.0"},
            "paths": {},
        }))
        # Operation file
        (api_dir / "get-echo.json").write_text(json.dumps({
            "id": "/apis/echo-api/operations/get-echo",
            "method": "GET",
            "urlTemplate": "/echo",
        }))
        result = read_local(str(tmp_path))
        assert "api:echo-api" in result
        art = result["api:echo-api"]
        assert art["type"] == "api"
        assert art["spec"] is not None
        assert art["spec"]["format"] == "openapi+json"
        assert "get-echo" in art["operations"]

    def test_read_local_old_format(self, tmp_path):
        from artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "legacy"
        api_dir.mkdir(parents=True)
        (api_dir / "configuration.json").write_text(json.dumps({
            "id": "/apis/legacy",
            "displayName": "Legacy",
            "path": "legacy",
        }))
        result = read_local(str(tmp_path))
        assert "api:legacy" in result

    def test_atomic_hash_changes_on_operation_change(self, tmp_path):
        from artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "test"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/test",
            "displayName": "Test",
            "path": "test",
        }))
        (api_dir / "op1.json").write_text(json.dumps({
            "id": "/apis/test/operations/op1",
            "method": "GET",
            "urlTemplate": "/v1",
        }))
        hash1 = read_local(str(tmp_path))["api:test"]["hash"]

        # Change operation
        (api_dir / "op1.json").write_text(json.dumps({
            "id": "/apis/test/operations/op1",
            "method": "GET",
            "urlTemplate": "/v2",
        }))
        hash2 = read_local(str(tmp_path))["api:test"]["hash"]
        assert hash1 != hash2


class TestProducts:
    def test_read_local(self, tmp_path):
        from artifacts.products import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter",
            "displayName": "Starter",
            "subscriptionRequired": True,
        }))
        result = read_local(str(tmp_path))
        assert "product:starter" in result
        assert result["product:starter"]["properties"]["displayName"] == "Starter"


class TestProductGroups:
    def test_read_local_with_groups_json(self, tmp_path):
        from artifacts.product_groups import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter",
            "displayName": "Starter",
        }))
        (prod_dir / "groups.json").write_text(json.dumps(["developers", "guests"]))
        result = read_local(str(tmp_path))
        assert "product_group:starter/developers" in result
        assert "product_group:starter/guests" in result
