from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from datetime import datetime
import uuid
import os

from registry_models import Package
from storage import storage
from metrics_engine import compute_all_metrics
from metrics.net_score import NetScore
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

        storage.record_event(
            "package_uploaded",
            package=package,
            actor="api",
            details={
                "source": "direct_upload",
                "content_length": len(data.get("content", "")),
            },
        )

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
        deleted_package = storage.delete_package(package_id)
        if deleted_package is None:
            return jsonify({"error": "Package not found"}), 404

        storage.record_event(
            "package_deleted",
            package=deleted_package,
            actor="api",
            details={"source": "api"},
        )
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

        storage.record_event(
            "metrics_evaluated",
            package=package,
            actor="api",
            details={"metrics": list(scores.keys())},
        )

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
        All non-latency metrics computed via compute_all_metrics:
        - license
        - ramp_up_time
        - bus_factor
        - dataset_and_code_score
        - dataset_quality
        - code_quality
        - performance_claims
        - size_score (each device score must be >= 0.5: raspberry_pi, jetson_nano, desktop_pc, aws_server)
        - net_score (aggregate score computed from all metrics)

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

        # Compute net_score from all metrics
        net_score = NetScore()
        net_score.evaluate(list(results.values()))
        results[net_score.name] = net_score

        # Validate all non-latency metrics from the rate behavior
        # These are all metrics returned by compute_all_metrics plus net_score
        
        for metric_name, metric in results.items():
            
            # Handle size_score which is a dict of device scores
            if metric_name == "size_score":
                if isinstance(metric.value, dict) and len(metric.value) > 0:
                    # Check that each individual device score is >= 0.5
                    for device, score in metric.value.items():
                        if score < 0.5:
                            return jsonify(
                                {"error": f"Failed threshold: {metric_name}.{device} {score:.3f} < 0.5"}
                            ), 400
                else:
                    # Invalid size_score, fail
                    return jsonify(
                        {"error": f"Failed threshold: {metric_name} is invalid or empty"}
                    ), 400
            # Handle numeric metrics
            elif isinstance(metric.value, (int, float)):
                if metric.value < 0.5:
                    return jsonify(
                        {"error": f"Failed threshold: {metric_name} {metric.value:.3f} < 0.5"}
                    ), 400
            else:
                # Unknown metric type, fail for safety
                return jsonify(
                    {"error": f"Failed threshold: {metric_name} has invalid type"}
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

        storage.record_event(
            "model_ingested",
            package=package,
            actor="api",
            details={"source": "huggingface", "url": url},
        )

        return jsonify(
            {"message": "Model ingested successfully", "package": package.to_dict()}
        ), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        storage.record_event(
            "registry_reset",
            actor="api",
            details={"initiator": "dashboard"},
        )
        return jsonify({"message": "Registry reset successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health/activity", methods=["GET"])
def health_activity():
    """Return operational activity metrics for the requested window."""
    try:
        window_minutes = int(request.args.get("window", 60))
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return jsonify({"error": "Invalid window or limit parameter"}), 400

    window_minutes = max(1, min(window_minutes, 24 * 60))
    limit = max(1, min(limit, 200))

    summary = storage.get_activity_summary(
        window_minutes=window_minutes,
        event_limit=limit,
    )
    return jsonify(summary), 200


@app.route("/health/logs", methods=["GET"])
def health_logs():
    """Return recent operational log entries."""
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        return jsonify({"error": "Invalid limit parameter"}), 400

    limit = max(1, min(limit, 500))
    level = request.args.get("level")

    entries = storage.get_recent_logs(limit=limit, level=level)
    return jsonify({"entries": entries}), 200


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


@app.route("/dashboard/health", methods=["GET"])
def health_dashboard_redirect():
    """Backward-compatible alias for the health dashboard route."""
    return render_template("health.html")


@app.route("/health/dashboard", methods=["GET"])
def health_dashboard_legacy():
    """Serve the health dashboard page or return JSON health data.

    Returns:
        HTML or JSON: Health dashboard page or health data
    """
    return render_template("health.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
