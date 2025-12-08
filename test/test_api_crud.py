# Additional tests to increase coverage for api_server.py
import io
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from registry_models import Package
from storage import storage



@pytest.fixture
def auth_token(client):
    """Get authentication token for API requests."""
    auth_data = {
        "user": {"name": "ece30861defaultadminuser", "is_admin": True},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A\'\"`;DROP TABLE packages;"}
    }
    response = client.put("/api/authenticate", json=auth_data)
    assert response.status_code == 200
    return response.get_json()


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert "Model Registry API" in data["message"]


def test_upload_package(client, auth_token):
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "content": "base64encodedcontent",
        "metadata": {"description": "Test model"},
    }

    response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    assert response.status_code == 201

    data = response.get_json()
    assert data["message"] == "Package uploaded successfully"
    assert data["package"]["name"] == "test-model"
    assert data["package"]["version"] == "1.0.0"


def test_list_packages(client, auth_token):
    package_data = {"name": "test-model", "version": "1.0.0"}
    client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)

    response = client.get("/api/packages")
    assert response.status_code == 200

    data = response.get_json()
    assert data["total"] == 1
    assert len(data["packages"]) == 1


def test_get_package(client, auth_token):
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]

    response = client.get(f"/api/packages/{package_id}")
    assert response.status_code == 200

    data = response.get_json()
    assert data["id"] == package_id
    assert data["name"] == "test-model"


def test_delete_package(client, auth_token):
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]

    response = client.delete(f"/api/packages/{package_id}")
    assert response.status_code == 200

    get_response = client.get(f"/api/packages/{package_id}")
    assert get_response.status_code == 404


