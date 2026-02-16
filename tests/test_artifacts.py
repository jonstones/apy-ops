"""Tests for artifact modules."""

import json
import os

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_artifact(artifact_type, artifact_id, props):
    """Build a minimal artifact dict for testing to_rest_payload / write_local."""
    from apy_ops.artifact_reader import compute_hash
    return {
        "type": artifact_type,
        "id": artifact_id,
        "hash": compute_hash(props),
        "properties": props,
    }


def _mock_client_list(items_by_path):
    """Return a MagicMock client whose .list(path) returns items_by_path[path]."""
    client = MagicMock()
    client.list.side_effect = lambda path: items_by_path.get(path, [])
    return client


def _mock_client_get(data_by_path):
    """Return a MagicMock client whose .get(path) returns data_by_path[path] or raises."""
    client = MagicMock()
    def _get(path):
        if path in data_by_path:
            return data_by_path[path]
        raise Exception("404 Not Found")
    client.get.side_effect = _get
    client.list.side_effect = lambda path: data_by_path.get(path, [])
    return client


# ===================================================================
# 1. Simple flat-file modules
# ===================================================================

_SIMPLE_MODULES = [
    ("apy_ops.artifacts.named_values", "named_value", "namedValues", "/namedValues"),
    ("apy_ops.artifacts.tags", "tag", "tags", "/tags"),
    ("apy_ops.artifacts.backends", "backend", "backends", "/backends"),
    ("apy_ops.artifacts.loggers", "logger", "loggers", "/loggers"),
    ("apy_ops.artifacts.diagnostics", "diagnostic", "diagnostics", "/diagnostics"),
    ("apy_ops.artifacts.groups", "group", "groups", "/groups"),
    ("apy_ops.artifacts.subscriptions", "subscription", "subscriptions", "/subscriptions"),
    ("apy_ops.artifacts.version_sets", "version_set", "apiVersionSets", "/apiVersionSets"),
]


class TestSimpleModules:
    """Parametrized tests covering all 8 simple flat-file artifact modules."""

    @pytest.fixture(params=_SIMPLE_MODULES, ids=[m[1] for m in _SIMPLE_MODULES])
    def mod_info(self, request):
        import importlib
        mod_path, art_type, subdir, rest_prefix = request.param
        mod = importlib.import_module(mod_path)
        return mod, art_type, subdir, rest_prefix

    # Tests that read_local parses all simple flat-file artifact modules from disk.
    def test_read_local(self, tmp_path, mod_info):
        mod, art_type, subdir, rest_prefix = mod_info
        d = tmp_path / subdir
        d.mkdir()
        (d / "item1.json").write_text(json.dumps({
            "id": f"{rest_prefix}/item1",
            "displayName": "Item 1",
        }))
        result = mod.read_local(str(tmp_path))
        key = f"{art_type}:item1"
        assert key in result
        assert result[key]["type"] == art_type
        assert result[key]["id"] == "item1"
        assert result[key]["hash"].startswith("sha256:")

    # Tests that read_local returns empty dict when no artifacts exist.
    def test_read_local_empty(self, tmp_path, mod_info):
        mod, *_ = mod_info
        assert mod.read_local(str(tmp_path)) == {}

    # Tests that write_local saves artifacts to disk and reads back identically.
    def test_write_local_roundtrip(self, tmp_path, mod_info):
        mod, art_type, subdir, rest_prefix = mod_info
        props = {"id": f"{rest_prefix}/x1", "displayName": "X1", "extra": "val"}
        artifacts = {f"{art_type}:x1": _make_artifact(art_type, "x1", props)}
        out = tmp_path / "out"
        out.mkdir()
        mod.write_local(str(out), artifacts)
        path = out / subdir / "x1.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["displayName"] == "X1"
        assert data["id"] == f"{rest_prefix}/x1"

    # Tests that to_rest_payload generates correct Azure REST API body format.
    def test_to_rest_payload(self, mod_info):
        mod, art_type, subdir, rest_prefix = mod_info
        props = {"id": f"{rest_prefix}/x1", "displayName": "X1"}
        artifact = _make_artifact(art_type, "x1", props)
        payload = mod.to_rest_payload(artifact)
        assert "properties" in payload
        assert "id" not in payload["properties"]
        assert payload["properties"]["displayName"] == "X1"

    # Tests that resource_path generates correct REST API path for artifact ID.
    def test_resource_path(self, mod_info):
        mod, art_type, subdir, rest_prefix = mod_info
        assert mod.resource_path("my-id") == f"{rest_prefix}/my-id"

    # Tests that read_live fetches artifacts from APIM REST API.
    def test_read_live(self, mod_info):
        mod, art_type, subdir, rest_prefix = mod_info
        client = _mock_client_list({
            rest_prefix: [
                {"name": "live1", "properties": {"displayName": "Live 1"}},
            ]
        })
        result = mod.read_live(client)
        key = f"{art_type}:live1"
        assert key in result
        assert result[key]["id"] == "live1"
        assert result[key]["properties"]["displayName"] == "Live 1"
        assert result[key]["hash"].startswith("sha256:")


