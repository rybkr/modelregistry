from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from datetime import datetime
import uuid
import os
import csv
import json
import io

from registry_models import Package
from storage import storage
from metrics_engine import compute_all_metrics
from models import Model
from resources.model_resource import ModelResource

# Get the directory where this file is located (src directory)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SRC_DIR, 'templates')
STATIC_DIR = os.path.join(SRC_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
CORS(app)

DEFAULT_USERNAME = "ece30861defaultadminuser"
DEFAULT_PASSWORD = "'correcthorsebatterystaple123(!__+@**(A;DROP TABLE packages'"


@app.route("/health", methods=["GET"])
def health():
    """Check the health status of the Model Registry API.

    Returns health information including server status, current timestamp,
    the total number of packages in the registry.

    Returns:
        tuple: JSON response with health data and 200 status code
            - status (str): Health status indicator
            - timestamp (str): Current UTC timestamp in ISO format
            - packages_count (int): Total number of packages stored
    """
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "packages_count": len(storage.packages),
        }
    ), 200


@app.route("/", methods=["GET"])
def index():
    """Serve the main package listing page or API info.

    Returns:
        HTML or JSON: Package listing page for browsers, API info for API requests
    """
    # Check if this is an API request
    # Default to JSON for programmatic requests (no Accept header or Accept: */*)
    # Only return HTML if explicitly requesting HTML
    accept_header = request.headers.get("Accept", "")
    wants_html = (
        "text/html" in accept_header and
        "application/json" not in accept_header and
        accept_header != "*/*" and
        accept_header != ""
    )
    
    if wants_html:
        return render_template("index.html")
    else:
        # Default to JSON for API requests and test clients
        return jsonify({"message": "Model Registry API v1.0", "status": "running"}), 200


@app.route("/api", methods=["GET"])
def api_root():
    """Return basic API information.

    Provides version and status information for the Model Registry API.

    Returns:
        tuple: JSON response with API metadata and 200 status code
            - message (str): API version identifier
            - status (str): API running status
    """
    return jsonify({"message": "Model Registry API v1.0", "status": "running"}), 200


