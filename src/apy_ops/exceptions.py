"""Custom exception hierarchy for APIM client errors."""

from __future__ import annotations


class ApimError(Exception):
    """Base exception for APIM API errors.

    Attributes:
        status_code: HTTP status code from the API response
        error_code: Error code from the Azure error response (e.g., "Conflict", "Unauthorized")
        message: Human-readable error message
        target: The field or resource that caused the error
        request_id: Azure request ID (x-ms-request-id header) for support tickets
        response: The full response object
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
        target: str | None = None,
        request_id: str | None = None,
        response: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.target = target
        self.request_id = request_id
        self.response = response

    def __repr__(self) -> str:
        parts = [f"status_code={self.status_code}"]
        if self.error_code:
            parts.append(f"error_code={self.error_code!r}")
        if self.request_id:
            parts.append(f"request_id={self.request_id!r}")
        return f"{self.__class__.__name__}({self.message!r}, {', '.join(parts)})"


class ApimTransientError(ApimError):
    """Transient APIM errors that can be retried."""

    pass


class ApimPermanentError(ApimError):
    """Permanent APIM errors that should not be retried."""

    pass


# Transient errors (retryable)
class ApimRateLimitError(ApimTransientError):
    """429 Too Many Requests - Rate limit exceeded."""

    pass


class ApimConflictError(ApimTransientError):
    """409 Conflict - Transient conflict (e.g., pessimistic concurrency)."""

    pass


class ApimPreconditionFailedError(ApimTransientError):
    """412 Precondition Failed - ETag mismatch, retry expected."""

    pass


class ApimUnprocessableEntityError(ApimTransientError):
    """422 Unprocessable Entity - Transient validation error."""

    pass


class ApimServerError(ApimTransientError):
    """5xx Server Error - Transient server-side issue."""

    pass


# Permanent errors (non-retryable)
class ApimBadRequestError(ApimPermanentError):
    """400 Bad Request - Invalid request format."""

    pass


class ApimUnauthorizedError(ApimPermanentError):
    """401 Unauthorized - Authentication failed."""

    pass


class ApimForbiddenError(ApimPermanentError):
    """403 Forbidden - Insufficient permissions."""

    pass


class ApimNotFoundError(ApimPermanentError):
    """404 Not Found - Resource does not exist."""

    pass