# ===================================================================
# 2. Directory-based modules
# ===================================================================

class TestProducts:
    # Tests that read_local parses product directory format with productInformation.json.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.products import read_local
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

    # Tests that write_local saves product directory structure with productInformation.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.products import write_local
        artifacts = {"product:starter": _make_artifact("product", "starter", {
            "displayName": "Starter", "subscriptionRequired": True,
        })}
        write_local(str(tmp_path), artifacts)
        info = tmp_path / "products" / "starter" / "productInformation.json"
        assert info.is_file()
        data = json.loads(info.read_text())
        assert data["displayName"] == "Starter"
        assert data["id"] == "/products/starter"

    # Tests that to_rest_payload removes cross-reference fields (groups, apis).
    def test_to_rest_payload_strips_cross_refs(self):
        from apy_ops.artifacts.products import to_rest_payload
        artifact = _make_artifact("product", "starter", {
            "id": "/products/starter", "displayName": "Starter",
            "groups": ["developers"], "apis": ["echo-api"],
        })
        payload = to_rest_payload(artifact)
        assert "groups" not in payload["properties"]
        assert "apis" not in payload["properties"]
        assert "id" not in payload["properties"]

    # Tests that resource_path generates correct product REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.products import resource_path
        assert resource_path("starter") == "/products/starter"

    # Tests that read_live fetches products from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.products import read_live
        client = _mock_client_list({
            "/products": [{"name": "starter", "properties": {"displayName": "Starter"}}],
        })
        result = read_live(client)
        assert "product:starter" in result


class TestGateways:
    # Tests that read_local parses gateway directory format with gatewayInformation.json.
    def test_read_local_directory_format(self, tmp_path):
        from apy_ops.artifacts.gateways import read_local
        gw_dir = tmp_path / "gateways" / "my-gw"
        gw_dir.mkdir(parents=True)
        (gw_dir / "gatewayInformation.json").write_text(json.dumps({
            "id": "/gateways/my-gw", "displayName": "My Gateway",
        }))
        result = read_local(str(tmp_path))
        assert "gateway:my-gw" in result

    # Tests that read_local supports gateway flat JSON file format.
    def test_read_local_flat_format(self, tmp_path):
        from apy_ops.artifacts.gateways import read_local
        gw_dir = tmp_path / "gateways"
        gw_dir.mkdir()
        (gw_dir / "my-gw.json").write_text(json.dumps({
            "id": "/gateways/my-gw", "displayName": "My Gateway",
        }))
        result = read_local(str(tmp_path))
        assert "gateway:my-gw" in result

    # Tests that write_local saves gateway as flat JSON file.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.gateways import write_local
        artifacts = {"gateway:gw1": _make_artifact("gateway", "gw1", {
            "displayName": "GW1",
        })}
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "gateways" / "gw1.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["id"] == "/gateways/gw1"

    # Tests that to_rest_payload generates correct gateway REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.gateways import to_rest_payload
        artifact = _make_artifact("gateway", "gw1", {
            "id": "/gateways/gw1", "displayName": "GW1",
        })
        payload = to_rest_payload(artifact)
        assert "id" not in payload["properties"]
        assert payload["properties"]["displayName"] == "GW1"

    # Tests that resource_path generates correct gateway REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.gateways import resource_path
        assert resource_path("gw1") == "/gateways/gw1"

    # Tests that read_live fetches gateways from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.gateways import read_live
        client = _mock_client_list({
            "/gateways": [{"name": "gw1", "properties": {"displayName": "GW1"}}],
        })
        result = read_live(client)
        assert "gateway:gw1" in result


