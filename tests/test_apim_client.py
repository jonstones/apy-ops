"""Tests for ApimClient REST wrapper."""

from unittest.mock import patch, MagicMock
import pytest

from apy_ops.apim_client import ApimClient, API_VERSION


@pytest.fixture
def client():
    """Create an ApimClient with mocked credentials."""
    with patch("apy_ops.apim_client.DefaultAzureCredential") as mock_cred:
        mock_token = MagicMock()
        mock_token.token = "fake-token"
        mock_token.expires_on = 9999999999.0
        mock_cred.return_value.get_token.return_value = mock_token
        c = ApimClient("sub-1", "rg-1", "apim-1")
    return c


class TestInit:
    # Tests that base_url contains subscription, resource group, and service name.
    def test_base_url(self, client):
        assert "sub-1" in client.base_url
        assert "rg-1" in client.base_url
        assert "apim-1" in client.base_url

    # Tests that service principal credentials are created correctly.
    def test_service_principal_auth(self):
        with patch("apy_ops.apim_client.ClientSecretCredential") as mock_sp:
            c = ApimClient("s", "r", "a", client_id="cid", client_secret="sec", tenant_id="tid")
            mock_sp.assert_called_once_with("tid", "cid", "sec")

    # Tests that DefaultAzureCredential is used when no service principal is provided.
    def test_default_credential_when_no_sp(self):
        with patch("apy_ops.apim_client.DefaultAzureCredential") as mock_def:
            c = ApimClient("s", "r", "a")
            mock_def.assert_called_once()


class TestGetToken:
    # Tests that token is cached and not re-fetched until expiry.
    def test_get_token_caches(self, client):
        with patch.object(client, "_credential") as mock_cred:
            mock_token = MagicMock()
            mock_token.token = "tok1"
            mock_token.expires_on = 9999999999.0
            mock_cred.get_token.return_value = mock_token
            t1 = client._get_token()
            t2 = client._get_token()
            # Second call should use cache, not call credential again
            assert mock_cred.get_token.call_count == 1
            assert t1 == "tok1"
            assert t2 == "tok1"

    # Tests that token is refreshed when expired.
    def test_get_token_refreshes_when_expired(self, client):
        with patch.object(client, "_credential") as mock_cred:
            mock_token = MagicMock()
            mock_token.token = "tok1"
            mock_token.expires_on = 0  # already expired
            mock_cred.get_token.return_value = mock_token
            client._token = None
            client._token_expiry = 0
            client._get_token()
            assert mock_cred.get_token.call_count == 1


class TestGet:
    # Tests that GET request returns parsed JSON response.
    @patch("apy_ops.apim_client.requests.request")
    def test_get_returns_json(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "test", "properties": {}}
        mock_request.return_value = mock_resp
        result = client.get("/apis/test")
        assert result["name"] == "test"
        mock_resp.raise_for_status.assert_called_once()

    # Tests that GET request raises exception on HTTP error.
    @patch("apy_ops.apim_client.requests.request")
    def test_get_raises_on_error(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_request.return_value = mock_resp
        with pytest.raises(Exception, match="404"):
            client.get("/apis/nonexistent")


class TestList:
    # Tests that list returns items from the value array.
    @patch("apy_ops.apim_client.requests.get")
    def test_list_returns_items(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "value": [{"name": "a"}, {"name": "b"}],
        }
        mock_get.return_value = mock_resp
        result = client.list("/apis")
        assert len(result) == 2
        assert result[0]["name"] == "a"

    # Tests that list handles pagination through nextLink.
    @patch("apy_ops.apim_client.requests.get")
    def test_list_pagination(self, mock_get, client):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "value": [{"name": "a"}],
            "nextLink": "https://next-page",
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "value": [{"name": "b"}],
        }
        mock_get.side_effect = [page1, page2]
        result = client.list("/apis")
        assert len(result) == 2
        assert result[0]["name"] == "a"
        assert result[1]["name"] == "b"


class TestPut:
    # Tests that PUT request returns parsed JSON response.
    @patch("apy_ops.apim_client.requests.request")
    def test_put_returns_json(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"name": "test"}'
        mock_resp.json.return_value = {"name": "test"}
        mock_request.return_value = mock_resp
        result = client.put("/apis/test", {"properties": {}})
        assert result["name"] == "test"

    # Tests that PUT request returns None for 204 No Content response.
    @patch("apy_ops.apim_client.requests.request")
    def test_put_empty_content_returns_none(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.content = b""
        mock_request.return_value = mock_resp
        result = client.put("/apis/test", {"properties": {}})
        assert result is None


class TestDelete:
    # Tests that DELETE request succeeds without raising.
    @patch("apy_ops.apim_client.requests.delete")
    def test_delete_success(self, mock_delete, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_delete.return_value = mock_resp
        client.delete("/apis/test")  # should not raise

    # Tests that DELETE request handles 404 gracefully without raising.
    @patch("apy_ops.apim_client.requests.delete")
    def test_delete_404_is_ok(self, mock_delete, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_delete.return_value = mock_resp
        client.delete("/apis/already-gone")  # should not raise


class TestRetry:
    # Tests that client retries on 429 rate limit with exponential backoff.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_retry_on_429(self, mock_request, mock_sleep, client):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [rate_limited, success]
        result = client.get("/apis/test")
        assert result["ok"] is True
        mock_sleep.assert_called_once_with(1)
