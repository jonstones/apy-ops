"""Azure API Management REST API client."""

from __future__ import annotations

import json
import time
from datetime import datetime
from functools import wraps
from typing import Any, Callable

import requests
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential, ClientSecretCredential

from apy_ops.exceptions import (
    ApimError,
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

API_VERSION = "2024-05-01"
MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # seconds


def _parse_error(response: requests.Response) -> dict[str, Any]:
    """Extract error details from Azure error response.

    Azure errors are typically in format:
    {
      "error": {
        "code": "ErrorCode",
        "message": "Error message",
        "target": "field name",
        "details": [...]
      }
    }

    Returns:
        Dict with keys: code, message, target, request_id. Missing keys are None.
    """
    request_id = response.headers.get("x-ms-request-id")

    try:
        data = response.json()
        error = data.get("error", {})
        return {
            "code": error.get("code"),
            "message": error.get("message"),
            "target": error.get("target"),
            "request_id": request_id,
        }
    except (ValueError, json.JSONDecodeError):
        # Fallback if response is not valid JSON
        return {
            "code": None,
            "message": response.text or f"HTTP {response.status_code}",
            "target": None,
            "request_id": request_id,
        }


def _should_retry(response: requests.Response, error_detail: dict[str, Any]) -> bool:
    """Determine if an error response warrants a retry.

    Args:
        response: The HTTP response object
        error_detail: Parsed error details from _parse_error()

    Returns:
        True if the error is transient and should be retried, False otherwise.
    """
    status = response.status_code

    # Always retry on 429 (rate limit)
    if status == 429:
        return True

    # Always retry on 412 (precondition failed/ETag mismatch)
    if status == 412:
        return True

    # Always retry on 5xx server errors
    if status >= 500:
        return True

    # Conditional retry on 409 (conflict)
    if status == 409:
        error_code = error_detail.get("code", "")
        # Only retry on specific transient conflict codes
        if "PessimisticConcurrencyConflict" in error_code or "Conflict" in error_code:
            return True
        return False

    # Conditional retry on 422 (unprocessable entity)
    if status == 422:
        error_code = error_detail.get("code", "")
        # Only retry on specific transient validation errors
        if "ManagementApiFailure" in error_code:
            return True
        return False

    # Don't retry on client errors (4xx except 429, 409, 412, 422)
    return False


def _parse_retry_after(response: requests.Response, default: int) -> int:
    """Parse Retry-After header from response.

    The Retry-After header can be:
    - An integer (seconds): "5"
    - An HTTP date (RFC 7231): "Wed, 21 Oct 2026 07:28:00 GMT"

    Args:
        response: The HTTP response object
        default: Default retry delay if header is missing or unparseable

    Returns:
        Number of seconds to wait before retrying
    """
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return default

    # Try parsing as integer (seconds)
    try:
        return int(retry_after)
    except ValueError:
        pass

    # Try parsing as HTTP date (RFC 7231)
    try:
        dt = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S %Z")
        delay = int((dt.timestamp() - time.time()))
        return max(1, delay)  # At least 1 second
    except (ValueError, AttributeError):
        pass

    # Fallback to default
    return default


def _create_exception(response: requests.Response, error_detail: dict[str, Any]) -> ApimError:
    """Create an appropriate exception instance for the error response.

    Args:
        response: The HTTP response object
        error_detail: Parsed error details from _parse_error()

    Returns:
        An ApimError instance (or appropriate subclass)
    """
    status = response.status_code
    error_code = error_detail.get("code")
    message = error_detail.get("message") or f"HTTP {status}"
    target = error_detail.get("target")
    request_id = error_detail.get("request_id")

    # Create base message
    full_message = message
    if error_code:
        full_message = f"{error_code}: {message}"

    # Map status codes to exception classes
    if status == 429:
        exc_class = ApimRateLimitError
    elif status == 409:
        exc_class = ApimConflictError
    elif status == 412:
        exc_class = ApimPreconditionFailedError
    elif status == 422:
        exc_class = ApimUnprocessableEntityError
    elif status >= 500:
        exc_class = ApimServerError
    elif status == 400:
        exc_class = ApimBadRequestError
    elif status == 401:
        exc_class = ApimUnauthorizedError
    elif status == 403:
        exc_class = ApimForbiddenError
    elif status == 404:
        exc_class = ApimNotFoundError
    else:
        exc_class = ApimError

    return exc_class(
        full_message,
        status_code=status,
        error_code=error_code,
        target=target,
        request_id=request_id,
        response=response,
    )


def _with_retry(func: Callable[..., requests.Response]) -> Callable[..., requests.Response]:
    """Decorator that adds retry logic with exponential backoff to a function.

    The decorated function should return a requests.Response object.
    On error, the decorator will:
    1. Parse the error details from the response
    2. Check if retry is appropriate via _should_retry()
    3. Sleep with Retry-After header or exponential backoff
    4. Retry up to MAX_RETRIES times
    5. On final failure, raise an ApimError

    Args:
        func: A function that returns requests.Response

    Returns:
        Wrapped function with retry logic
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> requests.Response:
        backoff = INITIAL_BACKOFF
        for attempt in range(MAX_RETRIES + 1):
            resp = func(*args, **kwargs)

            # Success - return immediately
            if resp.status_code < 400:
                return resp

            # Error - check if we should retry
            error_detail = _parse_error(resp)
            should_retry = _should_retry(resp, error_detail)

            if should_retry and attempt < MAX_RETRIES:
                # Calculate retry delay
                retry_delay = _parse_retry_after(resp, backoff)
                time.sleep(retry_delay)
                backoff *= 2
                continue

            # No retry or retries exhausted - raise exception
            raise _create_exception(resp, error_detail)

        # Unreachable, but satisfy type checker
        raise _create_exception(resp, error_detail)

    return wrapper


class ApimClient:
    """Thin wrapper around Azure APIM REST API with auth and retry."""

    def __init__(self, subscription_id: str, resource_group: str, service_name: str,
                 client_id: str | None = None, client_secret: str | None = None,
                 tenant_id: str | None = None) -> None:
        self.base_url = (
            f"https://management.azure.com/subscriptions/{subscription_id}"
            f"/resourceGroups/{resource_group}"
            f"/providers/Microsoft.ApiManagement/service/{service_name}"
        )
        credential: TokenCredential
        if client_id and client_secret and tenant_id:
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        else:
            credential = DefaultAzureCredential()
        self._credential = credential
        self._token: str | None = None
        self._token_expiry: float = 0

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry - 60:
            return self._token
        token = self._credential.get_token("https://management.azure.com/.default")
        self._token = token.token
        self._token_expiry = token.expires_on
        return self._token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    @_with_retry
    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> requests.Response:
        """Make an HTTP request with retry logic via decorator.

        Args:
            method: HTTP method (GET, PUT, DELETE, etc.)
            path: API path relative to base_url
            body: Optional request body for PUT/POST

        Returns:
            The response object (or raises ApimError on failure after retries)

        Raises:
            ApimError: On HTTP error after exhausting retries
        """
        url = f"{self.base_url}{path}"
        params = {"api-version": API_VERSION}
        return requests.request(
            method, url, headers=self._headers(),
            json=body, params=params, timeout=120,
        )

    def get(self, path: str) -> dict[str, Any]:
        """GET request returning parsed JSON.

        Args:
            path: API path relative to base_url

        Returns:
            Parsed JSON response

        Raises:
            ApimError: On HTTP error
        """
        resp = self._request("GET", path)
        return resp.json()

    @_with_retry
    def _request_raw(self, url: str, params: dict[str, str]) -> requests.Response:
        """Make a raw HTTP GET request with retry logic via decorator.

        This is used by list() for pagination to support arbitrary URLs (nextLink).

        Args:
            url: Full URL (not relative path)
            params: Query parameters

        Returns:
            The response object (or raises ApimError on failure after retries)

        Raises:
            ApimError: On HTTP error after exhausting retries
        """
        return requests.get(
            url, headers=self._headers(), params=params, timeout=120,
        )

    def list(self, path: str) -> list[dict[str, Any]]:
        """GET with pagination support. Returns list of all items.

        Args:
            path: API path relative to base_url

        Returns:
            List of all items from all pages

        Raises:
            ApimError: On HTTP error
        """
        items: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}{path}"
        params: dict[str, str] = {"api-version": API_VERSION}
        while url:
            resp = self._request_raw(url, params)
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("nextLink")
            params = {}  # nextLink includes query params
        return items

    def put(self, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
        """PUT request returning parsed JSON (or None for 204 No Content).

        Args:
            path: API path relative to base_url
            body: Request body

        Returns:
            Parsed JSON response, or None if response is empty

        Raises:
            ApimError: On HTTP error
        """
        resp = self._request("PUT", path, body)
        return resp.json() if resp.content else None

    def delete(self, path: str) -> None:
        """DELETE request. 404 (Not Found) is treated as success.

        Args:
            path: API path relative to base_url

        Raises:
            ApimError: On HTTP error (except 404)
        """
        try:
            self._request("DELETE", path)
        except ApimNotFoundError:
            # 404 on delete is fine — resource already gone
            pass