class TestPolicyFragments:
    # Tests that read_local parses policy fragment directory format with policyFragmentInformation.json.
    def test_read_local_directory_format(self, tmp_path):
        from apy_ops.artifacts.policy_fragments import read_local
        pf_dir = tmp_path / "policyFragments" / "my-frag"
        pf_dir.mkdir(parents=True)
        (pf_dir / "policyFragmentInformation.json").write_text(json.dumps({
            "id": "/policyFragments/my-frag", "displayName": "My Fragment",
        }))
        result = read_local(str(tmp_path))
        assert "policy_fragment:my-frag" in result

    # Tests that read_local supports policy fragment flat JSON file format.
    def test_read_local_flat_format(self, tmp_path):
        from apy_ops.artifacts.policy_fragments import read_local
        pf_dir = tmp_path / "policyFragments"
        pf_dir.mkdir()
        (pf_dir / "my-frag.json").write_text(json.dumps({
            "id": "/policyFragments/my-frag", "displayName": "My Fragment",
        }))
        result = read_local(str(tmp_path))
        assert "policy_fragment:my-frag" in result

    # Tests that write_local saves policy fragment as directory with policy.xml.
    def test_write_local_with_policy(self, tmp_path):
        from apy_ops.artifacts.policy_fragments import write_local
        artifacts = {"policy_fragment:frag1": _make_artifact("policy_fragment", "frag1", {
            "displayName": "Frag1", "policy": "<fragment>hello</fragment>",
        })}
        write_local(str(tmp_path), artifacts)
        info = tmp_path / "policyFragments" / "frag1" / "policyFragmentInformation.json"
        policy = tmp_path / "policyFragments" / "frag1" / "policy.xml"
        assert info.is_file()
        assert policy.is_file()
        assert policy.read_text() == "<fragment>hello</fragment>"
        data = json.loads(info.read_text())
        assert data["$ref-policy"] == "policy.xml"
        assert "policy" not in data  # inline policy removed

    # Tests that to_rest_payload generates correct policy fragment REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.policy_fragments import to_rest_payload
        artifact = _make_artifact("policy_fragment", "frag1", {
            "id": "/policyFragments/frag1", "displayName": "Frag1",
        })
        payload = to_rest_payload(artifact)
        assert "id" not in payload["properties"]

    # Tests that resource_path generates correct policy fragment REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.policy_fragments import resource_path
        assert resource_path("frag1") == "/policyFragments/frag1"

    # Tests that read_live fetches policy fragments from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.policy_fragments import read_live
        client = _mock_client_list({
            "/policyFragments": [{"name": "frag1", "properties": {"displayName": "Frag1"}}],
        })
        result = read_live(client)
        assert "policy_fragment:frag1" in result


# ===================================================================
# 3. Singleton: service_policy
# ===================================================================

class TestServicePolicy:
    # Tests that read_local reads global service policy from policy directory.
    def test_read_local_from_policy_dir(self, tmp_path):
        from apy_ops.artifacts.service_policy import read_local
        policy_dir = tmp_path / "policy"
        policy_dir.mkdir()
        (policy_dir / "policy.xml").write_text("<policies><inbound/></policies>")
        result = read_local(str(tmp_path))
        assert "service_policy:policy" in result
        assert "<policies>" in result["service_policy:policy"]["properties"]["value"]

    # Tests that read_local returns empty dict when no policy exists.
    def test_read_local_no_policy(self, tmp_path):
        from apy_ops.artifacts.service_policy import read_local
        assert read_local(str(tmp_path)) == {}

    # Tests that write_local saves service policy to policy directory.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.service_policy import write_local
        artifacts = {"service_policy:policy": _make_artifact("service_policy", "policy", {
            "format": "rawxml", "value": "<policies/>",
        })}
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "policy" / "policy.xml"
        assert path.is_file()
        assert path.read_text() == "<policies/>"

    # Tests that to_rest_payload generates correct service policy REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.service_policy import to_rest_payload
        artifact = _make_artifact("service_policy", "policy", {
            "format": "rawxml", "value": "<policies/>",
        })
        payload = to_rest_payload(artifact)
        assert payload == {"properties": {"format": "rawxml", "value": "<policies/>"}}

    # Tests that resource_path generates correct service policy REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.service_policy import resource_path
        assert resource_path("policy") == "/policies/policy"

    # Tests that read_live fetches global service policy from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.service_policy import read_live
        client = _mock_client_get({
            "/policies/policy": {"properties": {"format": "rawxml", "value": "<p/>"}},
        })
        result = read_live(client)
        assert "service_policy:policy" in result
        assert result["service_policy:policy"]["properties"]["value"] == "<p/>"

    # Tests that read_live handles 404 when service policy does not exist.
    def test_read_live_no_policy(self):
        from apy_ops.artifacts.service_policy import read_live
        client = MagicMock()
        client.get.side_effect = Exception("404")
        assert read_live(client) == {}


# ===================================================================
# 4. Complex: apis
# ===================================================================

