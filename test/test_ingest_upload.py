import pytest
import sys
import os
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from storage import storage


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()  # Reset before each test
        yield client
        storage.reset()  # Reset after each test

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



def test_upload_csv_file_success(client, auth_token):
    """Test successful CSV file upload with valid data."""
    csv_content = """name,version,metadata
package1,1.0.0,"{""description"": ""Test package 1""}"
package2,2.0.0,"{""author"": ""Test Author""}"
package3,3.0.0,{}
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["message"] == "Packages imported successfully"
    assert json_data["imported_count"] == 3
    assert len(json_data["packages"]) == 3
    assert json_data["packages"][0]["name"] == "package1"
    assert json_data["packages"][1]["name"] == "package2"
    assert json_data["packages"][2]["name"] == "package3"


def test_upload_json_array_success(client, auth_token):
    """Test successful JSON file upload with array of packages."""
    json_content = """[
    {
        "name": "json-package1",
        "version": "1.0.0",
        "metadata": {"description": "JSON package 1"}
    },
    {
        "name": "json-package2",
        "version": "2.0.0",
        "metadata": {"author": "JSON Author"}
    }
]"""

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "packages.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["message"] == "Packages imported successfully"
    assert json_data["imported_count"] == 2
    assert json_data["packages"][0]["name"] == "json-package1"
    assert json_data["packages"][1]["name"] == "json-package2"


def test_upload_json_single_object_success(client, auth_token):
    """Test successful JSON file upload with single package object."""
    json_content = """{
    "name": "single-package",
    "version": "1.0.0",
    "metadata": {"description": "Single package"}
}"""

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "package.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["message"] == "Packages imported successfully"
    assert json_data["imported_count"] == 1
    assert json_data["packages"][0]["name"] == "single-package"


def test_upload_no_file_error(client, auth_token):
    """Test error when no file is provided."""
    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data={}
    )

    assert response.status_code == 400
    json_data = response.get_json()
    assert "No file provided" in json_data["error"]


def test_upload_empty_filename_error(client, auth_token):
    """Test error when file has empty filename."""
    data = {
        "file": (io.BytesIO(b"test"), "")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 400
    json_data = response.get_json()
    assert "No file selected" in json_data["error"]


def test_upload_invalid_file_type_error(client, auth_token):
    """Test error when invalid file type is uploaded."""
    data = {
        "file": (io.BytesIO(b"test content"), "test.txt")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 400
    json_data = response.get_json()
    assert "Invalid file type" in json_data["error"]


def test_upload_csv_missing_required_fields(client, auth_token):
    """Test CSV upload with missing required fields."""
    csv_content = """name,version,metadata
package1,1.0.0,{}
,2.0.0,{}
package3,,{}
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    # Should succeed for valid rows and warn about invalid ones
    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["imported_count"] == 1  # Only package1 is valid
    assert "warnings" in json_data


def test_upload_json_missing_required_fields(client, auth_token):
    """Test JSON upload with missing required fields."""
    json_content = """[
    {
        "name": "valid-package",
        "version": "1.0.0"
    },
    {
        "name": "invalid-package"
    },
    {
        "version": "2.0.0"
    }
]"""

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "packages.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    # Should succeed for valid rows and warn about invalid ones
    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["imported_count"] == 1  # Only first package is valid
    assert "warnings" in json_data


def test_upload_empty_csv_error(client, auth_token):
    """Test error when CSV file is empty."""
    csv_content = """name,version,metadata
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 400
    json_data = response.get_json()
    assert "No valid package data found" in json_data["error"]


def test_upload_empty_json_array_error(client, auth_token):
    """Test error when JSON array is empty."""
    json_content = "[]"

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "packages.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 400
    json_data = response.get_json()
    assert "No valid package data found" in json_data["error"]


def test_upload_invalid_json_error(client, auth_token):
    """Test error when JSON is malformed."""
    json_content = """{"name": "test", "version": "1.0.0"""

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "packages.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 500
    json_data = response.get_json()
    assert "Failed to process file" in json_data["error"]


def test_upload_csv_without_metadata(client, auth_token):
    """Test CSV upload without metadata column."""
    csv_content = """name,version
package1,1.0.0
package2,2.0.0
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["imported_count"] == 2
    # Metadata should default to empty dict
    assert json_data["packages"][0]["metadata"] == {}


def test_upload_json_without_metadata(client, auth_token):
    """Test JSON upload without metadata field."""
    json_content = """[
    {
        "name": "package1",
        "version": "1.0.0"
    }
]"""

    data = {
        "file": (io.BytesIO(json_content.encode("utf-8")), "packages.json")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    json_data = response.get_json()
    assert json_data["imported_count"] == 1
    # Metadata should default to empty dict
    assert json_data["packages"][0]["metadata"] == {}


def test_packages_stored_correctly(client, auth_token):
    """Test that uploaded packages are actually stored and retrievable."""
    csv_content = """name,version,metadata
stored-package,5.0.0,"{""key"": ""value""}"
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 201
    package_id = response.get_json()["packages"][0]["id"]

    # Verify package can be retrieved
    get_response = client.get(f"/api/packages/{package_id}")
    assert get_response.status_code == 200

    package_data = get_response.get_json()
    assert package_data["name"] == "stored-package"
    assert package_data["version"] == "5.0.0"
    assert package_data["metadata"]["key"] == "value"


def test_upload_all_invalid_rows_error(client, auth_token):
    """Test error when all rows in file are invalid."""
    csv_content = """name,version,metadata
,1.0.0,{}
package2,,{}
"""

    data = {
        "file": (io.BytesIO(csv_content.encode("utf-8")), "packages.csv")
    }

    response = client.post(
        "/api/ingest/upload", headers={"X-Authorization": auth_token},
        content_type="multipart/form-data",
        data=data
    )

    assert response.status_code == 400
    json_data = response.get_json()
    # When all rows fail validation, we get this error
    assert "Failed to import any packages" in json_data["error"] or "No valid package data found" in json_data["error"]
    if "details" in json_data:
        assert len(json_data["details"]) > 0
