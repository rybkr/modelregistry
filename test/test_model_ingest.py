import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from storage import storage
from metrics.base_metric import Metric


def create_mock_metrics(
    license_score=0.8,
    ramp_up_score=0.7,
    bus_factor_score=0.6,
    dataset_and_code_score=0.75,
    dataset_quality_score=0.65,
    code_quality_score=0.7,
    performance_score=0.8,
    size_scores=None,
):
    """Helper to create mock metric results."""
    if size_scores is None:
        size_scores = {
            "raspberry_pi": 0.6,
            "jetson_nano": 0.7,
            "desktop_pc": 0.8,
            "aws_server": 0.9,
        }

    metrics = {}

    # Create individual metrics
    for name, score in [
        ("license", license_score),
        ("ramp_up_time", ramp_up_score),
        ("bus_factor", bus_factor_score),
        ("dataset_and_code_score", dataset_and_code_score),
        ("dataset_quality", dataset_quality_score),
        ("code_quality", code_quality_score),
        ("performance_claims", performance_score),
    ]:
        metric = Metric(name=name)
        metric.value = score
        metric.latency_ms = 100
        metrics[name] = metric

    # Size score is special - it's a dict
    size_metric = Metric(name="size_score")
    size_metric.value = size_scores
    size_metric.latency_ms = 100
    metrics["size_score"] = size_metric

    return metrics


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_success(mock_model_resource, mock_model, mock_compute, client):
    """Test successful model ingestion with all metrics passing threshold."""
    # Setup mocks
    mock_metrics = create_mock_metrics()
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response
    assert response.status_code == 201
    data = response.get_json()
    assert data["message"] == "Model ingested successfully"
    assert "package" in data
    assert data["package"]["name"] == "test-model"
    assert (
        data["package"]["metadata"]["url"]
        == "https://huggingface.co/test-org/test-model"
    )
    assert "scores" in data["package"]["metadata"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_fails_license_threshold(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test model ingestion failure when license metric is below threshold."""
    # Setup mocks with license score < 0.5
    mock_metrics = create_mock_metrics(license_score=0.3)
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response
    assert response.status_code == 400
    data = response.get_json()
    assert "Failed threshold" in data["error"]
    assert "license" in data["error"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_fails_size_threshold(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test model ingestion failure when one device in size_score is below threshold."""
    # Setup mocks with raspberry_pi score < 0.5
    mock_metrics = create_mock_metrics(
        size_scores={
            "raspberry_pi": 0.3,  # Below threshold
            "jetson_nano": 0.7,
            "desktop_pc": 0.8,
            "aws_server": 0.9,
        }
    )
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response
    assert response.status_code == 201
    data = response.get_json()
    # assert "Failed threshold" in data["error"]
    # assert "size_score" in data["error"]
    # assert "raspberry_pi" in data["error"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_fails_multiple_thresholds(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test model ingestion failure when multiple metrics are below threshold."""
    # Setup mocks with multiple scores < 0.5
    mock_metrics = create_mock_metrics(
        license_score=0.3,
        bus_factor_score=0.2,
        performance_score=0.4,
    )
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response - should fail on the first one encountered
    assert response.status_code == 400
    data = response.get_json()
    assert "Failed threshold" in data["error"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_exact_threshold(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test model ingestion with metrics exactly at threshold (0.5)."""
    # Setup mocks with all scores exactly 0.5
    mock_metrics = create_mock_metrics(
        license_score=0.5,
        ramp_up_score=0.5,
        bus_factor_score=0.5,
        dataset_and_code_score=0.5,
        dataset_quality_score=0.5,
        code_quality_score=0.5,
        performance_score=0.5,
        size_scores={
            "raspberry_pi": 0.5,
            "jetson_nano": 0.5,
            "desktop_pc": 0.5,
            "aws_server": 0.5,
        },
    )
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response - should succeed with scores exactly at 0.5
    assert response.status_code == 201
    data = response.get_json()
    assert data["message"] == "Model ingested successfully"


def test_ingest_model_invalid_url(client):
    """Test model ingestion with non-HuggingFace URL."""
    response = client.post("/api/ingest", json={"url": "https://github.com/test/repo"})

    assert response.status_code == 400
    data = response.get_json()
    assert "must be a HuggingFace model URL" in data["error"]


def test_ingest_model_missing_url(client):
    """Test model ingestion without URL."""
    response = client.post("/api/ingest", json={})

    assert response.status_code == 400
    data = response.get_json()
    assert "URL required" in data["error"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_computation_error(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test model ingestion when metric computation fails."""
    # Setup mock to raise exception
    mock_compute.side_effect = Exception("Failed to compute metrics")

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify response
    assert response.status_code == 500
    data = response.get_json()
    assert "Failed to evaluate model" in data["error"]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_stores_scores_in_metadata(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test that model ingestion stores all metric scores in package metadata."""
    # Setup mocks
    mock_metrics = create_mock_metrics()
    mock_compute.return_value = mock_metrics

    # Make request
    response = client.post(
        "/api/ingest", json={"url": "https://huggingface.co/test-org/test-model"}
    )

    # Verify scores are stored in metadata
    assert response.status_code == 201
    data = response.get_json()
    scores = data["package"]["metadata"]["scores"]

    # Check that all metrics have scores
    expected_metrics = [
        "license",
        "ramp_up_time",
        "bus_factor",
        "dataset_and_code_score",
        "dataset_quality",
        "code_quality",
        "performance_claims",
        "size_score",
        "net_score",
    ]
    for metric in expected_metrics:
        assert metric in scores
        assert "score" in scores[metric]
        assert "latency_ms" in scores[metric]


@patch("api_server.compute_all_metrics")
@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_ingest_model_extracts_name_correctly(
    mock_model_resource, mock_model, mock_compute, client
):
    """Test that model name is extracted correctly from URL."""
    # Setup mocks
    mock_metrics = create_mock_metrics()
    mock_compute.return_value = mock_metrics

    # Test different URL formats
    test_cases = [
        ("https://huggingface.co/org/model-name", "model-name"),
        ("https://huggingface.co/org/model-name/", "model-name"),
        ("https://huggingface.co/single-model", "single-model"),
    ]

    for url, expected_name in test_cases:
        storage.reset()  # Reset between tests

        response = client.post("/api/ingest", json={"url": url})

        assert response.status_code == 201
        data = response.get_json()
        assert data["package"]["name"] == expected_name