class TestApis:
    # Tests that read_local parses new API format with apiInformation.json and separate spec file.
    def test_read_local_new_format(self, tmp_path):
        from apy_ops.artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "Echo API_echo-api"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo-api", "displayName": "Echo API",
            "path": "echo", "protocols": ["https"],
        }))
        (api_dir / "specification.json").write_text(json.dumps({
            "openapi": "3.0.0", "info": {"title": "Echo", "version": "1.0"}, "paths": {},
        }))
        (api_dir / "get-echo.json").write_text(json.dumps({
            "id": "/apis/echo-api/operations/get-echo", "method": "GET", "urlTemplate": "/echo",
        }))
        result = read_local(str(tmp_path))
        assert "api:echo-api" in result
        art = result["api:echo-api"]
        assert art["type"] == "api"
        assert art["spec"] is not None
        assert art["spec"]["format"] == "openapi+json"
        assert "get-echo" in art["operations"]

    # Tests that read_local supports old API format with configuration.json.
    def test_read_local_old_format(self, tmp_path):
        from apy_ops.artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "legacy"
        api_dir.mkdir(parents=True)
        (api_dir / "configuration.json").write_text(json.dumps({
            "id": "/apis/legacy", "displayName": "Legacy", "path": "legacy",
        }))
        result = read_local(str(tmp_path))
        assert "api:legacy" in result

    # Tests that API hash changes when any operation is modified (atomic unit).
    def test_atomic_hash_changes_on_operation_change(self, tmp_path):
        from apy_ops.artifacts.apis import read_local
        api_dir = tmp_path / "apis" / "test"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/test", "displayName": "Test", "path": "test",
        }))
        (api_dir / "op1.json").write_text(json.dumps({
            "id": "/apis/test/operations/op1", "method": "GET", "urlTemplate": "/v1",
        }))
        hash1 = read_local(str(tmp_path))["api:test"]["hash"]
        (api_dir / "op1.json").write_text(json.dumps({
            "id": "/apis/test/operations/op1", "method": "GET", "urlTemplate": "/v2",
        }))
        hash2 = read_local(str(tmp_path))["api:test"]["hash"]
        assert hash1 != hash2

    # Tests that write_local saves API directory structure with operations.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.apis import write_local
        artifacts = {"api:echo": {
            "type": "api", "id": "echo", "hash": "sha256:x",
            "properties": {"displayName": "Echo API", "path": "echo"},
            "spec": None,
            "operations": {
                "get-echo": {"method": "GET", "urlTemplate": "/echo"},
            },
        }}
        write_local(str(tmp_path), artifacts)
        api_dir = tmp_path / "apis" / "Echo API_echo"
        assert api_dir.is_dir()
        info = json.loads((api_dir / "apiInformation.json").read_text())
        assert info["id"] == "/apis/echo"
        assert info["displayName"] == "Echo API"
        op = json.loads((api_dir / "get-echo.json").read_text())
        assert op["method"] == "GET"
        assert op["id"] == "/apis/echo/operations/get-echo"

    # Tests that to_rest_payload generates API payload without specification.
    def test_to_rest_payload_without_spec(self):
        from apy_ops.artifacts.apis import to_rest_payload
        artifact = {
            "type": "api", "id": "echo", "hash": "sha256:x",
            "properties": {"id": "/apis/echo", "displayName": "Echo", "path": "echo"},
            "spec": None, "operations": {},
        }
        payload = to_rest_payload(artifact)
        assert "id" not in payload["properties"]
        assert payload["properties"]["displayName"] == "Echo"

    # Tests that to_rest_payload includes specification in API payload.
    def test_to_rest_payload_with_spec(self):
        from apy_ops.artifacts.apis import to_rest_payload
        artifact = {
            "type": "api", "id": "echo", "hash": "sha256:x",
            "properties": {"displayName": "Echo", "path": "echo"},
            "spec": {"format": "openapi+json", "content": "{}", "path": "specification.json"},
            "operations": {},
        }
        payload = to_rest_payload(artifact)
        assert payload["properties"]["format"] == "openapi+json"
        assert payload["properties"]["value"] == "{}"

    # Tests that to_operation_payloads generates REST payloads for all operations.
    def test_to_operation_payloads(self):
        from apy_ops.artifacts.apis import to_operation_payloads
        artifact = {
            "type": "api", "id": "echo", "hash": "sha256:x",
            "properties": {}, "spec": None,
            "operations": {
                "get-echo": {"id": "/apis/echo/operations/get-echo", "method": "GET", "urlTemplate": "/echo"},
            },
        }
        payloads = to_operation_payloads(artifact)
        assert len(payloads) == 1
        op_id, payload = payloads[0]
        assert op_id == "get-echo"
        assert "id" not in payload["properties"]
        assert payload["properties"]["method"] == "GET"

    # Tests that resource_path generates correct API REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.apis import resource_path
        assert resource_path("echo-api") == "/apis/echo-api"

    # Tests that read_live fetches APIs and operations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.apis import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/apis": [{"name": "echo", "properties": {"displayName": "Echo"}}],
            "/apis/echo/operations": [{"name": "get-echo", "properties": {"method": "GET"}}],
        }.get(path, [])
        result = read_live(client)
        assert "api:echo" in result
        assert "get-echo" in result["api:echo"]["operations"]

    # Tests that _detect_spec_format identifies Swagger 2.0 JSON spec format.
    def test_detect_spec_format_swagger_json(self, tmp_path):
        from apy_ops.artifacts.apis import _detect_spec_format
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps({"swagger": "2.0", "info": {"title": "Test"}}))
        fmt, content = _detect_spec_format(str(spec))
        assert fmt == "swagger-json"

    # Tests that _detect_spec_format identifies OpenAPI 3.0 YAML spec format.
    def test_detect_spec_format_openapi_yaml(self, tmp_path):
        from apy_ops.artifacts.apis import _detect_spec_format
        spec = tmp_path / "spec.yaml"
        spec.write_text("openapi: '3.0.0'\ninfo:\n  title: Test\n")
        fmt, content = _detect_spec_format(str(spec))
        assert fmt == "openapi"

    # Tests that _detect_spec_format identifies WSDL spec format.
    def test_detect_spec_format_wsdl(self, tmp_path):
        from apy_ops.artifacts.apis import _detect_spec_format
        spec = tmp_path / "spec.wsdl"
        spec.write_text("<wsdl/>")
        fmt, _ = _detect_spec_format(str(spec))
        assert fmt == "wsdl"


