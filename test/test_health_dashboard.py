from __future__ import annotations

def test_health_activity_reports_recent_events(client) -> None:
    payload = {
        "name": "vision-model",
        "version": "1.0.0",
        "metadata": {"url": "https://example.com/model"},
    }

    response = client.post("/packages", json=payload)
    assert response.status_code == 201

    activity_response = client.get("/health/activity?window=60&limit=10")
    assert activity_response.status_code == 200

    data = activity_response.get_json()
    assert data["total_events"] >= 1
    assert data["counts"]["package_uploaded"] == 1
    assert len(data["events"]) >= 1
    assert any(event["type"] == "package_uploaded" for event in data["events"])


def test_health_logs_include_recent_operations(client) -> None:
    payload = {
        "name": "text-generator",
        "version": "2.0.0",
        "metadata": {"url": "https://example.com/model"},
    }

    upload_response = client.post("/packages", json=payload)
    assert upload_response.status_code == 201
    package_id = upload_response.get_json()["package"]["id"]

    delete_response = client.delete(f"/packages/{package_id}")
    assert delete_response.status_code == 200

    logs_response = client.get("/health/logs?limit=10")
    assert logs_response.status_code == 200

    entries = logs_response.get_json()["entries"]
    assert len(entries) >= 2
    messages = [entry["message"] for entry in entries]
    assert any("Uploaded package" in message for message in messages)
    assert any("Deleted package" in message for message in messages)

