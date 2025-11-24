import time
from typing import Any, Optional
from urllib.parse import quote_plus, urlparse

import requests

from errors import SCHEMA_ERROR, AppError, http_error_from_hf_response


class _Client:
    """A base client for interacting with the API metadata.

    Attributes:
        base_url (str): The base URL for the API.
    """

    def __init__(self, base_url: str):
        """Initialize the Client with a base URL.

        Args:
            base_url (str): The base URL for the API.
        """
        self.base_url = base_url.strip("/")

    def _get_json(
        self,
        path: str,
        retries: int,
        backoff: float = 2.0,
        headers: dict[str, Any] = {},
    ) -> Any:
        """Perform a GET request to the specified path and return the JSON response.

        Args:
            path (str): The API endpoint path.
            retries (Optional[int]): The number of retry attempts for failed requests.
                Defaults to 0.
            backoff (Optional[int]): The backoff multiplier for retry delays.
                Defaults to 2.

        Returns:
            Any: The JSON response from the API.

        Raises:
            AppError: If the response is not successful or the retries are exhausted.
        """
        url = self.base_url + path

        for attempt in range(retries + 1):
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError:
                if response.status_code >= 500 and attempt < retries:
                    wait_time = backoff * 2**attempt
                    time.sleep(wait_time)
                    continue

                if response.status_code == 429 and attempt < retries:
                    wait_time = response.headers.get(
                        "Retry-After", backoff * 2**attempt
                    )
                    time.sleep(float(wait_time))
                    continue
                break
            except requests.exceptions.RequestException:
                if attempt < retries:
                    wait_time = backoff * 2**attempt
                    time.sleep(wait_time)
                else:
                    break

        raise http_error_from_hf_response(
            url=url, status=response.status_code, body=response.text
        )


class HFClient(_Client):
    """A client for interacting with the Hugging Face API.

    Attributes:
        base_url (str): The base URL for the Hugging Face API.
    """

    def __init__(self, base_url: str = "https://huggingface.co"):
        """Initialize the HFClient with a base URL.

        Args:
            base_url (str): The base URL for the Hugging Face API.
                Defaults to "https://huggingface.co".
        """
        super().__init__(base_url=base_url)

    def get_model_metadata(self, repo_id: str, retries: int = 0) -> dict[str, Any]:
        """Retrieve metadata for a specific model from the Hugging Face API.

        Args:
            repo_id (str): The repository ID of the model.

        Returns:
            dict[str, Any]: The metadata of the model.

        Raises:
            AppError: If the response data is not a dictionary or if the request fails.
        """
        path = f"/api/models/{repo_id}"
        data = self._get_json(path, retries)
        if not isinstance(data, dict):
            raise AppError(
                code=SCHEMA_ERROR,
                message="Unexpected shape for model metadata.",
                context={"url": f"{self.base_url}{path}", "type": type(data).__name__},
            )

        data["num_contributors"] = None
        return data

    def get_dataset_metadata(self, repo_id: str, retries: int = 0) -> dict[str, Any]:
        """Retrieve metadata for a specific dataset from the Hugging Face API.

        Args:
            repo_id (str): The repository ID of the dataset.

        Returns:
            dict[str, Any]: The metadata of the dataset.

        Raises:
            AppError: If the response data is not a dictionary or if the request fails.
        """
        path = f"/api/datasets/{repo_id}"
        data = self._get_json(path, retries)
        if not isinstance(data, dict):
            raise AppError(
                code=SCHEMA_ERROR,
                message="Unexpected shape for dataset metadata.",
                context={"url": f"{self.base_url}{path}", "type": type(data).__name__},
            )

        data["num_contributors"] = None
        return data

    def get_space_metadata(self, repo_id: str, retries: int = 0) -> dict[str, Any]:
        """Retrieve metadata for a specific code space from the Hugging Face API.

        Args:
            repo_id (str): The repository ID of the code space.

        Returns:
            dict[str, Any]: The metadata of the code space.

        Raises:
            AppError: If the response data is not a dictionary or if the request fails.
        """
        path = f"/api/spaces/{repo_id}"
        data = self._get_json(path, retries)
        if not isinstance(data, dict):
            raise AppError(
                code=SCHEMA_ERROR,
                message="Unexpected shape for space metadata.",
                context={"url": f"{self.base_url}{path}", "type": type(data).__name__},
            )

        data["num_contributors"] = None
        return data