# ===================================================================
# 5. Association modules
# ===================================================================

class TestProductGroups:
    # Tests that read_local parses product-group associations from groups.json.
    def test_read_local_with_groups_json(self, tmp_path):
        from apy_ops.artifacts.product_groups import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter", "displayName": "Starter",
        }))
        (prod_dir / "groups.json").write_text(json.dumps(["developers", "guests"]))
        result = read_local(str(tmp_path))
        assert "product_group:starter/developers" in result
        assert "product_group:starter/guests" in result

    # Tests that write_local saves product-group associations as groups.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.product_groups import write_local
        artifacts = {
            "product_group:starter/devs": _make_artifact("product_group", "starter/devs", {
                "productId": "starter", "groupId": "devs",
            }),
            "product_group:starter/admins": _make_artifact("product_group", "starter/admins", {
                "productId": "starter", "groupId": "admins",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "products" / "starter" / "groups.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data == ["admins", "devs"]  # sorted

    # Tests that to_rest_payload generates empty body for product-group association.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.product_groups import to_rest_payload
        artifact = _make_artifact("product_group", "s/d", {"productId": "s", "groupId": "d"})
        assert to_rest_payload(artifact) == {}

    # Tests that resource_path generates correct product-group REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.product_groups import resource_path
        assert resource_path("starter/developers") == "/products/starter/groups/developers"

    # Tests that read_live fetches product-group associations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.product_groups import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/products": [{"name": "starter"}],
            "/products/starter/groups": [{"name": "devs"}],
        }.get(path, [])
        result = read_live(client)
        assert "product_group:starter/devs" in result


class TestProductApis:
    # Tests that read_local parses product-api associations from apis.json.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.product_apis import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter", "displayName": "Starter",
        }))
        (prod_dir / "apis.json").write_text(json.dumps(["echo-api", "weather-api"]))
        result = read_local(str(tmp_path))
        assert "product_api:starter/echo-api" in result
        assert "product_api:starter/weather-api" in result

    # Tests that write_local saves product-api associations as apis.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.product_apis import write_local
        artifacts = {
            "product_api:starter/echo": _make_artifact("product_api", "starter/echo", {
                "productId": "starter", "apiId": "echo",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "products" / "starter" / "apis.json"
        assert path.is_file()
        assert json.loads(path.read_text()) == ["echo"]

    # Tests that to_rest_payload generates empty body for product-api association.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.product_apis import to_rest_payload
        artifact = _make_artifact("product_api", "s/a", {"productId": "s", "apiId": "a"})
        assert to_rest_payload(artifact) == {}

    # Tests that resource_path generates correct product-api REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.product_apis import resource_path
        assert resource_path("starter/echo") == "/products/starter/apis/echo"

    # Tests that read_live fetches product-api associations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.product_apis import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/products": [{"name": "starter"}],
            "/products/starter/apis": [{"name": "echo"}],
        }.get(path, [])
        result = read_live(client)
        assert "product_api:starter/echo" in result


class TestProductTags:
    # Tests that read_local parses product-tag associations from tags.json.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.product_tags import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter", "displayName": "Starter",
        }))
        (prod_dir / "tags.json").write_text(json.dumps(["env-prod"]))
        result = read_local(str(tmp_path))
        assert "product_tag:starter/env-prod" in result

    # Tests that write_local saves product-tag associations as tags.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.product_tags import write_local
        artifacts = {
            "product_tag:starter/t1": _make_artifact("product_tag", "starter/t1", {
                "productId": "starter", "tagId": "t1",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "products" / "starter" / "tags.json"
        assert json.loads(path.read_text()) == ["t1"]

    # Tests that to_rest_payload generates empty body for product-tag association.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.product_tags import to_rest_payload
        artifact = _make_artifact("product_tag", "s/t", {"productId": "s", "tagId": "t"})
        assert to_rest_payload(artifact) == {}

    # Tests that resource_path generates correct product-tag REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.product_tags import resource_path
        assert resource_path("starter/env-prod") == "/products/starter/tags/env-prod"

    # Tests that read_live fetches product-tag associations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.product_tags import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/products": [{"name": "starter"}],
            "/products/starter/tags": [{"name": "t1"}],
        }.get(path, [])
        result = read_live(client)
        assert "product_tag:starter/t1" in result


class TestGatewayApis:
    # Tests that read_local parses gateway-api associations from apis.json.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.gateway_apis import read_local
        gw_dir = tmp_path / "gateways" / "gw1"
        gw_dir.mkdir(parents=True)
        (gw_dir / "gatewayInformation.json").write_text(json.dumps({
            "id": "/gateways/gw1", "displayName": "GW1",
        }))
        (gw_dir / "apis.json").write_text(json.dumps(["echo-api"]))
        result = read_local(str(tmp_path))
        assert "gateway_api:gw1/echo-api" in result

    # Tests that write_local saves gateway-api associations as apis.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.gateway_apis import write_local
        artifacts = {
            "gateway_api:gw1/echo": _make_artifact("gateway_api", "gw1/echo", {
                "gatewayId": "gw1", "apiId": "echo",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "gateways" / "gw1" / "apis.json"
        assert json.loads(path.read_text()) == ["echo"]

    # Tests that to_rest_payload generates gateway-api REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.gateway_apis import to_rest_payload
        artifact = _make_artifact("gateway_api", "gw1/echo", {
            "gatewayId": "gw1", "apiId": "echo",
        })
        payload = to_rest_payload(artifact)
        assert payload == {"properties": {"provisioningState": "created"}}

    # Tests that resource_path generates correct gateway-api REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.gateway_apis import resource_path
        assert resource_path("gw1/echo") == "/gateways/gw1/apis/echo"

    # Tests that read_live fetches gateway-api associations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.gateway_apis import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/gateways": [{"name": "gw1"}],
            "/gateways/gw1/apis": [{"name": "echo"}],
        }.get(path, [])
        result = read_live(client)
        assert "gateway_api:gw1/echo" in result


class TestApiTags:
    # Tests that read_local parses api-tag associations from tags.json.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.api_tags import read_local
        api_dir = tmp_path / "apis" / "Echo_echo-api"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo-api", "displayName": "Echo",
        }))
        (api_dir / "tags.json").write_text(json.dumps(["env-prod"]))
        result = read_local(str(tmp_path))
        assert "api_tag:echo-api/env-prod" in result

    # Tests that write_local saves api-tag associations as tags.json.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.api_tags import write_local
        # Create the API directory first so _find_api_dir works
        api_dir = tmp_path / "apis" / "Echo_echo-api"
        api_dir.mkdir(parents=True)
        artifacts = {
            "api_tag:echo-api/t1": _make_artifact("api_tag", "echo-api/t1", {
                "apiId": "echo-api", "tagId": "t1",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = api_dir / "tags.json"
        assert json.loads(path.read_text()) == ["t1"]

    # Tests that to_rest_payload generates empty body for api-tag association.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.api_tags import to_rest_payload
        artifact = _make_artifact("api_tag", "echo/t1", {"apiId": "echo", "tagId": "t1"})
        assert to_rest_payload(artifact) == {}

    # Tests that resource_path generates correct api-tag REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.api_tags import resource_path
        assert resource_path("echo-api/env-prod") == "/apis/echo-api/tags/env-prod"

    # Tests that read_live fetches api-tag associations from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.api_tags import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/apis": [{"name": "echo"}],
            "/apis/echo/tags": [{"name": "t1"}],
        }.get(path, [])
        result = read_live(client)
        assert "api_tag:echo/t1" in result


class TestApiDiagnostics:
    # Tests that read_local parses api-diagnostic artifacts from diagnostics subdirectory.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.api_diagnostics import read_local
        api_dir = tmp_path / "apis" / "echo"
        diag_dir = api_dir / "diagnostics"
        diag_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo", "displayName": "Echo",
        }))
        (diag_dir / "appinsights.json").write_text(json.dumps({
            "id": "/apis/echo/diagnostics/appinsights", "loggerId": "/loggers/ai1",
        }))
        result = read_local(str(tmp_path))
        assert "api_diagnostic:echo/appinsights" in result

    # Tests that write_local saves api-diagnostic to diagnostics subdirectory.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.api_diagnostics import write_local
        api_dir = tmp_path / "apis" / "echo"
        api_dir.mkdir(parents=True)
        artifacts = {
            "api_diagnostic:echo/ai": _make_artifact("api_diagnostic", "echo/ai", {
                "loggerId": "/loggers/ai1",
            }),
        }
        write_local(str(tmp_path), artifacts)
        path = api_dir / "diagnostics" / "ai.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["id"] == "/apis/echo/diagnostics/ai"

    # Tests that to_rest_payload generates api-diagnostic REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.api_diagnostics import to_rest_payload
        artifact = _make_artifact("api_diagnostic", "echo/ai", {
            "id": "/apis/echo/diagnostics/ai", "loggerId": "/loggers/ai1",
        })
        payload = to_rest_payload(artifact)
        assert "id" not in payload["properties"]
        assert payload["properties"]["loggerId"] == "/loggers/ai1"

    # Tests that resource_path generates correct api-diagnostic REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.api_diagnostics import resource_path
        assert resource_path("echo/appinsights") == "/apis/echo/diagnostics/appinsights"

    # Tests that read_live fetches api-diagnostics from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.api_diagnostics import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/apis": [{"name": "echo"}],
            "/apis/echo/diagnostics": [{"name": "ai", "properties": {"loggerId": "/loggers/ai1"}}],
        }.get(path, [])
        result = read_live(client)
        assert "api_diagnostic:echo/ai" in result


