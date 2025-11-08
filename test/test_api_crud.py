def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert "Model Registry API" in data["message"]


def test_upload_package(client):
    package_data = {
        "name": "test-model",
        "version": "1.0.0",
        "content": "base64encodedcontent",
        "metadata": {"description": "Test model"},
    }

    response = client.post("/packages", json=package_data)
    assert response.status_code == 201

    data = response.get_json()
    assert data["message"] == "Package uploaded successfully"
    assert data["package"]["name"] == "test-model"
    assert data["package"]["version"] == "1.0.0"


def test_list_packages(client):
    package_data = {"name": "test-model", "version": "1.0.0"}
    client.post("/packages", json=package_data)

    response = client.get("/packages")
    assert response.status_code == 200

    data = response.get_json()
    assert data["total"] == 1
    assert len(data["packages"]) == 1


def test_get_package(client):
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/packages", json=package_data)
    package_id = upload_response.get_json()["package"]["id"]

    response = client.get(f"/packages/{package_id}")
    assert response.status_code == 200

    data = response.get_json()
    assert data["id"] == package_id
    assert data["name"] == "test-model"


def test_delete_package(client):
    package_data = {"name": "test-model", "version": "1.0.0"}
    upload_response = client.post("/packages", json=package_data)
    package_id = upload_response.get_json()["package"]["id"]

    response = client.delete(f"/packages/{package_id}")
    assert response.status_code == 200

    get_response = client.get(f"/packages/{package_id}")
    assert get_response.status_code == 404


def test_reset_registry(client):
    package_data = {"name": "test-model", "version": "1.0.0"}
    client.post("/packages", json=package_data)

    response = client.delete("/reset")
    assert response.status_code == 200

    list_response = client.get("/packages")
    data = list_response.get_json()
    assert data["total"] == 0


def test_health_dashboard_page(client):
    response = client.get("/health/dashboard")
    assert response.status_code == 200
    assert b"System Health Dashboard" in response.data