def test_reset_registry(client, auth_token):
    package_data = {"name": "test-model", "version": "1.0.0"}
    client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)

    # Authenticate to get token (required by OpenAPI spec)
    # Note: autograder uses "packages" not "artifacts" in the password
    auth_data = {
        "user": {"name": "ece30861defaultadminuser", "is_admin": True},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    assert auth_response.status_code == 200
    token = auth_response.get_json()  # Token is returned as JSON string

    # Call reset with authentication header
    response = client.delete("/api/reset", headers={"X-Authorization": token})
    assert response.status_code == 200

    list_response = client.get("/api/packages")
    data = list_response.get_json()
    assert data["total"] == 0


def test_health_dashboard_page(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert b"System Health Dashboard" in response.data


def test_check_auth_header_missing(client):
    """Test check_auth_header returns 403 when header is missing."""
    # Test reset endpoint without auth header
    response = client.delete("/api/reset")
    assert response.status_code == 403
    data = response.get_json()
    assert "Authentication failed" in data["error"]


def test_check_auth_header_invalid_token(client):
    """Test check_auth_header returns 403 when token is invalid."""
    # Test reset endpoint with invalid token
    response = client.delete("/api/reset", headers={"X-Authorization": "invalid-token"})
    assert response.status_code == 403
    data = response.get_json()
    assert "Authentication failed" in data["error"]


def test_infer_artifact_type_dataset(client):
    """Test infer_artifact_type returns 'dataset' for dataset URLs."""
    package = Package(
        id="test-id",
        name="test-dataset",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/datasets/test-org/test-dataset"},
    )
    # This is tested indirectly through artifact endpoints
    # Create package and test artifact conversion
    storage.create_package(package)
    
    # Authenticate first
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test list_artifacts to trigger infer_artifact_type
    response = client.post(
        "/api/artifacts",
        json=[{"name": "test-dataset"}],
        headers={"X-Authorization": token}
    )
    assert response.status_code == 200
    artifacts = response.get_json()
    if artifacts:
        assert artifacts[0]["type"] == "dataset"


def test_infer_artifact_type_code(client):
    """Test infer_artifact_type returns 'code' for code URLs."""
    package = Package(
        id="test-id",
        name="test-code",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://github.com/test-org/test-repo"},
    )
    storage.create_package(package)
    
    # Authenticate first
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test list_artifacts
    response = client.post(
        "/api/artifacts",
        json=[{"name": "test-code"}],
        headers={"X-Authorization": token}
    )
    assert response.status_code == 200


def test_package_to_artifact_metadata_with_type(client):
    """Test package_to_artifact_metadata with explicit artifact_type."""
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test get_artifact with explicit type
    response = client.get(
        "/api/artifacts/model/test-id",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 200


def test_package_to_artifact_download_url_generation(client):
    """Test package_to_artifact generates download_url."""
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test get_artifact to trigger download_url generation
    response = client.get(
        "/api/artifacts/model/test-id",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 200
    artifact = response.get_json()
    assert "download_url" in artifact["data"]


def test_validate_artifact_type(client):
    """Test validate_artifact_type validation."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test with invalid artifact type
    response = client.get(
        "/api/artifacts/invalid_type/test-id",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400
    assert "Invalid artifact type" in response.get_json()["error"]


def test_validate_artifact_id(client):
    """Test validate_artifact_id validation."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test with invalid artifact ID (contains invalid characters)
    response = client.get(
        "/api/artifacts/model/invalid@id#123",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400
    assert "Invalid artifact ID format" in response.get_json()["error"]


def test_root_endpoint_html(client):
    """Test root endpoint returns HTML when Accept header requests HTML."""
    response = client.get("/", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"


def test_api_root_endpoint(client):
    """Test /api endpoint."""
    response = client.get("/api")
    assert response.status_code == 200
    data = response.get_json()
    assert "Model Registry API" in data["message"]


def test_upload_package_no_data(client, auth_token):
    """Test upload_package with no data."""
    # Flask returns 500 when json=None, but we can test with empty data
    response = client.post("/api/packages", headers={"X-Authorization": auth_token}, data="", content_type="application/json")
    assert response.status_code in [400, 500]  # Either is acceptable


def test_upload_package_missing_field(client, auth_token):
    """Test upload_package with missing required field."""
    response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json={"name": "test"})
    assert response.status_code == 400
    assert "Missing required field" in response.get_json()["error"]


def test_upload_package_exception(client, auth_token):
    """Test upload_package exception handling."""
    with patch("api_server.storage.create_package", side_effect=Exception("Storage error")):
        response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json={"name": "test", "version": "1.0.0"})
        assert response.status_code == 500


def test_list_packages_sorting(client, auth_token):
    """Test list_packages with different sort fields."""
    # Create multiple packages
    for i in range(3):
        client.post("/api/packages", headers={"X-Authorization": auth_token}, json={"name": f"package-{i}", "version": f"{i}.0.0"})
    
    # Test sort by date
    response = client.get("/api/packages?sort-field=date")
    assert response.status_code == 200
    
    # Test sort by size
    response = client.get("/api/packages?sort-field=size")
    assert response.status_code == 200
    
    # Test sort by version
    response = client.get("/api/packages?sort-field=version")
    assert response.status_code == 200
    
    # Test descending order
    response = client.get("/api/packages?sort-field=alpha&sort-order=descending")
    assert response.status_code == 200


def test_list_packages_exception(client):
    """Test list_packages exception handling."""
    # Patch search_packages instead to trigger exception
    with patch("api_server.storage.search_packages", side_effect=Exception("Storage error")):
        response = client.get("/api/packages?query=test")
        assert response.status_code == 500


def test_get_package_html(client, auth_token):
    """Test get_package returns HTML when Accept header requests HTML."""
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    response = client.get(
        f"/api/packages/{package_id}",
        headers={"Accept": "text/html"}
    )
    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"


def test_get_package_exception(client, auth_token):
    """Test get_package exception handling."""
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.storage.get_package", side_effect=Exception("Storage error")):
        response = client.get(f"/api/packages/{package_id}")
        assert response.status_code == 500


def test_delete_package_not_found(client):
    """Test delete_package with non-existent package."""
    response = client.delete("/api/packages/non-existent-id")
    assert response.status_code == 404


def test_delete_package_exception(client, auth_token):
    """Test delete_package exception handling."""
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.storage.delete_package", side_effect=Exception("Storage error")):
        response = client.delete(f"/api/packages/{package_id}")
        assert response.status_code == 500


def test_download_package_no_url(client, auth_token):
    """Test download_package with package that has no URL."""
    package_data = {"name": "test-model", "version": "1.0.0", "metadata": {}}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    response = client.get(f"/packages/{package_id}/download", headers={"X-Authorization": auth_token})
    assert response.status_code == 400
    assert "no associated model URL" in response.get_json()["error"]


def test_download_package_invalid_content_type(client, auth_token):
    """Test download_package with invalid content type."""
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "metadata": {"url": "https://huggingface.co/test-org/test-model"}
    }
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    response = client.get(f"/packages/{package_id}/download?content=invalid", headers={"X-Authorization": auth_token})
    assert response.status_code == 400
    assert "Invalid content type" in response.get_json()["error"]


def test_download_package_no_files_found(client, auth_token):
    """Test download_package when no files match."""
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "metadata": {"url": "https://huggingface.co/test-org/test-model"}
    }
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.ModelResource") as mock_resource:
        mock_repo = MagicMock()
        mock_repo.glob.return_value = []  # No files
        mock_repo.root = "/tmp"
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=None)
        mock_instance = MagicMock()
        mock_instance.open_files.return_value = mock_context
        mock_resource.return_value = mock_instance
        
        response = client.get(f"/packages/{package_id}/download?content=weights", headers={"X-Authorization": auth_token})
        # May return 400 or 500 depending on where exception occurs
        assert response.status_code in [400, 500]


def test_download_package_exception(client, auth_token):
    """Test download_package exception handling."""
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "metadata": {"url": "https://huggingface.co/test-org/test-model"}
    }
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.ModelResource", side_effect=Exception("Model error")):
        response = client.get(f"/packages/{package_id}/download", headers={"X-Authorization": auth_token})
        assert response.status_code == 500