# ===================================================================
# 6. Policy modules
# ===================================================================

class TestApiPolicies:
    # Tests that read_local parses api-level policy from policy.xml.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.api_policies import read_local
        api_dir = tmp_path / "apis" / "Echo_echo-api"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo-api", "displayName": "Echo",
        }))
        (api_dir / "policy.xml").write_text("<policies><inbound/></policies>")
        result = read_local(str(tmp_path))
        assert "api_policy:echo-api" in result
        assert result["api_policy:echo-api"]["properties"]["format"] == "rawxml"
        assert "<policies>" in result["api_policy:echo-api"]["properties"]["value"]

    # Tests that read_local returns empty dict when api-policy does not exist.
    def test_read_local_no_policy(self, tmp_path):
        from apy_ops.artifacts.api_policies import read_local
        api_dir = tmp_path / "apis" / "echo"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo", "displayName": "Echo",
        }))
        result = read_local(str(tmp_path))
        assert result == {}

    # Tests that write_local saves api-policy to policy.xml.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.api_policies import write_local
        api_dir = tmp_path / "apis" / "Echo_echo-api"
        api_dir.mkdir(parents=True)
        artifacts = {"api_policy:echo-api": _make_artifact("api_policy", "echo-api", {
            "format": "rawxml", "value": "<policies/>",
        })}
        write_local(str(tmp_path), artifacts)
        path = api_dir / "policy.xml"
        assert path.is_file()
        assert path.read_text() == "<policies/>"

    # Tests that to_rest_payload generates api-policy REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.api_policies import to_rest_payload
        artifact = _make_artifact("api_policy", "echo", {
            "format": "rawxml", "value": "<policies/>",
        })
        payload = to_rest_payload(artifact)
        assert payload == {"properties": {"format": "rawxml", "value": "<policies/>"}}

    # Tests that resource_path generates correct api-policy REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.api_policies import resource_path
        assert resource_path("echo-api") == "/apis/echo-api/policies/policy"

    # Tests that read_live fetches api-policies from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.api_policies import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/apis": [{"name": "echo"}],
        }.get(path, [])
        client.get.return_value = {"properties": {"format": "rawxml", "value": "<p/>"}}
        result = read_live(client)
        assert "api_policy:echo" in result