class GitHubClient(_Client):
    """A client for interacting with the GitHub API.

    Attributes:
        base_url (str): The base URL for the GitHub API.
    """

    def __init__(self, base_url: str = "https://api.github.com/repos"):
        """Initialize the GitHubClient with a base URL.

        Args:
            base_url (str): The base URL for the GitHub API.
                Defaults to "https://api.github.com/repos".
        """
        super().__init__(base_url=base_url)

    def _github_owner_repo_from_url(self, url: str) -> tuple[str, str]:
        path = urlparse(url)
        parts = [x for x in path.path.strip("/").split("/") if x]
        return parts[0], parts[1]

    def get_metadata(
        self, url: str, retries: int = 0, token: Optional[str] = None
    ) -> dict[str, Any]:
        """Retrieve metadata for a specific repository from the GitHub API.

        Args:
            url: The GitHub repository URL
            retries: Number of retry attempts for failed requests
            token: Optional GitHub API token for authentication

        Returns:
            dict[str, Any]: The metadata of the repository.

        Raises:
            AppError: If the response data is not a dictionary or if the request fails.
        """
        owner, repo = self._github_owner_repo_from_url(url)
        path = f"/{owner}/{repo}"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = self._get_json(path, retries, headers=headers)
        if not isinstance(data, dict):
            raise AppError(
                code=SCHEMA_ERROR,
                message="Unexpected shape for GitHub metadata.",
                context={"url": f"{self.base_url}{path}", "type": type(data).__name__},
            )

        # Try to get contributors, but don't fail if it doesn't work
        try:
            data["num_contributors"] = self._get_number_contributors(
                owner, repo, retries=retries, token=token
            )
        except Exception:
            data["num_contributors"] = None

        return data

    def _get_number_contributors(
        self, owner: str, repo: str, retries: int = 0, token: Optional[str] = None
    ) -> Optional[int]:
        """Get the number of contributors for a GitHub repository.

        Args:
            owner: The repository owner (username or organization)
            repo: The repository name
            retries: Number of retry attempts for failed requests
            token: Optional GitHub API token for authentication

        Returns:
            Number of contributors, or None if the request fails
        """
        path = f"/{owner}/{repo}/contributors"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = self._get_json(path, retries, headers=headers)
        if not isinstance(data, list):
            return None
        return len(data)

    def get_pull_requests(
        self, owner: str, repo: str, state: str = "all", retries: int = 0, token: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get all pull requests for a GitHub repository.

        Args:
            owner: The repository owner (username or organization)
            repo: The repository name
            state: The state of the PRs to fetch (open, closed, or all). Defaults to "all"
            retries: Number of retry attempts for failed requests
            token: Optional GitHub API token for authentication

        Returns:
            List of pull request dictionaries, or empty list if the request fails
        """
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        all_prs = []
        page = 1
        per_page = 100
        
        while True:
            try:
                path = f"/{owner}/{repo}/pulls?state={state}&page={page}&per_page={per_page}"
                # Use _get_json for consistency, but handle pagination manually
                url = self.base_url + path
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                prs = response.json()
                
                if not isinstance(prs, list) or len(prs) == 0:
                    break
                    
                all_prs.extend(prs)
                
                # If we got fewer than per_page results, we're done
                if len(prs) < per_page:
                    break
                    
                page += 1
            except Exception:
                break
                
        return all_prs

    def get_pull_request(self, owner: str, repo: str, pr_number: int, retries: int = 0, token: Optional[str] = None) -> dict[str, Any] | None:
        """Get details for a specific pull request, including additions and deletions.

        Args:
            owner: The repository owner (username or organization)
            repo: The repository name
            pr_number: The pull request number
            retries: Number of retry attempts for failed requests
            token: Optional GitHub API token for authentication

        Returns:
            Pull request dictionary with details, or None if the request fails
        """
        path = f"/{owner}/{repo}/pulls/{pr_number}"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            data = self._get_json(path, retries, headers=headers)
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    def get_pull_request_reviews(
        self, owner: str, repo: str, pr_number: int, retries: int = 0, token: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get reviews for a specific pull request.

        Args:
            owner: The repository owner (username or organization)
            repo: The repository name
            pr_number: The pull request number
            retries: Number of retry attempts for failed requests
            token: Optional GitHub API token for authentication

        Returns:
            List of review dictionaries, or empty list if the request fails
        """
        path = f"/{owner}/{repo}/pulls/{pr_number}/reviews"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            data = self._get_json(path, retries, headers=headers)
            if not isinstance(data, list):
                return []
            return data
        except Exception:
            return []


class GitLabClient(_Client):
    """A client for interacting with the GitLab API.

    Attributes:
        base_url (str): The base URL for the GitLab API.
    """

    def __init__(self, base_url: str = "https://gitlab.com/api/v4/projects"):
        """Initialize the GitLabClient with a base URL.

        Args:
            base_url (str): The base URL for the GitLab API.
                Defaults to "https://gitlab.com/api/v4/projects".
        """
        super().__init__(base_url=base_url)

    def _gitlab_owner_repo_from_url(self, url: str) -> str:
        path = urlparse(url)
        parts = [x for x in path.path.strip("/").split("/") if x]
        return "/".join(parts)

    def get_metadata(
        self, url: str, retries: int = 0, token: Optional[str] = None
    ) -> dict[str, Any]:
        """Retrieve metadata for a specific repository from the GitLab API.

        Args:
            url: The GitLab repository URL
            retries: Number of retry attempts for failed requests
            token: Optional GitLab API token for authentication

        Returns:
            dict[str, Any]: The metadata of the repository.

        Raises:
            AppError: If the response data is not a dictionary or if the request fails.
        """
        ns_name = self._gitlab_owner_repo_from_url(url)
        path = f"/{quote_plus(ns_name)}"
        headers = {"PRIVATE-TOKEN": token} if token else {}
        data = self._get_json(path, retries, headers=headers)
        if not isinstance(data, dict):
            raise AppError(
                code=SCHEMA_ERROR,
                message="Unexpected shape for GitLab metadata.",
                context={"url": f"{self.base_url}{path}", "type": type(data).__name__},
            )

        # Try to get contributors, but don't fail if it doesn't work
        try:
            data["num_contributors"] = self._get_number_contributors(
                ns_name, retries, token
            )
        except Exception:
            data["num_contributors"] = None

        return data

    def _get_number_contributors(
        self, ns_name: str, retries: int = 0, token: Optional[str] = None
    ) -> Optional[int]:
        """Get the number of contributors for a GitLab repository.

        Args:
            ns_name: The namespace and project name (e.g., "group/project")
            retries: Number of retry attempts for failed requests
            token: Optional GitLab API token for authentication

        Returns:
            Number of contributors, or None if the request fails
        """
        path = f"/{quote_plus(ns_name)}/repository/contributors"  # URL-encoded id
        headers = {"PRIVATE-TOKEN": token} if token else {}

        data = self._get_json(path, retries, headers=headers)
        if not isinstance(data, list):
            return None
        return len(data)