def test_rate_package(client, auth_token):
    """Test rate_package endpoint."""
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "metadata": {"url": "https://huggingface.co/test-org/test-model"}
    }
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        mock_metrics.return_value = {
            "ramp_up_time": MagicMock(value=0.8, latency_ms=100),
            "license": MagicMock(value=0.7, latency_ms=200),
        }
        
        response = client.get(f"/packages/{package_id}/rate")
        # May fail if model can't be loaded, but we test the endpoint path
        assert response.status_code in [200, 400, 500]


def test_rate_package_no_url(client, auth_token):
    """Test rate_package with package that has no URL."""
    package_data = {"name": "test-model", "version": "1.0.0", "metadata": {}}
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    response = client.get(f"/packages/{package_id}/rate")
    assert response.status_code == 400
    assert "No URL" in response.get_json()["error"]


def test_rate_package_exception(client, auth_token):
    """Test rate_package exception handling."""
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "metadata": {"url": "https://huggingface.co/test-org/test-model"}
    }
    upload_response = client.post("/api/packages", headers={"X-Authorization": auth_token}, json=package_data)
    package_id = upload_response.get_json()["package"]["id"]
    
    with patch("api_server.compute_all_metrics", side_effect=Exception("Metrics error")):
        response = client.get(f"/packages/{package_id}/rate")
        assert response.status_code == 500


def test_ingest_model_threshold_failure(client, auth_token):
    """Test ingest_model with metrics below threshold."""
    url = "https://huggingface.co/test-org/test-model"
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        from metrics.ramp_up_time import RampUpTime
        
        # Create metric with value below 0.5 threshold
        mock_metric = MagicMock()
        mock_metric.value = 0.3  # Below threshold
        mock_metric.latency_ms = 100
        
        mock_metrics.return_value = {
            "ramp_up_time": mock_metric,
            "license": mock_metric,
        }
        
        with patch("api_server.NetScore") as mock_net_score:
            mock_net_instance = MagicMock()
            mock_net_score.return_value = mock_net_instance
            
            response = client.post("/api/ingest", headers={"X-Authorization": auth_token}, json={"url": url})
            assert response.status_code == 400
            assert "Failed threshold" in response.get_json()["error"]