class TestProductPolicies:
    # Tests that read_local parses product-level policy from policy.xml.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.product_policies import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter", "displayName": "Starter",
        }))
        (prod_dir / "policy.xml").write_text("<policies><inbound/></policies>")
        result = read_local(str(tmp_path))
        assert "product_policy:starter" in result

    # Tests that read_local returns empty dict when product-policy does not exist.
    def test_read_local_no_policy(self, tmp_path):
        from apy_ops.artifacts.product_policies import read_local
        prod_dir = tmp_path / "products" / "starter"
        prod_dir.mkdir(parents=True)
        (prod_dir / "productInformation.json").write_text(json.dumps({
            "id": "/products/starter", "displayName": "Starter",
        }))
        assert read_local(str(tmp_path)) == {}

    # Tests that write_local saves product-policy to policy.xml.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.product_policies import write_local
        artifacts = {"product_policy:starter": _make_artifact("product_policy", "starter", {
            "format": "rawxml", "value": "<policies/>",
        })}
        write_local(str(tmp_path), artifacts)
        path = tmp_path / "products" / "starter" / "policy.xml"
        assert path.is_file()
        assert path.read_text() == "<policies/>"

    # Tests that to_rest_payload generates product-policy REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.product_policies import to_rest_payload
        artifact = _make_artifact("product_policy", "starter", {
            "format": "rawxml", "value": "<policies/>",
        })
        payload = to_rest_payload(artifact)
        assert payload == {"properties": {"format": "rawxml", "value": "<policies/>"}}

    # Tests that resource_path generates correct product-policy REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.product_policies import resource_path
        assert resource_path("starter") == "/products/starter/policies/policy"

    # Tests that read_live fetches product-policies from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.product_policies import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/products": [{"name": "starter"}],
        }.get(path, [])
        client.get.return_value = {"properties": {"format": "rawxml", "value": "<p/>"}}
        result = read_live(client)
        assert "product_policy:starter" in result