@app.route("/packages", methods=["POST"])
def upload_package():
    """Upload a new package to the registry.

    Creates a new package entry with the provided name, version, and optional
    metadata. Automatically assigns a unique ID and records upload timestamp.

    Request Body (JSON):
        - name (str, required): Package name
        - version (str, required): Package version
        - content (str, optional): Package content
        - metadata (dict, optional): Additional package metadata

    Returns:
        tuple: JSON response and HTTP status code
            Success (201):
                - message (str): Success confirmation
                - package (dict): Created package details
            Error (400): Missing required fields or no data provided
            Error (500): Server error during package creation
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        required_fields = ["name", "version"]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        package_id = str(uuid.uuid4())
        package = Package(
            id=package_id,
            name=data["name"],
            version=data["version"],
            uploaded_by=DEFAULT_USERNAME,
            upload_timestamp=datetime.utcnow(),
            size_bytes=len(data.get("content", "")),
            metadata=data.get("metadata", {}),
            s3_key=None,
        )

        storage.create_package(package)

        return jsonify(
            {"message": "Package uploaded successfully", "package": package.to_dict()}
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/packages", methods=["GET"])
def list_packages():
    """List packages with optional search and pagination.

    Retrieves a paginated list of packages. Supports searching by query string
    with optional regex matching.

    Query Parameters:
        - offset (int, optional): Starting index for pagination (default: 0)
        - limit (int, optional): Maximum number of results (default: 100)
        - query (str, optional): Search query string
        - regex (bool, optional): Enable regex search mode (default: false)

    Returns:
        tuple: JSON response and HTTP status code
            Success (200):
                - packages (list): Array of package objects
                - offset (int): Current offset value
                - limit (int): Current limit value
                - total (int): Total number of packages in registry
            Error (500): Server error during retrieval
    """
    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 100))
        query = request.args.get("query", "")
        regex = request.args.get("regex", "false").lower() == "true"

        if query:
            packages = storage.search_packages(query, use_regex=regex)
            packages = packages[offset : offset + limit]
        else:
            packages = storage.list_packages(offset=offset, limit=limit)

        return jsonify(
            {
                "packages": [p.to_dict() for p in packages],
                "offset": offset,
                "limit": limit,
                "total": len(storage.packages),
            }
        ), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/packages/<package_id>", methods=["GET"])
def get_package(package_id):
    """Retrieve a specific package by ID.

    Fetches detailed information about a package using its unique identifier.
    Returns JSON for API requests or HTML page for browser requests.

    Args:
        package_id (str): Unique package identifier (UUID)

    Returns:
        tuple or HTML: JSON response and HTTP status code, or HTML page
            Success (200): Package details as dictionary or HTML page
            Error (404): Package not found
            Error (500): Server error during retrieval
    """
    # Check if this is an API request
    # Default to JSON for programmatic requests (no Accept header or Accept: */*)
    # Only return HTML if explicitly requesting HTML
    accept_header = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    
    # Return HTML only if explicitly requesting HTML
    wants_html = (
        "text/html" in accept_header and
        "application/json" not in accept_header
    )
    
    if wants_html:
        # Return HTML page for browser requests
        return render_template("package_detail.html", package_id=package_id)
    else:
        # Default to JSON for API requests
        try:
            package = storage.get_package(package_id)
            if not package:
                return jsonify({"error": "Package not found"}), 404
            return jsonify(package.to_dict()), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/packages/<package_id>", methods=["DELETE"])
def delete_package(package_id):
    """Delete a package from the registry.

    Removes a package and all associated data using its unique identifier.

    Args:
        package_id (str): Unique package identifier (UUID)

    Returns:
        tuple: JSON response and HTTP status code
            Success (200): Deletion confirmation message
            Error (404): Package not found
            Error (500): Server error during deletion
    """
    try:
        success = storage.delete_package(package_id)
        if not success:
            return jsonify({"error": "Package not found"}), 404
        return jsonify({"message": "Package deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/packages/<package_id>/rate", methods=["GET"])
def rate_package(package_id):
    """Calculate and return quality metrics for a package.

    Evaluates a package by computing various quality metrics based on its
    associated URL. The package must have a URL in its metadata.

    Args:
        package_id (str): Unique package identifier (UUID)

    Returns:
        tuple: JSON response and HTTP status code
            Success (200): Dictionary of metric scores and latencies
                Each metric contains:
                    - score (float): Metric score value
                    - latency_ms (float): Computation time in milliseconds
            Error (404): Package not found
            Error (400): Package missing URL in metadata
            Error (500): Server error during metric computation
    """
    try:
        package = storage.get_package(package_id)
        if not package:
            return jsonify({"error": "Package not found"}), 404

        url = package.metadata.get("url")
        if not url:
            return jsonify({"error": "No URL in package metadata"}), 400

        model = Model(model=ModelResource(url=url))
        results = compute_all_metrics(model)

        scores = {}
        for name, metric in results.items():
            scores[name] = {"score": metric.value, "latency_ms": metric.latency_ms}

        return jsonify(scores), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ingest", methods=["POST"])
def ingest_model():
    """Ingest and validate a HuggingFace model into the registry.

    Evaluates a HuggingFace model URL against quality thresholds and creates
    a package entry if all metrics pass. All non-latency metrics must score
    at least 0.5 to be accepted.

    Request Body (JSON):
        - url (str, required): HuggingFace model URL (must start with
          'https://huggingface.co/')

    Quality Thresholds (minimum 0.5):
        - license
        - ramp_up_time
        - bus_factor
        - dataset_and_code
        - dataset_quality
        - code_quality
        - performance

    Returns:
        tuple: JSON response and HTTP status code
            Success (201):
                - message (str): Success confirmation
                - package (dict): Created package with embedded scores
            Error (400): Invalid URL, missing URL, or failed quality threshold
            Error (500): Server error during ingestion or evaluation
    """
    try:
        data = request.get_json()
        if not data or "url" not in data:
            return jsonify({"error": "URL required"}), 400

        url = data["url"]

        if not url.startswith("https://huggingface.co/"):
            return jsonify({"error": "URL must be a HuggingFace model URL"}), 400

        try:
            model = Model(model=ModelResource(url=url))
            results = compute_all_metrics(model)
        except Exception as e:
            return jsonify({"error": f"Failed to evaluate model: {str(e)}"}), 500

        non_latency_metrics = [
            "license",
            "ramp_up_time",
            "bus_factor",
            "dataset_and_code",
            "dataset_quality",
            "code_quality",
            "performance",
        ]

        for metric_name in non_latency_metrics:
            if metric_name in results:
                metric = results[metric_name]
                score = metric.value if isinstance(metric.value, (int, float)) else 0
                if score < 0.5:
                    return jsonify(
                        {"error": f"Failed threshold: {metric_name} {score} < 0.5"}
                    ), 400

        parts = url.rstrip("/").split("/")
        model_name = parts[-1] if parts else "unknown"

        scores = {}
        for name, metric in results.items():
            scores[name] = {"score": metric.value, "latency_ms": metric.latency_ms}

        package_id = str(uuid.uuid4())
        package = Package(
            id=package_id,
            name=model_name,
            version="1.0.0",
            uploaded_by=DEFAULT_USERNAME,
            upload_timestamp=datetime.utcnow(),
            size_bytes=0,
            metadata={"url": url, "scores": scores},
            s3_key=None,
        )

        storage.create_package(package)

        return jsonify(
            {"message": "Model ingested successfully", "package": package.to_dict()}
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ingest/upload", methods=["POST"])
def ingest_upload():
    """Ingest packages from uploaded CSV or JSON file.

    Accepts a file upload (CSV or JSON format) containing package data.
    Validates and stores all packages from the file.

    File Format Requirements:

    CSV Format - Must include columns: name, version
    Optional columns: metadata (JSON string)
    Example:
        name,version,metadata
        package1,1.0.0,"{\"description\": \"test\"}"
        package2,2.0.0,"{\"key\": \"value\"}"

    JSON Format - Array of objects or single object
    Required fields: name, version
    Optional fields: metadata (object)
    Example:
        [
            {"name": "package1", "version": "1.0.0", "metadata": {"key": "value"}},
            {"name": "package2", "version": "2.0.0"}
        ]

    Request:
        - Content-Type: multipart/form-data
        - file: CSV or JSON file

    Returns:
        tuple: JSON response and HTTP status code
            Success (201):
                - message (str): Success confirmation
                - imported_count (int): Number of packages successfully imported
                - packages (list): List of created package details
            Error (400): No file, invalid format, validation errors
            Error (500): Server error during processing
    """
    try:
        # Check if file is in request
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        # Check if file has a filename
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        # Validate file extension
        allowed_extensions = {".csv", ".json"}
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            return jsonify(
                {
                    "error": f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
                }
            ), 400

        # Read file content
        file_content = file.read().decode("utf-8")

        packages_data = []

        # Parse based on file type
        if file_ext == ".csv":
            packages_data = parse_csv_content(file_content)
        elif file_ext == ".json":
            packages_data = parse_json_content(file_content)

        if not packages_data:
            return jsonify({"error": "No valid package data found in file"}), 400

        # Validate and create packages
        created_packages = []
        errors = []

        for idx, pkg_data in enumerate(packages_data):
            try:
                # Validate required fields - check for existence and non-empty values
                if not pkg_data.get("name") or not pkg_data.get("version"):
                    errors.append(
                        f"Row {idx + 1}: Missing required fields (name, version)"
                    )
                    continue

                # Create package
                package_id = str(uuid.uuid4())
                package = Package(
                    id=package_id,
                    name=pkg_data["name"],
                    version=pkg_data["version"],
                    uploaded_by=DEFAULT_USERNAME,
                    upload_timestamp=datetime.utcnow(),
                    size_bytes=0,
                    metadata=pkg_data.get("metadata", {}),
                    s3_key=None,
                )

                storage.create_package(package)
                created_packages.append(package.to_dict())

            except Exception as e:
                errors.append(f"Row {idx + 1}: {str(e)}")

        # Return response
        if not created_packages and errors:
            return jsonify({"error": "Failed to import any packages", "details": errors}), 400

        response = {
            "message": "Packages imported successfully",
            "imported_count": len(created_packages),
            "packages": created_packages,
        }

        if errors:
            response["warnings"] = errors

        return jsonify(response), 201

    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 500


def parse_csv_content(content: str) -> list:
    """Parse CSV content into list of package dictionaries.

    Args:
        content: CSV file content as string

    Returns:
        list: List of package dictionaries with name, version, metadata
    """
    packages = []
    csv_reader = csv.DictReader(io.StringIO(content))

    for row in csv_reader:
        pkg_data = {
            "name": row.get("name", "").strip(),
            "version": row.get("version", "").strip(),
        }

        # Parse metadata if present
        if "metadata" in row and row["metadata"] and row["metadata"].strip():
            try:
                pkg_data["metadata"] = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pkg_data["metadata"] = {}
        else:
            pkg_data["metadata"] = {}

        # Include all rows, even with missing fields (validation happens later)
        packages.append(pkg_data)

    return packages


def parse_json_content(content: str) -> list:
    """Parse JSON content into list of package dictionaries.

    Args:
        content: JSON file content as string

    Returns:
        list: List of package dictionaries with name, version, metadata
    """
    try:
        data = json.loads(content)

        # Handle single object
        if isinstance(data, dict):
            return [data]

        # Handle array of objects
        if isinstance(data, list):
            return data

        return []

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")


@app.route("/reset", methods=["DELETE"])
def reset_registry():
    """Reset the entire package registry.

    Removes all packages from the registry. This is a destructive operation
    that cannot be undone.

    Returns:
        tuple: JSON response and HTTP status code
            Success (200): Reset confirmation message
            Error (500): Server error during reset operation
    """
    try:
        storage.reset()
        return jsonify({"message": "Registry reset successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Frontend page routes
@app.route("/upload", methods=["GET"])
def upload_package_page():
    """Serve the upload package page.

    Returns:
        HTML: Upload package page
    """
    return render_template("upload.html")


@app.route("/ingest", methods=["GET"])
def ingest_page():
    """Serve the ingest model page.

    Returns:
        HTML: Ingest model page
    """
    return render_template("ingest.html")


@app.route("/health", methods=["GET"])
def health_dashboard():
    """Serve the health dashboard page or return JSON health data.

    Returns:
        HTML or JSON: Health dashboard page or health data
    """
    # Check if this is an API request (Accept: application/json)
    if request.headers.get("Accept", "").startswith("application/json"):
        return health()
    return render_template("health.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