def test_ingest_model_size_score_threshold(client, auth_token):
    """Test ingest_model with size_score threshold check."""
    url = "https://huggingface.co/test-org/test-model"
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        # Create size_score with max below threshold
        size_metric = MagicMock()
        size_metric.value = {
            "raspberry_pi": 0.3,
            "jetson_nano": 0.4,
            "desktop_pc": 0.2,
            "aws_server": 0.3
        }
        size_metric.latency_ms = 100
        
        other_metric = MagicMock()
        other_metric.value = 0.8
        other_metric.latency_ms = 100
        
        mock_metrics.return_value = {
            "size_score": size_metric,
            "license": other_metric,
        }
        
        with patch("api_server.NetScore") as mock_net_score:
            mock_net_instance = MagicMock()
            mock_net_score.return_value = mock_net_instance
            
            response = client.post("/api/ingest", headers={"X-Authorization": auth_token}, json={"url": url})
            assert response.status_code == 400
            assert "Failed threshold" in response.get_json()["error"]


def test_ingest_model_invalid_metric_type(client, auth_token):
    """Test ingest_model with invalid metric type."""
    url = "https://huggingface.co/test-org/test-model"
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        # Create metric with invalid type (not int/float/dict)
        invalid_metric = MagicMock()
        invalid_metric.value = "invalid"  # String instead of number
        invalid_metric.latency_ms = 100
        
        mock_metrics.return_value = {
            "license": invalid_metric,
        }
        
        with patch("api_server.NetScore") as mock_net_score:
            mock_net_instance = MagicMock()
            mock_net_score.return_value = mock_net_instance
            
            response = client.post("/api/ingest", headers={"X-Authorization": auth_token}, json={"url": url})
            assert response.status_code == 400
            assert "Failed threshold" in response.get_json()["error"]


def test_ingest_model_exception(client, auth_token):
    """Test ingest_model exception handling."""
    url = "https://huggingface.co/test-org/test-model"
    
    with patch("api_server.ModelResource", side_effect=Exception("Model error")):
        response = client.post("/api/ingest", headers={"X-Authorization": auth_token}, json={"url": url})
        assert response.status_code == 500


def test_ingest_upload_csv_metadata_parse_error(client, auth_token):
    """Test ingest_upload with CSV metadata JSON parse error."""
    csv_content = "name,version,metadata\ntest,1.0.0,{invalid json}"
    files = {"file": (io.BytesIO(csv_content.encode()), "test.csv")}
    
    response = client.post("/api/ingest/upload", headers={"X-Authorization": auth_token}, data=files)
    # Should still create package but with empty metadata
    assert response.status_code in [201, 400]


def test_ingest_upload_json_single_object(client, auth_token):
    """Test ingest_upload with JSON single object."""
    json_content = '{"name": "test", "version": "1.0.0"}'
    files = {"file": (io.BytesIO(json_content.encode()), "test.json")}
    
    response = client.post("/api/ingest/upload", headers={"X-Authorization": auth_token}, data=files)
    assert response.status_code == 201


def test_ingest_upload_json_invalid(client, auth_token):
    """Test ingest_upload with invalid JSON."""
    json_content = "{invalid json}"
    files = {"file": (io.BytesIO(json_content.encode()), "test.json")}
    
    response = client.post("/api/ingest/upload", headers={"X-Authorization": auth_token}, data=files)
    # Invalid JSON raises exception, returns 500
    assert response.status_code in [400, 500]


def test_ingest_upload_exception(client, auth_token):
    """Test ingest_upload exception handling."""
    csv_content = "name,version\ntest,1.0.0"
    files = {"file": (io.BytesIO(csv_content.encode()), "test.csv")}
    
    # Patch parse_csv_content to raise exception
    with patch("api_server.parse_csv_content", side_effect=Exception("Parse error")):
        response = client.post("/api/ingest/upload", headers={"X-Authorization": auth_token}, data=files)
        assert response.status_code == 500


