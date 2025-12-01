from __future__ import annotations
import pytest


@pytest.fixture
def auth_token(client):
    """Get authentication token for API requests."""
    auth_data = {
        "user": {"name": "ece30861defaultadminuser", "is_admin": True},
        "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
    }
    response = client.put("/api/authenticate", json=auth_data)
    assert response.status_code == 200
    return response.get_json()


def test_health_activity_reports_recent_events(client, auth_token) -> None:
    payload = {
        "name": "vision-model",
        "version": "1.0.0",
        "metadata": {"url": "https://example.com/model"},
    }

    response = client.post("/api/packages", json=payload, headers={"X-Authorization": auth_token})
    assert response.status_code == 201

    activity_response = client.get("/api/health/activity?window=60&limit=10")
    assert activity_response.status_code == 200

    data = activity_response.get_json()
    assert data["total_events"] >= 1
    assert data["counts"]["package_uploaded"] == 1
    assert len(data["events"]) >= 1
    assert any(event["type"] == "package_uploaded" for event in data["events"])


def test_health_logs_include_recent_operations(client, auth_token) -> None:
    payload = {
        "name": "text-generator",
        "version": "2.0.0",
        "metadata": {"url": "https://example.com/model"},
    }

    upload_response = client.post("/api/packages", json=payload, headers={"X-Authorization": auth_token})
    assert upload_response.status_code == 201
    package_id = upload_response.get_json()["package"]["id"]

    delete_response = client.delete(f"/api/packages/{package_id}")
    assert delete_response.status_code == 200

    logs_response = client.get("/api/health/logs?limit=10")
    assert logs_response.status_code == 200

    entries = logs_response.get_json()["entries"]
    assert len(entries) >= 2
    messages = [entry["message"] for entry in entries]
    assert any("Uploaded package" in message for message in messages)
    assert any("Deleted package" in message for message in messages)

