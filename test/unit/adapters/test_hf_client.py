"""Unit tests for HuggingFace client adapter.

This module contains unit tests for the HFClient class, which handles
communication with the HuggingFace API. Tests cover metadata fetching
for models, datasets, and spaces, error handling, and response parsing.
"""

from test.helpers.builders import make_response
from unittest.mock import MagicMock, patch

import pytest
import requests

from adapters.client import HFClient
from errors import SCHEMA_ERROR, AppError


@pytest.fixture
def hf_client() -> HFClient:
    """Fixture to create an instance of HFClient."""
    return HFClient()


class TestGetModelMetadata:
    """Test cases for the get_model_metadata method."""

    @patch("adapters.client.requests.get")
    def test_success(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test successful retrieval of model metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body={"name": "test-model"})

        # Call the method
        result = hf_client.get_model_metadata("test-repo")

        # Assertions
        assert result == {"name": "test-model", "num_contributors": None}
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/models/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_schema_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test schema error when retrieving model metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body=["unexpected", "list"])

        # Call the method and assert exception
        with pytest.raises(AppError) as exc_info:
            hf_client.get_model_metadata("test-repo")

        assert exc_info.value.code == SCHEMA_ERROR
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/models/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_http_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test HTTP error when retrieving model metadata."""
        mock_get.return_value = make_response(404, text="Not Found")

        # Call the method and assert exception
        with pytest.raises(AppError):
            print(hf_client.get_model_metadata("test-repo"))

        mock_get.assert_called_once_with(
            "https://huggingface.co/api/models/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_retry_on_5xx_then_succeed(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 5xx errors and eventual success."""
        # Mock responses: 500 twice, then 200
        mock_get.side_effect = [
            make_response(status=500, text="Internal Server Error"),
            make_response(status=500, text="Internal Server Error"),
            make_response(status=200, body={"name": "test-model"}),
        ]

        # Call the method
        result = hf_client.get_model_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-model", "num_contributors": None}
        assert mock_get.call_count == 3
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_429_with_retry_after_header(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 429 errors with Retry-After header."""
        # Mock responses: 429 with Retry-After, then 200
        mock_get.side_effect = [
            make_response(
                status=429, text="Rate Limit Exceeded", headers={"Retry-After": "1"}
            ),
            make_response(status=200, body={"name": "test-model"}),
        ]

        # Call the method
        result = hf_client.get_model_metadata("test-repo", 1)

        # Assertions
        assert result == {"name": "test-model", "num_contributors": None}
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(
            1
        )  # Ensure sleep was called with Retry-After value

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_429_without_retry_after_header(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 429 errors without Retry-After header."""
        # Mock responses: 429 twice, then 200
        mock_get.side_effect = [
            make_response(status=429, text="Rate Limit Exceeded"),
            make_response(status=429, text="Rate Limit Exceeded"),
            make_response(status=200, body={"name": "test-model"}),
        ]

        # Call the method
        result = hf_client.get_model_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-model", "num_contributors": None}
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2  # Ensure sleep was called for retries
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_request_exception_handling(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test handling of RequestException during retries."""
        # Mock responses: raise RequestException twice, then succeed
        mock_get.side_effect = [
            requests.exceptions.RequestException("Connection error"),
            requests.exceptions.RequestException("Connection error"),
            make_response(status=200, body={"name": "test-model"}),
        ]

        # Call the method
        result = hf_client.get_model_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-model", "num_contributors": None}
        assert mock_get.call_count == 3
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time


class TestGetDatasetMetadata:
    """Test cases for the get_dataset_metadata method."""

    @patch("adapters.client.requests.get")
    def test_success(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test successful retrieval of dataset metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body={"name": "test-dataset"})

        # Call the method
        result = hf_client.get_dataset_metadata("test-repo")

        # Assertions
        assert result == {"name": "test-dataset", "num_contributors": None}
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/datasets/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_schema_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test schema error when retrieving dataset metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body=["unexpected", "list"])

        # Call the method and assert exception
        with pytest.raises(AppError) as exc_info:
            hf_client.get_dataset_metadata("test-repo")

        assert exc_info.value.code == SCHEMA_ERROR
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/datasets/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_http_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test HTTP error when retrieving dataset metadata."""
        # Mock response
        mock_get.return_value = make_response(status=500, text="Internal Server Error")

        # Call the method and assert exception
        with pytest.raises(AppError):
            hf_client.get_dataset_metadata("test-repo")

        mock_get.assert_called_once_with(
            "https://huggingface.co/api/datasets/test-repo", headers={}
        )


class TestGetSpaceMetadata:
    """Test cases for the get_space_metadata method."""

    @patch("adapters.client.requests.get")
    def test_success(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test successful retrieval of space metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body={"name": "test-space"})

        # Call the method
        result = hf_client.get_space_metadata("test-repo")

        # Assertions
        assert result == {"name": "test-space", "num_contributors": None}
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/spaces/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_schema_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test schema error when retrieving space metadata."""
        # Mock response
        mock_get.return_value = make_response(status=200, body=["unexpected", "list"])

        # Call the method and assert exception
        with pytest.raises(AppError) as exc_info:
            hf_client.get_space_metadata("test-repo")

        assert exc_info.value.code == SCHEMA_ERROR
        mock_get.assert_called_once_with(
            "https://huggingface.co/api/spaces/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    def test_http_error(self, mock_get: MagicMock, hf_client: HFClient) -> None:
        """Test HTTP error when retrieving space metadata."""
        # Mock response
        mock_get.return_value = make_response(404, text="Not Found")

        # Call the method and assert exception
        with pytest.raises(AppError):
            hf_client.get_space_metadata("test-repo")

        mock_get.assert_called_once_with(
            "https://huggingface.co/api/spaces/test-repo", headers={}
        )

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_retry_on_5xx_then_succeed(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 5xx errors and eventual success."""
        # Mock responses: 500 twice, then 200
        mock_get.side_effect = [
            make_response(status=500, text="Internal Server Error"),
            make_response(status=500, text="Internal Server Error"),
            make_response(status=200, body={"name": "test-space"}),
        ]

        # Call the method
        result = hf_client.get_space_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-space", "num_contributors": None}
        assert mock_get.call_count == 3
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_429_with_retry_after_header(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 429 errors with Retry-After header."""
        # Mock responses: 429 with Retry-After, then 200
        mock_get.side_effect = [
            make_response(
                status=429, text="Rate Limit Exceeded", headers={"Retry-After": "1"}
            ),
            make_response(status=200, body={"name": "test-space"}),
        ]

        # Call the method
        result = hf_client.get_space_metadata("test-repo", 1)

        # Assertions
        assert result == {"name": "test-space", "num_contributors": None}
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once_with(
            1
        )  # Ensure sleep was called with Retry-After value

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_429_without_retry_after_header(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test retry logic on 429 errors without Retry-After header."""
        # Mock responses: 429 twice, then 200
        mock_get.side_effect = [
            make_response(status=429, text="Rate Limit Exceeded"),
            make_response(status=429, text="Rate Limit Exceeded"),
            make_response(status=200, body={"name": "test-space"}),
        ]

        # Call the method
        result = hf_client.get_space_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-space", "num_contributors": None}
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2  # Ensure sleep was called for retries
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time

    @patch("adapters.client.requests.get")
    @patch("time.sleep", return_value=None)  # Mock sleep to avoid actual delays
    def test_request_exception_handling(
        self, mock_sleep: MagicMock, mock_get: MagicMock, hf_client: HFClient
    ) -> None:
        """Test handling of RequestException during retries."""
        # Mock responses: raise RequestException twice, then succeed
        mock_get.side_effect = [
            requests.exceptions.RequestException("Connection error"),
            requests.exceptions.RequestException("Connection error"),
            make_response(status=200, body={"name": "test-space"}),
        ]

        # Call the method
        result = hf_client.get_space_metadata("test-repo", 2)

        # Assertions
        assert result == {"name": "test-space", "num_contributors": None}
        assert mock_get.call_count == 3
        mock_sleep.assert_any_call(2)  # Ensure sleep was called with backoff time
        mock_sleep.assert_any_call(
            4
        )  # Ensure sleep was called with increased backoff time