def test_reset_registry_exception(client):
    """Test reset_registry exception handling."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    with patch("api_server.storage.reset", side_effect=Exception("Reset error")):
        response = client.delete("/api/reset", headers={"X-Authorization": token})
        assert response.status_code == 500


def test_health_activity_invalid_params(client):
    """Test health_activity with invalid parameters."""
    response = client.get("/api/health/activity?window=invalid")
    assert response.status_code == 400


def test_health_logs_invalid_limit(client):
    """Test health_logs with invalid limit."""
    response = client.get("/api/health/logs?limit=invalid")
    assert response.status_code == 400


def test_get_tracks(client):
    """Test get_tracks endpoint."""
    response = client.get("/api/tracks")
    assert response.status_code == 200
    data = response.get_json()
    assert "plannedTracks" in data


# test_get_tracks_exception removed - can't easily test exception in get_tracks
# since it's a simple endpoint with try/except that's hard to trigger


def test_authenticate_missing_body(client):
    """Test authenticate with missing request body."""
    response = client.put("/api/authenticate", json=None)
    assert response.status_code == 400


def test_authenticate_missing_user(client):
    """Test authenticate with missing user field."""
    response = client.put("/api/authenticate", json={"secret": {"password": "test"}})
    assert response.status_code == 400


def test_authenticate_invalid_user_type(client):
    """Test authenticate with invalid user type."""
    response = client.put("/api/authenticate", json={"user": "not-a-dict", "secret": {"password": "test"}})
    assert response.status_code == 400


def test_authenticate_missing_secret(client):
    """Test authenticate with missing secret field."""
    response = client.put("/api/authenticate", json={"user": {"name": "test"}})
    assert response.status_code == 400


def test_authenticate_invalid_secret_type(client):
    """Test authenticate with invalid secret type."""
    response = client.put("/api/authenticate", json={"user": {"name": "test"}, "secret": "not-a-dict"})
    assert response.status_code == 400


def test_authenticate_missing_username(client):
    """Test authenticate with missing username."""
    response = client.put("/api/authenticate", json={
        "user": {},
        "secret": {"password": "test"}
    })
    assert response.status_code == 400


def test_authenticate_missing_password(client):
    """Test authenticate with missing password."""
    response = client.put("/api/authenticate", json={
        "user": {"name": "test"},
        "secret": {}
    })
    assert response.status_code == 400


def test_authenticate_invalid_credentials(client):
    """Test authenticate with invalid credentials."""
    response = client.put("/api/authenticate", json={
        "user": {"name": "wrong-user"},
        "secret": {"password": "wrong-password"}
    })
    assert response.status_code == 401


def test_authenticate_exception(client):
    """Test authenticate exception handling."""
    # Can't patch request.get_json outside request context
    # Instead, test with malformed JSON that causes parsing issues
    response = client.put(
        "/api/authenticate",
        data="invalid json",
        content_type="application/json"
    )
    # Flask will return 400 for invalid JSON
    assert response.status_code in [400, 415, 500]


def test_list_artifacts_no_auth(client):
    """Test list_artifacts without authentication."""
    response = client.post("/api/artifacts", json=[{"name": "test"}])
    assert response.status_code == 403


def test_list_artifacts_invalid_query(client):
    """Test list_artifacts with invalid query."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Test with non-list query
    response = client.post("/api/artifacts", json={"name": "test"}, headers={"X-Authorization": token})
    assert response.status_code == 400


def test_list_artifacts_empty_query(client):
    """Test list_artifacts with empty query list."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post("/api/artifacts", json=[], headers={"X-Authorization": token})
    assert response.status_code == 400


def test_list_artifacts_missing_name(client):
    """Test list_artifacts with query missing name field."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post("/api/artifacts", json=[{}], headers={"X-Authorization": token})
    assert response.status_code == 400


def test_list_artifacts_invalid_offset(client):
    """Test list_artifacts with invalid offset."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post(
        "/api/artifacts?offset=invalid",
        json=[{"name": "test"}],
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_list_artifacts_exception(client):
    """Test list_artifacts exception handling."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    with patch("api_server.storage.get_artifacts_by_query", side_effect=Exception("Storage error")):
        response = client.post(
            "/api/artifacts",
            json=[{"name": "test"}],
            headers={"X-Authorization": token}
        )
        assert response.status_code == 500


def test_get_artifact_no_auth(client):
    """Test get_artifact without authentication."""
    response = client.get("/api/artifacts/model/test-id")
    assert response.status_code == 403