class TestApiOperationPolicies:
    # Tests that read_local parses operation-level policy from operation subdirectory.
    def test_read_local(self, tmp_path):
        from apy_ops.artifacts.api_operation_policies import read_local
        api_dir = tmp_path / "apis" / "echo"
        op_dir = api_dir / "get-echo"
        op_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo", "displayName": "Echo",
        }))
        (op_dir / "policy.xml").write_text("<policies><inbound/></policies>")
        result = read_local(str(tmp_path))
        assert "api_operation_policy:echo/get-echo" in result

    # Tests that read_local returns empty dict when api-operation-policy does not exist.
    def test_read_local_no_policy(self, tmp_path):
        from apy_ops.artifacts.api_operation_policies import read_local
        api_dir = tmp_path / "apis" / "echo"
        api_dir.mkdir(parents=True)
        (api_dir / "apiInformation.json").write_text(json.dumps({
            "id": "/apis/echo", "displayName": "Echo",
        }))
        assert read_local(str(tmp_path)) == {}

    # Tests that write_local saves api-operation-policy to operation subdirectory.
    def test_write_local(self, tmp_path):
        from apy_ops.artifacts.api_operation_policies import write_local
        api_dir = tmp_path / "apis" / "echo"
        api_dir.mkdir(parents=True)
        artifacts = {
            "api_operation_policy:echo/get-echo": _make_artifact(
                "api_operation_policy", "echo/get-echo",
                {"format": "rawxml", "value": "<policies/>"},
            ),
        }
        write_local(str(tmp_path), artifacts)
        path = api_dir / "get-echo" / "policy.xml"
        assert path.is_file()
        assert path.read_text() == "<policies/>"

    # Tests that to_rest_payload generates api-operation-policy REST API body.
    def test_to_rest_payload(self):
        from apy_ops.artifacts.api_operation_policies import to_rest_payload
        artifact = _make_artifact("api_operation_policy", "echo/get-echo", {
            "format": "rawxml", "value": "<policies/>",
        })
        payload = to_rest_payload(artifact)
        assert payload == {"properties": {"format": "rawxml", "value": "<policies/>"}}

    # Tests that resource_path generates correct api-operation-policy REST API path.
    def test_resource_path(self):
        from apy_ops.artifacts.api_operation_policies import resource_path
        assert resource_path("echo/get-echo") == "/apis/echo/operations/get-echo/policies/policy"

    # Tests that read_live fetches api-operation-policies from APIM REST API.
    def test_read_live(self):
        from apy_ops.artifacts.api_operation_policies import read_live
        client = MagicMock()
        client.list.side_effect = lambda path: {
            "/apis": [{"name": "echo"}],
            "/apis/echo/operations": [{"name": "get-echo"}],
        }.get(path, [])
        client.get.return_value = {"properties": {"format": "rawxml", "value": "<p/>"}}
        result = read_live(client)
        assert "api_operation_policy:echo/get-echo" in result
