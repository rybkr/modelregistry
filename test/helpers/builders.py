"""Builders and factories for creating test doubles and mock objects."""

import io
import json
import tarfile
from typing import Any, Optional

import requests


def make_response(
    status: int,
    body: Optional[Any] = None,
    text: str = "",
    url: str = "https://huggingface.co/api/models/test-repo",
    headers: Optional[dict[str, Any]] = None,
) -> requests.Response:
    """Create a mock HTTP response object with the given status, body, text, and URL.

    Args:
        status (int): The HTTP status code for the response.
        body (Optional[Any])): The JSON body of the response. Defaults to None.
        text (str): The plain text content of the response. Defaults to an empty string.
        url (str): The URL associated with the response. Defaults to a test URL.
        headers (Optional[dict[str, Any]]): Optional headers to add to the response.

    Returns:
        requests.Response: A mock HTTP response object with the specified attributes.
    """
    response = requests.Response()
    response.status_code = status
    response.url = url
    if body is not None:
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
    else:
        response._content = text.encode()

    if headers:
        response.headers.update(headers)
    return response


def build_tgz(files: dict[str, bytes]) -> bytes:
    """Create a tar.gz archive with files in a top-level folder.

    This mimics the structure of GitHub/GitLab repository archives.

    Args:
        files (dict[str, bytes]): Mapping of file paths to file contents.

    Returns:
        bytes: The tar.gz archive as bytes.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for rel, data in files.items():
            data_io = io.BytesIO(data)
            info = tarfile.TarInfo(name=f"top/{rel}")
            info.size = len(data)
            tf.addfile(info, data_io)
    return buf.getvalue()
