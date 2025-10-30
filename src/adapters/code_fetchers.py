from __future__ import annotations

import io
import tarfile
import tempfile
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, ContextManager, Iterable, Optional
from urllib.parse import quote_plus, urlparse

import requests

from adapters.client import GitHubClient, GitLabClient
from adapters.model_fetchers import _BaseSnapshotFetcher
from adapters.repo_view import RepoView
from errors import (
    HTTP_ERROR,
    NETWORK_ERROR,
    UNSUPPORTED_URL,
    AppError,
)

SPACE_ALLOW = ["app.*", "requirements*.txt", "runtime.txt", "*.py", "README.*"]


# NOTE: Might want to explore fast file retrieval especially for large files


def open_codebase(
    url: str,
    *,
    ref: Optional[str] = None,
    token: Optional[str] = None,
    allow_patterns: Optional[Iterable[str]] = None,
) -> ContextManager[RepoView]:
    """Open a codebase and return a context manager for interacting with it.

    This function determines the type of codebase (e.g., GitHub, GitLab, Hugging Face
    Space) based on the provided URL and returns an appropriate context manager for
    interacting with the codebase. The context manager provides access to the
    repository's files and metadata.

    Args:
        url (str): The URL of the codebase to open.
            Defaults to False.
        ref (Optional[str]): The branch, tag, or commit to fetch. Defaults to None.
        token (Optional[str]): An optional authentication token for private
            repositories.

    Returns:
        ContextManager[RepoView]: A context manager for interacting with the codebase.

    Raises:
        AppError: If the URL is unsupported or invalid.
    """
    host, parts = _parse(url)
    if _is_hf_space(host, parts):
        return _HFSpaceFetcher(
            f"{parts[1]}/{parts[2]}", _extract_rev(parts), allow_patterns=allow_patterns
        )
    if host.endswith("github.com"):
        owner, repo = parts[0], parts[1]
        revision = _extract_rev(parts) or ref
        return _GitHubCodeFetcher(owner, repo, revision, token)
    if host.endswith("gitlab.com"):
        ns_name = "/".join(parts)
        revision = _extract_rev(parts) or ref
        return _GitLabCodeFetcher(ns_name, revision, token)

    raise AppError(UNSUPPORTED_URL, "Unsupported codebase url link")


def _parse(url: str) -> tuple[str, list[str]]:
    p = urlparse(url)
    return p.netloc.lower(), [x for x in p.path.strip("/").split("/") if x]


def _is_hf_space(host: str, parts: list[str]) -> bool:
    return host == "huggingface.co" and len(parts) >= 3 and parts[0] == "spaces"


def _extract_rev(parts: list[str]) -> Optional[str]:
    for i in range(len(parts) - 1):
        if parts[i] in {"tree", "blob", "resolve"}:
            return parts[i + 1]
    return None


class _HFSpaceFetcher(_BaseSnapshotFetcher):
    """Fetcher for Hugging Face Space repositories."""

    def __init__(
        self,
        repo_id: str,
        revision: Optional[str],
        allow_patterns: Optional[Iterable[str]] = None,
        use_shared_cache: bool = True,
    ) -> None:
        """Initialize the space fetcher with repository details.

        Args:
            repo_id (str): The ID of the space repository to fetch.
            revision (Optional[str]):
                The specific revision of the space repository to fetch.
            allow_patterns (Optional[Iterable[str]]): Patterns of files to allow
                during fetching. Defaults to SPACE_ALLOW.
            use_shared_cache (bool): Whether to use a shared cache for the snapshot.
                Defaults to True.
        """
        allow_patterns = allow_patterns or SPACE_ALLOW
        super().__init__(repo_id, "space", revision, allow_patterns, use_shared_cache)


class _GitHubCodeFetcher(AbstractContextManager[RepoView]):
    """A context manager for fetching and extracting GitHub repositories as tarballs."""

    def __init__(
        self,
        owner: str,
        repo: str,
        ref: Optional[str],
        token: Optional[str] = None,
    ) -> None:
        """Initialize the GitHubCodeFetcher with repository details.

        Args:
            owner (str): The owner of the GitHub repository.
            repo (str): The name of the GitHub repository.
            ref (Optional[str]): The branch, tag, or commit to fetch.
                Defaults to "main".
            token (Optional[str]): A GitHub personal access token for authentication.
        """
        self.owner = owner
        self.repo = repo
        self.ref = ref or GitHubClient().get_metadata(
            f"https://github.com/{owner}/{repo}"
        ).get("default_branch", "main")
        self.token = token
        self._tmp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self._root: Optional[Path] = None

    def __enter__(self) -> RepoView:
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="mac")
        root = Path(self._tmp_dir.name)

        url = (
            f"https://api.github.com/repos/{self.owner}/{self.repo}/tarball/{self.ref}"
        )
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        _extract_tarball(url, headers, root)
        self._root = _top_dir(root)
        return RepoView(self._root)

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> None:
        try:
            if self._tmp_dir:
                self._tmp_dir.cleanup()
        finally:
            self._tmp_dir = None
            self._root = None


class _GitLabCodeFetcher(AbstractContextManager[RepoView]):
    """A context manager for fetching and extracting GitLab repositories as a tar.gz."""

    def __init__(
        self,
        ns_name: str,
        ref: Optional[str],
        token: Optional[str] = None,
    ) -> None:
        """Initialize the GitLabCodeFetcher with repository details.

        Args:
            ns_name (str): The namespace of the GitHub repository.
            ref (Optional[str]): The branch, tag, or commit to fetch.
                Defaults to "main".
            token (Optional[str]): A GitLab personal access token for authentication.
        """
        self.ns_name = ns_name
        self.ref = ref or GitLabClient().get_metadata(
            f"https://gitlab.com/{ns_name}"
        ).get("default_branch", "main")
        self.token = token
        self._tmp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self._root: Optional[Path] = None

    def __enter__(self) -> RepoView:
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="mac_")
        root = Path(self._tmp_dir.name)

        url = (
            f"https://gitlab.com/api/v4/projects/{quote_plus(self.ns_name)}"
            f"/repository/archive.tar.gz?sha={self.ref}"
        )
        headers = {}
        if self.token:
            headers["PRIVATE-TOKEN"] = self.token

        _extract_tarball(url, headers, root)
        self._root = _top_dir(root)
        return RepoView(self._root)

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> None:
        try:
            if self._tmp_dir:
                self._tmp_dir.cleanup()
        finally:
            self._tmp_dir = None
            self._root = None


def _extract_tarball(url: str, headers: dict[str, Any], dest: Path) -> None:
    try:
        response = requests.get(url, headers=headers, allow_redirects=True)
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        if response.status_code == 404:
            raise AppError(
                HTTP_ERROR,
                "Specified repo, branch or tag does not exist",
                context={"url": url},
            )
        raise AppError(
            HTTP_ERROR,
            f"HTTP {response.status_code} for tarball.",
            context={"url": url},
        )
    except requests.RequestException as e:
        raise AppError(
            NETWORK_ERROR,
            "Network error fetching tarball.",
            cause=e,
            context={"url": url},
        )

    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:
            tf.extractall(dest)


def _top_dir(root: Path) -> Path:
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return dirs[0] if dirs else root