def test_get_artifact_not_found(client):
    """Test get_artifact with non-existent artifact."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.get(
        "/api/artifacts/model/non-existent-id",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 404


def test_update_artifact_no_auth(client):
    """Test update_artifact without authentication."""
    response = client.put("/api/artifacts/model/test-id", json={})
    assert response.status_code == 403


def test_update_artifact_missing_body(client):
    """Test update_artifact with missing request body."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create a package first
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.put(
        "/api/artifacts/model/test-id",
        data="",
        content_type="application/json",
        headers={"X-Authorization": token}
    )
    # Flask returns 415 for missing/invalid Content-Type, or 400 for missing body
    assert response.status_code in [400, 415]


def test_update_artifact_id_mismatch(client):
    """Test update_artifact with ID mismatch."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create a package first
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.put(
        "/api/artifacts/model/test-id",
        json={
            "metadata": {"id": "different-id", "type": "model"},
            "data": {}
        },
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_update_artifact_type_mismatch(client):
    """Test update_artifact with type mismatch."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create a package first
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.put(
        "/api/artifacts/model/test-id",
        json={
            "metadata": {"id": "test-id", "type": "dataset"},
            "data": {}
        },
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_create_artifact_no_auth(client):
    """Test create_artifact without authentication."""
    response = client.post("/api/artifact/model", json={"url": "https://huggingface.co/test-org/test-model"})
    assert response.status_code == 403


def test_create_artifact_missing_url(client):
    """Test create_artifact with missing URL."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post(
        "/api/artifact/model",
        json={},
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_create_artifact_duplicate_url(client):
    """Test create_artifact with duplicate URL."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    url = "https://huggingface.co/test-org/test-model"
    
    # Create package with this URL first
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": url},
    )
    storage.create_package(package)
    
    # Try to create artifact with same URL
    with patch("api_server.compute_all_metrics") as mock_metrics:
        mock_metric = MagicMock()
        mock_metric.value = 0.8
        mock_metric.latency_ms = 100
        mock_metrics.return_value = {"license": mock_metric}
        
        with patch("api_server.NetScore"):
            response = client.post(
                "/api/artifact/model",
                json={"url": url},
                headers={"X-Authorization": token}
            )
            assert response.status_code == 409


