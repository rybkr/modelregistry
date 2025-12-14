"""Code fetcher for downloading and accessing code repositories from multiple platforms.

This module provides functionality to download and access code repositories from
HuggingFace Spaces, GitHub, and GitLab. It handles URL parsing, platform detection,
repository snapshot downloading, and provides a unified RepoView interface for
accessing repository files regardless of the source platform.
"""

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
    """Parse a URL into hostname and path components.

    Args:
        url: URL to parse

    Returns:
        tuple: (hostname in lowercase, list of path components)
    """
    p = urlparse(url)
    return p.netloc.lower(), [x for x in p.path.strip("/").split("/") if x]


def _is_hf_space(host: str, parts: list[str]) -> bool:
    """Check if URL represents a HuggingFace Space.

    Args:
        host: URL hostname
        parts: URL path components

    Returns:
        bool: True if URL is a HuggingFace Space, False otherwise
    """
    return host == "huggingface.co" and len(parts) >= 3 and parts[0] == "spaces"


def _extract_rev(parts: list[str]) -> Optional[str]:
    """Extract revision (branch/tag/commit) from URL path components.

    Looks for revision indicators like "tree", "blob", or "resolve" in the
    path and returns the following component as the revision.

    Args:
        parts: URL path components

    Returns:
        Optional[str]: Revision identifier or None if not found
    """
    for i in range(len(parts) - 1):
        if parts[i] in {"tree", "blob", "resolve"}:
            return parts[i + 1]
    return None


class _HFSpaceFetcher(_BaseSnapshotFetcher):
    """Fetcher for Hugging Face Space repositories.

    Downloads HuggingFace Space repositories using snapshot_download and provides
    access through a RepoView interface. Filters files by pattern to download
    only relevant code files.
    """

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
    """A context manager for fetching and extracting GitHub repositories as tarballs.

    Downloads GitHub repositories as tarballs, extracts them, and provides
    access through a RepoView interface. Supports authentication via personal access tokens.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        ref: Optional[str],
        token: Optional[str] = None,
    ) -> None:
        """Initialize the GitHubCodeFetcher with repository details.

        Args:
            owner: The owner/organization of the GitHub repository
            repo: The name of the GitHub repository
            ref: The branch, tag, or commit to fetch (defaults to default branch)
            token: A GitHub personal access token for authentication (optional)
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        # Get default branch - pass token to avoid rate limiting
        self.ref = ref or GitHubClient().get_metadata(
            f"https://github.com/{owner}/{repo}", token=token
        ).get("default_branch", "main")
        self._tmp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self._root: Optional[Path] = None

    def __enter__(self) -> RepoView:
        """Enter context manager and download GitHub repository.

        Downloads the repository as a tarball, extracts it, and returns
        a RepoView for accessing the files.

        Returns:
            RepoView: View of the downloaded repository
        """
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
        """Exit context manager and clean up temporary resources.

        Args:
            exc_type: Exception type if an exception occurred
            exc_value: Exception instance if an exception occurred
            traceback: Traceback object if an exception occurred

        Returns:
            None
        """
        try:
            if self._tmp_dir:
                self._tmp_dir.cleanup()
        finally:
            self._tmp_dir = None
            self._root = None


class _GitLabCodeFetcher(AbstractContextManager[RepoView]):
    """A context manager for fetching and extracting GitLab repositories as a tar.gz.

    Downloads GitLab repositories as tar.gz archives, extracts them, and provides
    access through a RepoView interface. Supports authentication via personal access tokens.
    """

    def __init__(
        self,
        ns_name: str,
        ref: Optional[str],
        token: Optional[str] = None,
    ) -> None:
        """Initialize the GitLabCodeFetcher with repository details.

        Args:
            ns_name: The namespace/path of the GitLab repository (e.g., "group/sub/repo")
            ref: The branch, tag, or commit to fetch (defaults to default branch)
            token: A GitLab personal access token for authentication (optional)
        """
        self.ns_name = ns_name
        self.ref = ref or GitLabClient().get_metadata(
            f"https://gitlab.com/{ns_name}"
        ).get("default_branch", "main")
        self.token = token
        self._tmp_dir: Optional[tempfile.TemporaryDirectory[str]] = None
        self._root: Optional[Path] = None

    def __enter__(self) -> RepoView:
        """Enter context manager and download GitLab repository.

        Downloads the repository as a tar.gz archive, extracts it, and returns
        a RepoView for accessing the files.

        Returns:
            RepoView: View of the downloaded repository
        """
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
        """Exit context manager and clean up temporary resources.

        Args:
            exc_type: Exception type if an exception occurred
            exc_value: Exception instance if an exception occurred
            traceback: Traceback object if an exception occurred

        Returns:
            None
        """
        try:
            if self._tmp_dir:
                self._tmp_dir.cleanup()
        finally:
            self._tmp_dir = None
            self._root = None


def _extract_tarball(url: str, headers: dict[str, Any], dest: Path) -> None:
    """Download and extract a tarball archive to a destination directory.

    Downloads a tar.gz archive from the given URL and extracts it to the
    destination path. Handles HTTP errors and network exceptions.

    Args:
        url: URL to download the tarball from
        headers: HTTP headers to include in the request
        dest: Destination directory path for extraction

    Raises:
        AppError: If download fails (HTTP_ERROR) or network error occurs (NETWORK_ERROR)
    """
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
    """Find the top-level directory in an extracted archive.

    When archives are extracted, they typically create a single top-level
    directory containing all files. This function finds and returns that
    directory, or the root itself if no subdirectory exists.

    Args:
        root: Root directory to search for top-level subdirectory

    Returns:
        Path: Path to the top-level directory, or root if none found
    """
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return dirs[0] if dirs else root
