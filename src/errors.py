from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Canonical error codes (keep short & stable)
NETWORK_ERROR = "NETWORK_ERROR"  # DNS, connect, TLS, timeout
RATE_LIMIT = "RATE_LIMIT"  # 429
AUTH_ERROR = "AUTH_ERROR"  # 401/403
NOT_FOUND = "NOT_FOUND"  # 404
SERVER_ERROR = "SERVER_ERROR"  # 5xx
HTTP_ERROR = "HTTP_ERROR"  # other 4xx
SCHEMA_ERROR = "SCHEMA_ERROR"  # JSON/schema parsing/validation
UNSUPPORTED_URL = "UNSUPPORTED_URL"  # host/type we don't handle
INTERNAL_ERROR = "INTERNAL_ERROR"  # unexpected bug


@dataclass
class AppError(Exception):
    """A custom exception class for application-specific errors.

    Attributes:
        code (str): A short, stable error code representing the type of error.
        message (str): A human-readable error message.
        cause (Optional[BaseException]): The underlying exception that caused
            this error, if any.
        context (Optional[dict[str, Any]]): Additional context about the error,
            such as request details.
    """

    code: str
    message: str
    cause: Optional[BaseException] = None
    context: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        """Return a string representation of the error.

        Returns:
            str: A string representation of the error.
        """
        base = f"{self.code}: {self.message}"
        if self.context:
            # keep it short; avoid leaking secrets
            safe = {
                k: v
                for k, v in self.context.items()
                if k.lower() not in {"authorization", "api_key"}
            }
            base += f" | ctx={safe}"
        return base


def http_error_from_hf_response(
    *,
    url: str,
    status: int,
    body: Optional[str] = None,
    headers: Optional[dict[str, Any]] = None,
) -> AppError:
    """Create an AppError instance from an HTTP response from the Hugging Face API.

    Args:
        url (str): The URL of the API request.
        status (int): The HTTP status code of the response.
        body (Optional[str]): The body of the response, if available.
        headers (Optional[dict[str, Any]]): The headers of the response,
            if available.

    Returns:
        AppError: An instance of AppError representing the HTTP error.

    Raises:
        AppError: If the HTTP status code indicates an error.
    """
    # Trim noisy bodies
    snippet = (body or "").strip().replace("\n", " ")
    if len(snippet) > 300:
        snippet = snippet[:300] + "…"

    # Try to extract a correlation/request id if HF sent one
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
