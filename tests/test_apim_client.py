"""Tests for ApimClient REST wrapper."""

from unittest.mock import patch, MagicMock
import pytest

from apy_ops.apim_client import ApimClient, API_VERSION
from apy_ops.exceptions import (
    ApimError,
    ApimTransientError,
    ApimPermanentError,
    ApimRateLimitError,
    ApimConflictError,
    ApimPreconditionFailedError,
    ApimUnprocessableEntityError,
    ApimServerError,
    ApimBadRequestError,
    ApimUnauthorizedError,
    ApimForbiddenError,
    ApimNotFoundError,
)


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

    # Tests that GET request raises ApimNotFoundError on 404.
    @patch("apy_ops.apim_client.requests.request")
    def test_get_raises_on_404(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.headers = {}
        mock_resp.json.side_effect = ValueError()  # No error body
        mock_resp.text = ""
        mock_request.return_value = mock_resp
        with pytest.raises(ApimNotFoundError):
            client.get("/apis/nonexistent")

    # Tests that GET request raises ApimBadRequestError on 400.
    @patch("apy_ops.apim_client.requests.request")
    def test_get_raises_on_400(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.headers = {}
        mock_resp.json.return_value = {
            "error": {
                "code": "InvalidRequest",
                "message": "Bad request"
            }
        }
        mock_request.return_value = mock_resp
        with pytest.raises(ApimBadRequestError):
            client.get("/apis/test")


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
    @patch("apy_ops.apim_client.requests.request")
    def test_delete_success(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_request.return_value = mock_resp
        client.delete("/apis/test")  # should not raise

    # Tests that DELETE request handles 404 gracefully without raising (tested above in TestDeleteHandlesNotFound)
    # Kept for backward compatibility with test name
    @patch("apy_ops.apim_client.requests.request")
    def test_delete_404_is_ok_deprecated(self, mock_request, client):
        """This test is deprecated - use TestDeleteHandlesNotFound.test_delete_404_is_ok instead."""
        pass


class TestExceptionHierarchy:
    # Tests that exception hierarchy is correct.
    def test_apim_error_base_class(self):
        exc = ApimError("test", status_code=400)
        assert isinstance(exc, Exception)
        assert exc.status_code == 400
        assert exc.message == "test"

    # Tests that transient errors inherit from ApimTransientError.
    def test_transient_error_types(self):
        for exc_class in [ApimRateLimitError, ApimConflictError, ApimPreconditionFailedError,
                          ApimUnprocessableEntityError, ApimServerError]:
            exc = exc_class("test", status_code=429)
            assert isinstance(exc, ApimTransientError)
            assert isinstance(exc, ApimError)

    # Tests that permanent errors inherit from ApimPermanentError.
    def test_permanent_error_types(self):
        for exc_class in [ApimBadRequestError, ApimUnauthorizedError, ApimForbiddenError, ApimNotFoundError]:
            exc = exc_class("test", status_code=400)
            assert isinstance(exc, ApimPermanentError)
            assert isinstance(exc, ApimError)

    # Tests exception attributes are preserved.
    def test_exception_attributes(self):
        exc = ApimConflictError("Conflict detected", status_code=409, error_code="PessimisticConcurrencyConflict",
                               target="api.properties.path", request_id="req-123")
        assert exc.message == "Conflict detected"
        assert exc.status_code == 409
        assert exc.error_code == "PessimisticConcurrencyConflict"
        assert exc.target == "api.properties.path"
        assert exc.request_id == "req-123"


class TestErrorParsing:
    # Tests parsing Azure error format with all fields.
    @patch("apy_ops.apim_client.requests.request")
    def test_parse_error_azure_format(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 409
        mock_resp.headers = {"x-ms-request-id": "req-456"}
        mock_resp.json.return_value = {
            "error": {
                "code": "Conflict",
                "message": "Resource conflict",
                "target": "api.properties.path"
            }
        }
        mock_request.return_value = mock_resp
        with pytest.raises(ApimConflictError) as exc_info:
            client.get("/apis/test")
        exc = exc_info.value
        assert exc.error_code == "Conflict"
        assert exc.request_id == "req-456"
        assert "Resource conflict" in exc.message

    # Tests fallback when response is not valid JSON.
    @patch("apy_ops.apim_client.requests.request")
    def test_parse_error_malformed_json(self, mock_request, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.headers = {"x-ms-request-id": "req-789"}
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_resp.text = "Internal Server Error"
        mock_request.return_value = mock_resp
        with pytest.raises(ApimServerError) as exc_info:
            client.get("/apis/test")
        exc = exc_info.value
        assert "Internal Server Error" in exc.message


class TestShouldRetry:
    # Tests retry decision on 429 (always retry).
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_should_retry_on_429(self, mock_request, mock_sleep, client):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}
        rate_limited.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [rate_limited, success]
        result = client.get("/apis/test")
        assert result["ok"] is True
        assert mock_sleep.call_count == 1

    # Tests conditional retry on 409 with transient error code.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_should_retry_on_409_with_conflict_error_code(self, mock_request, mock_sleep, client):
        conflict = MagicMock()
        conflict.status_code = 409
        conflict.headers = {}
        conflict.json.return_value = {"error": {"code": "PessimisticConcurrencyConflict"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [conflict, success]
        result = client.get("/apis/test")
        assert result["ok"] is True
        assert mock_sleep.call_count == 1

    # Tests no retry on 409 with non-transient error code.
    @patch("apy_ops.apim_client.requests.request")
    def test_should_not_retry_on_409_with_permanent_error_code(self, mock_request, client):
        conflict = MagicMock()
        conflict.status_code = 409
        conflict.headers = {}
        conflict.json.return_value = {"error": {"code": "ResourceConflict", "message": "API already exists"}}
        mock_request.return_value = conflict
        with pytest.raises(ApimConflictError):
            client.get("/apis/test")

    # Tests retry on 412 (always retry).
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_should_retry_on_412(self, mock_request, mock_sleep, client):
        precond_failed = MagicMock()
        precond_failed.status_code = 412
        precond_failed.headers = {}
        precond_failed.json.return_value = {"error": {"code": "PreconditionFailed"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [precond_failed, success]
        result = client.get("/apis/test")
        assert result["ok"] is True

    # Tests retry on 500 server error (always retry).
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_should_retry_on_500(self, mock_request, mock_sleep, client):
        server_error = MagicMock()
        server_error.status_code = 500
        server_error.headers = {}
        server_error.json.side_effect = ValueError()
        server_error.text = "Internal Server Error"
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [server_error, success]
        result = client.get("/apis/test")
        assert result["ok"] is True

    # Tests no retry on 400 bad request.
    @patch("apy_ops.apim_client.requests.request")
    def test_should_not_retry_on_400(self, mock_request, client):
        bad_request = MagicMock()
        bad_request.status_code = 400
        bad_request.headers = {}
        bad_request.json.return_value = {"error": {"code": "InvalidRequest"}}
        mock_request.return_value = bad_request
        with pytest.raises(ApimBadRequestError):
            client.get("/apis/test")


class TestRetryAfterParsing:
    # Tests parsing Retry-After as integer seconds.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_parse_retry_after_integer(self, mock_request, mock_sleep, client):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "3"}
        rate_limited.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [rate_limited, success]
        client.get("/apis/test")
        # Should sleep for exactly 3 seconds (from header)
        mock_sleep.assert_called_once_with(3)

    # Tests exponential backoff when no Retry-After header.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_exponential_backoff(self, mock_request, mock_sleep, client):
        rate_limited_1 = MagicMock()
        rate_limited_1.status_code = 429
        rate_limited_1.headers = {}  # No Retry-After
        rate_limited_1.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        rate_limited_2 = MagicMock()
        rate_limited_2.status_code = 429
        rate_limited_2.headers = {}
        rate_limited_2.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [rate_limited_1, rate_limited_2, success]
        client.get("/apis/test")
        # Backoff should be 1s, then 2s (doubled)
        assert mock_sleep.call_count == 2
        calls = mock_sleep.call_args_list
        assert calls[0][0][0] == 1  # First retry: 1s
        assert calls[1][0][0] == 2  # Second retry: 2s


class TestRetryExhaustion:
    # Tests that exhausted retries raise exception.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_exhausted_retries_raises(self, mock_request, mock_sleep, client):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}
        rate_limited.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        mock_request.return_value = rate_limited
        with pytest.raises(ApimRateLimitError):
            client.get("/apis/test")
        # Should retry MAX_RETRIES (5) times, total attempts = 6
        assert mock_request.call_count == 6
        # Should sleep MAX_RETRIES (5) times
        assert mock_sleep.call_count == 5


class TestDeleteHandlesNotFound:
    # Tests that DELETE 404 is successful.
    @patch("apy_ops.apim_client.requests.request")
    def test_delete_404_is_ok(self, mock_request, client):
        not_found = MagicMock()
        not_found.status_code = 404
        not_found.headers = {}
        not_found.json.side_effect = ValueError()
        not_found.text = ""
        mock_request.return_value = not_found
        # Should not raise
        client.delete("/apis/nonexistent")

    # Tests that DELETE 500 raises exception.
    @patch("apy_ops.apim_client.requests.request")
    def test_delete_500_raises(self, mock_request, client):
        server_error = MagicMock()
        server_error.status_code = 500
        server_error.headers = {}
        server_error.json.side_effect = ValueError()
        server_error.text = "Internal Server Error"
        mock_request.return_value = server_error
        with pytest.raises(ApimServerError):
            client.delete("/apis/test")


class TestRetry:
    # Tests that client retries on 429 rate limit with exponential backoff.
    @patch("apy_ops.apim_client.time.sleep")
    @patch("apy_ops.apim_client.requests.request")
    def test_retry_on_429(self, mock_request, mock_sleep, client):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "1"}
        rate_limited.json.return_value = {"error": {"code": "RateLimitExceeded"}}
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}
        mock_request.side_effect = [rate_limited, success]
        result = client.get("/apis/test")
        assert result["ok"] is True
        mock_sleep.assert_called_once_with(1)