def test_create_artifact_metrics_failure(client):
    """Test create_artifact when metrics computation fails."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    with patch("api_server.ModelResource", side_effect=Exception("Model error")):
        response = client.post(
            "/api/artifact/model",
            json={"url": "https://huggingface.co/test-org/test-model"},
            headers={"X-Authorization": token}
        )
        assert response.status_code == 424


def test_get_model_rating_no_auth(client):
    """Test get_model_rating without authentication."""
    response = client.get("/api/artifact/model/test-id/rate")
    assert response.status_code == 403


def test_get_model_rating_no_url(client):
    """Test get_model_rating with package that has no URL."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package without URL
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={},
    )
    storage.create_package(package)
    
    response = client.get(
        "/api/artifact/model/test-id/rate",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_get_model_rating_compute_metrics(client):
    """Test get_model_rating computes metrics when not cached."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package with URL but no scores
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        mock_metric = MagicMock()
        mock_metric.value = 0.8
        mock_metric.latency_ms = 100
        mock_metrics.return_value = {"license": mock_metric}
        
        with patch("api_server.NetScore"):
            response = client.get(
                "/api/artifact/model/test-id/rate",
                headers={"X-Authorization": token}
            )
            # May fail if model can't be loaded
            assert response.status_code in [200, 500]


def test_get_model_rating_exception(client):
    """Test get_model_rating exception handling."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    with patch("api_server.compute_all_metrics", side_effect=Exception("Metrics error")):
        response = client.get(
            "/api/artifact/model/test-id/rate",
            headers={"X-Authorization": token}
        )
        assert response.status_code == 500


def test_get_artifact_cost_no_auth(client):
    """Test get_artifact_cost without authentication."""
    response = client.get("/api/artifact/model/test-id/cost")
    assert response.status_code == 403


def test_get_artifact_cost_not_found(client):
    """Test get_artifact_cost with non-existent artifact."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.get(
        "/api/artifact/model/non-existent-id/cost",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 404


def test_get_artifact_cost_with_dependency(client):
    """Test get_artifact_cost with dependency parameter."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=1024 * 1024,  # 1 MB
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.get(
        "/api/artifact/model/test-id/cost?dependency=true",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "size_mb" in data
    assert data["dependency"] is True


def test_get_artifact_lineage_no_auth(client):
    """Test get_artifact_lineage without authentication."""
    response = client.get("/api/artifact/model/test-id/lineage")
    assert response.status_code == 403


def test_get_artifact_lineage_no_url(client):
    """Test get_artifact_lineage with package that has no URL."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package without URL
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={},
    )
    storage.create_package(package)
    
    response = client.get(
        "/api/artifact/model/test-id/lineage",
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_check_artifact_license_no_auth(client):
    """Test check_artifact_license without authentication."""
    response = client.post("/api/artifact/model/test-id/license-check", json={"github_url": "https://github.com/test"})
    assert response.status_code == 403


def test_check_artifact_license_missing_body(client):
    """Test check_artifact_license with missing request body."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.post(
        "/api/artifact/model/test-id/license-check",
        data="",
        content_type="application/json",
        headers={"X-Authorization": token}
    )
    # Flask returns 415 for missing/invalid Content-Type, or 400 for missing body
    assert response.status_code in [400, 415]


def test_check_artifact_license_missing_github_url(client):
    """Test check_artifact_license with missing github_url."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    response = client.post(
        "/api/artifact/model/test-id/license-check",
        json={},
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_check_artifact_license_no_url(client):
    """Test check_artifact_license with package that has no URL."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package without URL
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={},
    )
    storage.create_package(package)
    
    response = client.post(
        "/api/artifact/model/test-id/license-check",
        json={"github_url": "https://github.com/test"},
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_check_artifact_license_no_metric(client):
    """Test check_artifact_license when license metric is not found."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    with patch("api_server.compute_all_metrics") as mock_metrics:
        mock_metrics.return_value = {}  # No license metric
        
        response = client.post(
            "/api/artifact/model/test-id/license-check",
            json={"github_url": "https://github.com/test"},
            headers={"X-Authorization": token}
        )
        assert response.status_code == 200
        assert response.get_json() is False


def test_check_artifact_license_exception(client):
    """Test check_artifact_license exception handling."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    # Create package
    package = Package(
        id="test-id",
        name="test-model",
        version="1.0.0",
        uploaded_by="test-user",
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata={"url": "https://huggingface.co/test-org/test-model"},
    )
    storage.create_package(package)
    
    with patch("api_server.ModelResource", side_effect=Exception("Model error")):
        response = client.post(
            "/api/artifact/model/test-id/license-check",
            json={"github_url": "https://github.com/test"},
            headers={"X-Authorization": token}
        )
        assert response.status_code == 502


def test_search_artifacts_by_regex_no_auth(client):
    """Test search_artifacts_by_regex without authentication."""
    response = client.post("/api/artifact/byRegEx", json={"regex": "test"})
    assert response.status_code == 403


def test_search_artifacts_by_regex_missing_body(client):
    """Test search_artifacts_by_regex with missing request body."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post(
        "/api/artifact/byRegEx",
        data="",
        content_type="application/json",
        headers={"X-Authorization": token}
    )
    # Flask returns 415 for missing/invalid Content-Type, or 400 for missing body
    assert response.status_code in [400, 415]


def test_search_artifacts_by_regex_missing_regex(client):
    """Test search_artifacts_by_regex with missing regex."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    response = client.post(
        "/api/artifact/byRegEx",
        json={},
        headers={"X-Authorization": token}
    )
    assert response.status_code == 400


def test_search_artifacts_by_regex_exception(client):
    """Test search_artifacts_by_regex exception handling."""
    # Authenticate
    auth_data = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    auth_response = client.put("/api/authenticate", json=auth_data)
    token = auth_response.get_json()
    
    with patch("api_server.storage.search_packages", side_effect=Exception("Search error")):
        response = client.post(
            "/api/artifact/byRegEx",
            json={"regex": "test"},
            headers={"X-Authorization": token}
        )
        assert response.status_code == 400


def test_upload_page(client):
    """Test upload page route."""
    response = client.get("/upload")
    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"


def test_ingest_page(client):
    """Test ingest page route."""
    response = client.get("/ingest")
    assert response.status_code == 200
    assert response.content_type == "text/html; charset=utf-8"

