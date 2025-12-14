"""Error handling and exception classes for the Model Registry.

This module provides structured error handling with custom exception types
and error codes. It includes utilities for converting HTTP responses from
external APIs (like HuggingFace) into structured application errors with
appropriate error codes and sanitized context information.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

NETWORK_ERROR = "NETWORK_ERROR"
RATE_LIMIT = "RATE_LIMIT"
AUTH_ERROR = "AUTH_ERROR"
NOT_FOUND = "NOT_FOUND"
SERVER_ERROR = "SERVER_ERROR"
HTTP_ERROR = "HTTP_ERROR"
SCHEMA_ERROR = "SCHEMA_ERROR"
UNSUPPORTED_URL = "UNSUPPORTED_URL"
INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class AppError(Exception):
    """A custom exception class for application-specific errors.

    This exception provides structured error information including error codes,
    messages, optional underlying causes, and contextual data. Sensitive fields
    like authorization tokens are automatically filtered from string representations.

    Attributes:
        code (str): A short, stable error code representing the type of error
            (e.g., NETWORK_ERROR, RATE_LIMIT, AUTH_ERROR)
        message (str): A human-readable error message describing the error
        cause (Optional[BaseException]): The underlying exception that caused
            this error, if any
        context (Optional[dict[str, Any]]): Additional context about the error,
            such as request details, URLs, or response data
    """

    code: str
    message: str
    cause: Optional[BaseException] = None
    context: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        """Return a string representation of the error.

        Formats the error as "CODE: message" with optional context information.
        Automatically filters sensitive fields (authorization, api_key) from
        the context to prevent credential leakage in logs.

        Returns:
            str: Formatted error string with code, message, and sanitized context
        """
        base = f"{self.code}: {self.message}"
        if self.context:
            safe_ctx = {
                k: v
                for k, v in self.context.items()
                if k.lower() not in {"authorization", "api_key"}
            }
            base += f" | ctx={safe_ctx}"
        return base


def http_error_from_hf_response(
    *,
    url: str,
    status: int,
    body: Optional[str] = None,
    headers: Optional[dict[str, Any]] = None,
) -> AppError:
    """Create an AppError instance from an HTTP response from the Hugging Face API.

    Converts HTTP error responses from the HuggingFace API into structured
    AppError instances with appropriate error codes based on status codes.
    Automatically extracts request IDs from headers and truncates response
    bodies for safe logging.

    Args:
        url: The URL of the API request that failed
        status: The HTTP status code of the response
        body: The response body, if available (will be truncated to 300 chars)
        headers: The response headers, if available (used to extract request IDs)

    Returns:
        AppError: Structured error with appropriate code:
            - RATE_LIMIT for 429 status
            - AUTH_ERROR for 401/403 status
            - NOT_FOUND for 404 status
            - SERVER_ERROR for 5xx status
            - HTTP_ERROR for other 4xx status codes
    """
    snippet = (body or "").strip().replace("\n", " ")
    if len(snippet) > 300:
        snippet = snippet[:300] + "…"

    req_id = None
    if headers:
        for k in ("x-request-id", "x-amzn-requestid"):
            if k in headers:
                req_id = headers.get(k)

    ctx: dict[str, Any] = {"url": url, "status": status}
    if req_id:
        ctx["request_id"] = req_id
    if snippet:
        ctx["body"] = snippet

    if status == 429:
        code = RATE_LIMIT
        msg = "Hugging Face API rate limit exceeded (429)."
    elif status in (401, 403):
        code = AUTH_ERROR
        msg = "Unauthorized or forbidden when calling Hugging Face API."
    elif status == 404:
        code = NOT_FOUND
        msg = "Resource not found on Hugging Face API."
    elif 500 <= status <= 599:
        code = SERVER_ERROR
        msg = "Hugging Face API server error."
    elif 400 <= status <= 499:
        code = HTTP_ERROR
        msg = f"Client error from Hugging Face API (HTTP {status})."
    else:
        code = HTTP_ERROR
        msg = f"Unexpected HTTP status from Hugging Face API (HTTP {status})."

    return AppError(code=code, message=msg, cause=None, context=ctx)
