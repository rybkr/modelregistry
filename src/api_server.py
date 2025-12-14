from flask import Flask, jsonify, request, render_template, Response, send_file
from flask_cors import CORS
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlparse, quote
from lineage import build_lineage_graph, compute_tree_score

import uuid
import os
import csv
import json
import io
import logging
import zipfile
import tempfile
import re
import time
import base64
import boto3
import threading
from botocore.exceptions import ClientError, NoCredentialsError, ReadTimeoutError, ConnectTimeoutError
from botocore.config import Config

from registry_models import Package
from storage import storage
from metrics_engine import compute_all_metrics
from metrics.net_score import NetScore
from models import Model
from resources.model_resource import ModelResource
from resources.dataset_resource import DatasetResource
from resources.code_resource import CodeResource

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("api_server")

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(SRC_DIR, "templates")
STATIC_DIR = os.path.join(SRC_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
CORS(app)


def load_config_from_repo(package):
    """Safely load config.json from a model repo. Returns dict or None."""
    try:
        url = package.metadata.get("url", "")
        if not url:
            return None

        model = Model(model=ModelResource(url=url))

        with model.model.open_files(allow_patterns=["config.json"]) as repo:
            if repo.exists("config.json"):
                return repo.read_json("config.json")

    except Exception as e:
        logger.warning(f"Failed to load config.json for {package.id}: {e}")

    return None


# Register JSON error handler to ensure API endpoints always return JSON
@app.errorhandler(404)
def not_found(error):
    """Return JSON 404 errors for API requests."""
    accept_header = request.headers.get("Accept", "")
    if request.path.startswith("/api/") or (
        request.path.startswith("/packages/") and "/rate" in request.path
    ):
        return jsonify({"error": "Not found"}), 404
    if "application/json" in accept_header:
        return jsonify({"error": "Not found"}), 404
    return error


@app.errorhandler(500)
def internal_error(error):
    """Return JSON 500 errors for API requests."""
    accept_header = request.headers.get("Accept", "")
    if request.path.startswith("/api/") or (
        request.path.startswith("/packages/") and "/rate" in request.path
    ):
        return jsonify({"error": "Internal server error"}), 500
    if "application/json" in accept_header:
        return jsonify({"error": "Internal server error"}), 500
    return error


DEFAULT_USERNAME = "ece30861defaultadminuser"

_valid_tokens = set()

DEFAULT_TOKEN = "bearer default-admin-token"

# S3 configuration for package content storage
# PACKAGE_STORAGE_BUCKET: S3 bucket name for storing package content (optional)
# If not set, packages are created without S3 keys (backward compatible)
# Package content is uploaded to S3 when the 'content' field is provided in package creation requests
_package_s3_bucket = os.environ.get("PACKAGE_STORAGE_BUCKET")
_package_s3_client = None

# Rate limiting for S3 uploads - ONE AT A TIME to prevent any stalling
_max_concurrent_s3_uploads = 1  # Only ONE upload at a time
_active_s3_uploads = 0
_s3_upload_lock = threading.Lock()


def initialize_default_token():
    """Initialize the default admin token for the reset/initial state.

    Per spec: In its initial and "Reset" state, the system must have a default user.
    This function ensures the default token is available.
    """
    _valid_tokens.add(DEFAULT_TOKEN)


def initialize_default_admin_user():
    """Initialize the default admin user in storage.

    Validates that the default admin user exists. The user should be created
    via S3 initialization or environment variable during storage initialization.
    This function serves as a validation check.
    """
    # Check if default user already exists
    existing_user = storage.get_user(DEFAULT_USERNAME)
    if existing_user:
        logger.info("Default admin user already exists")
        return
    
    logger.warning(
        f"Default admin user '{DEFAULT_USERNAME}' not found. "
        "It should be created during storage initialization from S3 or environment variable."
    )


def _get_package_s3_client():
    """Get or initialize S3 client for package content storage.
    
    Returns:
        boto3.client or None: S3 client if bucket is configured, None otherwise
    """
    global _package_s3_client
    
    if not _package_s3_bucket:
        return None
    
    if _package_s3_client is None:
        try:
            # Configure S3 client with ULTRA-AGGRESSIVE timeouts - NEVER STALL
            s3_config = Config(
                connect_timeout=1,  # 1 second max to connect
                read_timeout=3,     # 3 seconds max to read
                retries={
                    'max_attempts': 1,  # No retries - fail fast
                    'mode': 'standard'
                }
            )
            _package_s3_client = boto3.client('s3', config=s3_config)
            logger.info(f"S3 client initialized for package storage bucket: {_package_s3_bucket}")
        except (NoCredentialsError, Exception) as e:
            logger.warning(f"Failed to initialize S3 client for package storage: {e}")
            return None
    
    return _package_s3_client


def _decode_package_content(content: str) -> bytes:
    """Decode package content from string to bytes.
    
    Attempts to decode base64 if content appears to be base64-encoded.
    Otherwise treats as plain text and encodes to bytes.
    
    Args:
        content: Content string (may be base64-encoded or plain text)
        
    Returns:
        bytes: Decoded content as bytes
    """
    if not content:
        return b""
    
    # Try to decode as base64 first
    try:
        # Remove whitespace and check if it looks like base64
        content_clean = content.strip().replace('\n', '').replace('\r', '')
        if len(content_clean) > 0 and len(content_clean) % 4 == 0:
            decoded = base64.b64decode(content_clean, validate=True)
            logger.debug("Content decoded as base64")
            return decoded
    except Exception:
        # Not base64, treat as plain text
        pass
    
    # Treat as plain text and encode to bytes
    try:
        return content.encode('utf-8')
    except Exception as e:
        logger.warning(f"Failed to encode content to bytes: {e}")
        return content.encode('utf-8', errors='ignore')


def _upload_package_to_s3(package_id: str, content: bytes = None, metadata: dict = None) -> Optional[str]:
    """Upload package to S3 (non-blocking, rate-limited).
    
    Only uploads to S3 if there's available bandwidth (not too many concurrent uploads).
    If system is busy, skips S3 upload to prevent overwhelming the system.
    
    Args:
        package_id: Unique package identifier (UUID)
        content: Content bytes to upload (optional)
        metadata: Package metadata to store (optional)
        
    Returns:
        Optional[str]: S3 key if upload started, None if skipped due to rate limiting
    """
    s3_client = _get_package_s3_client()
    if not s3_client or not _package_s3_bucket:
        logger.warning(f"Package storage S3 bucket not configured or client unavailable. Bucket: {_package_s3_bucket}, Client: {s3_client is not None}")
        return None
    
    # Check if we have bandwidth for S3 upload (rate limiting - ONE AT A TIME)
    global _active_s3_uploads
    try:
        with _s3_upload_lock:
            if _active_s3_uploads >= _max_concurrent_s3_uploads:
                # Already one upload in progress, skip this one - NEVER STALL
                logger.debug(f"Skipping S3 upload for package {package_id}: upload already in progress (one at a time)")
                return None
            _active_s3_uploads += 1
    except Exception:
        # If lock fails for any reason, skip upload - NEVER STALL
        logger.warning(f"Lock error checking S3 upload status, skipping upload for package {package_id}")
        return None
    
    # Generate S3 key
    s3_key = f"packages/{package_id}/content"
    
    # Prepare data for background thread (copy to avoid reference issues)
    bucket_name = _package_s3_bucket
    key_name = s3_key
    if content and len(content) > 0:
        content_bytes = content
        content_type = "application/octet-stream"
        is_metadata = False
    else:
        content_bytes = json.dumps(metadata or {}, indent=2).encode('utf-8')
        content_type = "application/json"
        is_metadata = True
    
    def _do_upload():
        """Background thread function to perform S3 upload. NEVER STALLS."""
        global _active_s3_uploads
        try:
            # Get a fresh S3 client in the thread (thread-safe)
            thread_s3_client = _get_package_s3_client()
            if not thread_s3_client:
                return
            
            # Use aggressive timeout - fail fast if S3 is slow
            thread_s3_client.put_object(
                Bucket=bucket_name,
                Key=key_name,
                Body=content_bytes,
                ContentType=content_type
            )
            if is_metadata:
                logger.info(f"Package metadata uploaded to S3: {key_name} (metadata only, {len(content_bytes)} bytes)")
            else:
                logger.info(f"Package content uploaded to S3: {key_name} ({len(content_bytes)} bytes)")
        except (ReadTimeoutError, ConnectTimeoutError) as e:
            logger.warning(f"S3 upload timeout for package {package_id}: {e}. Continuing without S3 storage.")
        except ClientError as e:
            logger.error(f"Failed to upload package to S3: {e}")
        except Exception as e:
            logger.error(f"Unexpected error uploading package to S3: {e}")
        finally:
            # ALWAYS decrement counter - even on exception - to prevent deadlock
            try:
                with _s3_upload_lock:
                    _active_s3_uploads = max(0, _active_s3_uploads - 1)
            except Exception:
                # If lock fails, force reset (should never happen but safety)
                _active_s3_uploads = 0
    
    # Start upload in background thread (daemon so it doesn't block shutdown)
    thread = threading.Thread(target=_do_upload, daemon=True)
    thread.start()
    
    # Return immediately with the expected s3_key
    return s3_key


def check_auth_header():
    """Check if X-Authorization header is present and token is valid.

    Per OpenAPI spec, X-Authorization header is required for certain endpoints.
    Validates header presence and token validity using new storage-based token system.
    Falls back to old _valid_tokens set for backward compatibility.

    Returns:
        tuple: (is_valid, error_response, user_info)
            - is_valid (bool): True if header present and token valid, False otherwise
            - error_response (Optional[tuple]): (json_response, status_code) if invalid, None if valid
            - user_info (Optional[dict]): User info if authenticated, None otherwise
    """
    auth_header = request.headers.get("X-Authorization")
    logger.info(f"check_auth_header called, header present: {auth_header is not None}")

    if not auth_header:
        logger.warning("Auth failed: no X-Authorization header")
        return (
            False,
            (
                jsonify(
                    {
                        "error": "Authentication failed due to invalid or missing AuthenticationToken"
                    }
                ),
                403,
            ),
            None,
        )

    token_value = auth_header.strip().strip('"').strip("'")

    # Check new storage-based token system first
    token_info = storage.get_token(token_value)
    if token_info:
        # Valid token from new system
        storage.increment_token_usage(token_value)
        user = storage.get_user_by_id(token_info.user_id)
        user_info = {
            "username": token_info.username,
            "user_id": token_info.user_id,
            "is_admin": user.is_admin if user else False,
            "permissions": user.permissions if user else [],
        }
        logger.info(f"Token valid (new system): user={token_info.username}")
        return True, None, user_info

    # Fall back to old token system for backward compatibility
    is_default = token_value == DEFAULT_TOKEN
    is_in_valid_set = token_value in _valid_tokens

    logger.info(
        f"Token validation: is_default={is_default}, is_in_valid_set={is_in_valid_set}, valid_tokens_count={len(_valid_tokens)}"
    )

    if not is_default and not is_in_valid_set:
        logger.warning(f"Auth failed: token not recognized")
        return (
            False,
            (
                jsonify(
                    {
                        "error": "Authentication failed due to invalid or missing AuthenticationToken"
                    }
                ),
                403,
            ),
            None,
        )

    # Old system - assume default admin permissions
    user_info = {
        "username": DEFAULT_USERNAME,
        "user_id": "default",
        "is_admin": True,
        "permissions": ["upload", "search", "download", "admin"],
    }

    return True, None, user_info


def check_permission(user_info: dict, required_permission: str) -> tuple:
    """Check if user has the required permission.

    Args:
        user_info: User information dict from check_auth_header()
        required_permission: Permission to check ('upload', 'search', 'download', 'admin')

    Returns:
        tuple: (has_permission, error_response)
            - has_permission (bool): True if user has permission
            - error_response (Optional[tuple]): (json_response, status_code) if denied, None if allowed
    """
    if not user_info:
        return False, (
            jsonify(
                {
                    "error": "Authentication failed due to invalid or missing AuthenticationToken"
                }
            ),
            403,
        )

    # Admin users have all permissions
    if user_info.get("is_admin", False):
        return True, None

    # Check if user has the specific permission
    user_permissions = user_info.get("permissions", [])
    if required_permission in user_permissions:
        return True, None

    # Permission denied
    logger.warning(
        f"Permission denied: user={user_info.get('username')} lacks '{required_permission}' permission"
    )
    return False, (
        jsonify({"error": f"You do not have permission to {required_permission}"}),
        403,
    )


def infer_artifact_type_from_url(url: str) -> str:
    """Infer artifact type from URL.

    Args:
        url: The artifact source URL

    Returns:
        str: "model", "dataset", or "code"
    """
    if "huggingface.co/datasets/" in url:
        return "dataset"
    elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
        return "code"
    return "model"


def infer_artifact_type(package: Package) -> str:
    """Infer artifact type from package URL or metadata.

    Args:
        package: Package to infer type from

    Returns:
        str: "model", "dataset", or "code" (default: "model")
    """
    url = package.metadata.get("url", "")
    return infer_artifact_type_from_url(url)


def package_to_artifact_metadata(
    package: Package, artifact_type: Optional[str] = None
) -> dict:
    """Convert Package to ArtifactMetadata format.

    Args:
        package: Package to convert
        artifact_type: Optional type override

    Returns:
        dict: ArtifactMetadata {name, id, type}
    """
    if artifact_type is None:
        artifact_type = infer_artifact_type(package)
    return {"name": package.name, "id": package.id, "type": artifact_type}


def package_to_artifact(package: Package, artifact_type: Optional[str] = None) -> dict:
    """Convert Package to Artifact format.

    Args:
        package: Package to convert
        artifact_type: Optional type override

    Returns:
        dict: Artifact {metadata: {...}, data: {url, download_url?}}
    """
    url = package.metadata.get("url", "")
    artifact_data = {"url": url}

    # Construct download_url in the format expected by autograder: {host}/download/{artifact_name}
    try:
        # Use request context to get the host and construct download URL
        base_url = request.url_root.rstrip("/")
        # URL-encode package name, preserving hyphens but encoding other special chars
        artifact_name = package.name or ""
        encoded_name = quote(artifact_name, safe="-") if artifact_name else ""
        artifact_data["download_url"] = f"{base_url}/download/{encoded_name}"
    except RuntimeError:
        # Fallback if request context is not available (e.g., in tests)
        if url:
            artifact_data["download_url"] = url
        elif "download_url" in package.metadata:
            artifact_data["download_url"] = package.metadata["download_url"]

    return {
        "metadata": package_to_artifact_metadata(package, artifact_type),
        "data": artifact_data,
    }


def validate_artifact_type(artifact_type: str) -> bool:
    """Validate artifact type is one of: model, dataset, code.

    Args:
        artifact_type: Type to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return artifact_type in {"model", "dataset", "code"}


def validate_artifact_id(artifact_id: str) -> bool:
    """Validate artifact ID matches pattern ^[a-zA-Z0-9-]+$.

    Args:
        artifact_id: ID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    return bool(re.match(r"^[a-zA-Z0-9\-]+$", artifact_id))


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


# ================================ ROUTES ====================================


@app.route("/", methods=["GET"])
def index():
    """Serve the main package listing page or API info.

    Returns:
        HTML or JSON: Package listing page for browsers, API info for API requests
    """
    accept_header = request.headers.get("Accept", "")
    wants_html = (
        "text/html" in accept_header
        and "application/json" not in accept_header
        and accept_header != "*/*"
        and accept_header != ""
    )

    if wants_html:
        return render_template("index.html")
    else:
        return jsonify({"message": "Model Registry API v0.1.0", "status": "ok"}), 200


@app.route("/api", methods=["GET"])
def api_root():
    """Return basic API information.

    Provides version and status information for the Model Registry API.

    Returns:
        tuple: JSON response with API metadata and 200 status code
            - message (str): API version identifier
            - status (str): API running status
    """
    return jsonify({"message": "Model Registry API v0.1.0", "status": "ok"}), 200


@app.route("/api/health", methods=["GET"])
def health():
    """Check the health status of the Model Registry API.

    Returns health information including server status, current timestamp,
    and the total number of packages in the registry.

    Returns:
        tuple: JSON response with health data and 200 status code
            - status (str): Health status, always "healthy" if endpoint responds
            - timestamp (str): Current UTC timestamp in ISO format
            - packages_count (int): Total number of packages in the registry
    """
    # Ultra-fast health check - just verify storage is accessible
    # Don't count packages (can be slow with many packages)
    try:
        # Just verify storage object exists and is accessible
        _ = storage.packages
        packages_count = len(storage.packages)  # Direct access, no method call overhead
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify(
            {
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
        ), 503
    
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "packages_count": packages_count,
        }
    ), 200


@app.route("/api/health/logs", methods=["GET"])
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


@app.route("/api/health/activity", methods=["GET"])
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


@app.route("/api/packages", methods=["GET", "POST"])
def packages():
    """Handle GET and POST requests for packages.

    GET: Get packages with optional search and pagination.
    POST: Create a new package.
    """
    if request.method == "GET":
        return get_packages()
    else:
        return create_package()


def get_packages():
    """Get packages with optional search and pagination.

    Query parameters:
        offset: Pagination offset (default: 0)
        limit: Maximum number of packages to return (default: 25)
        query: Search query string (optional)
        regex: If 'true', treat query as regex pattern (default: false)
        version: Filter by version (optional)
        sort-field: Field to sort by (optional)
        sort-order: Sort order 'asc' or 'desc' (optional)

    Returns:
        tuple: JSON response with packages, total, offset, limit
    """
    logger.info("get_packages called")

    # Get query parameters
    offset_str = request.args.get("offset", "0")
    limit_str = request.args.get("limit", "25")
    query = request.args.get("query", "").strip()
    use_regex = request.args.get("regex", "false").lower() == "true"
    version = request.args.get("version", "").strip()
    sort_field = request.args.get("sort-field", "").strip()
    sort_order = request.args.get("sort-order", "").strip()

    try:
        offset = int(offset_str)
        limit = int(limit_str)
    except ValueError:
        return jsonify({"error": "Invalid offset or limit parameter"}), 400

    # Get all packages or search
    if query:
        packages = storage.search_packages(query, use_regex=use_regex)
    else:
        packages = list(storage.packages.values())

    # Filter by version if specified
    if version:
        packages = [pkg for pkg in packages if pkg.version == version]

    # Sort if specified
    if sort_field:
        reverse = sort_order.lower() == "desc"
        try:
            if sort_field == "name":
                packages.sort(key=lambda p: p.name.lower(), reverse=reverse)
            elif sort_field == "version":
                packages.sort(key=lambda p: p.version, reverse=reverse)
            elif sort_field == "upload_timestamp":
                packages.sort(key=lambda p: p.upload_timestamp, reverse=reverse)
            elif sort_field == "size_bytes":
                packages.sort(key=lambda p: p.size_bytes, reverse=reverse)
        except Exception as e:
            logger.warning(f"Sort failed: {e}")

    total = len(packages)

    # Apply pagination
    paginated_packages = packages[offset : offset + limit]

    # Convert to dict format expected by frontend
    packages_data = []
    for package in paginated_packages:
        packages_data.append(
            {
                "id": package.id,
                "name": package.name,
                "version": package.version,
                "uploaded_by": package.uploaded_by,
                "upload_timestamp": package.upload_timestamp.isoformat(),
                "size_bytes": package.size_bytes,
                "metadata": package.metadata,
            }
        )

    response = {
        "packages": packages_data,
        "total": total,
        "offset": offset,
        "limit": limit,
    }

    return jsonify(response), 200


def create_package():
    """Create a new package.

    Request body:
        name: Package name (required)
        version: Package version (required)
        content: Package content (optional)
        metadata: Additional metadata dict (optional)

    Returns:
        tuple: JSON response with package data, 201
    """
    logger.info("create_package called")

    # Check authentication
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        logger.warning("Upload failed: authentication check failed")
        return error_response

    # Check upload permission
    has_permission, permission_error = check_permission(user_info, "upload")
    if not has_permission:
        logger.warning(f"Upload failed: permission denied for user={user_info.get('username')}")
        return permission_error

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate required fields
    name = data.get("name", "").strip()
    version = data.get("version", "").strip()

    if not name:
        return jsonify({"error": "Package name is required"}), 400
    if not version:
        return jsonify({"error": "Package version is required"}), 400

    # Get optional fields
    content = data.get("content", "")
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        return jsonify({"error": "metadata must be a dictionary"}), 400

    # Generate package ID
    package_id = str(uuid.uuid4())

    # Always upload package to S3 (with content if provided, or metadata if not)
    s3_key = None
    content_length = len(content) if content else 0
    logger.info(f"Package creation: name={name}, version={version}, content_length={content_length}, has_content={bool(content)}")
    
    try:
        content_bytes = None
        if content:
            content_bytes = _decode_package_content(content)
        
        # Always upload to S3 (content if available, metadata otherwise)
        s3_key = _upload_package_to_s3(package_id, content_bytes, metadata)
        if not s3_key:
            logger.warning(f"Failed to upload package to S3 for package {package_id}, continuing without S3 storage")
    except Exception as e:
        logger.error(f"Error uploading package to S3: {e}, continuing without S3 storage")

    # Calculate size_bytes from content
    size_bytes = len(content.encode("utf-8")) if content else 0

    # Infer artifact type from metadata URL
    artifact_type = "model"  # default
    if metadata and "url" in metadata:
        artifact_type = infer_artifact_type_from_url(metadata["url"])

    # Create package
    package = Package(
        id=package_id,
        artifact_type=artifact_type,
        name=name,
        version=version,
        uploaded_by=DEFAULT_USERNAME,
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=size_bytes,
        metadata=metadata,
        s3_key=s3_key,
    )

    # Store package
    storage.create_package(package)

    logger.info(f"Package created: {package_id} ({name} v{version})")

    # Return package data in format expected by frontend
    return jsonify({"package": package.to_dict()}), 201


@app.route("/packages/<package_id>", methods=["GET"])
@app.route("/api/packages/<package_id>", methods=["GET"])
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
    accept_header = request.headers.get("Accept", "")

    # Return HTML only if explicitly requesting HTML
    wants_html = (
        "text/html" in accept_header and "application/json" not in accept_header
    )

    package = storage.get_package(package_id)
    if not package:
        if wants_html:
            return render_template("404.html"), 404
        return jsonify({"error": "Package not found"}), 404

    if wants_html:
        return render_template("package_detail.html", package=package)

    return jsonify(package.to_dict()), 200


@app.route("/packages/<package_id>/rate", methods=["GET"])
@app.route("/api/packages/<package_id>/rate", methods=["GET"])
def rate_package(package_id):
    """Calculate and return quality metrics for a package.

    Request body: {github_url: string}

    Returns:
        tuple: (boolean JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(package_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    github_url = data.get("github_url", "")
    if not github_url:
        return jsonify({"error": "github_url required in request body"}), 400

    package = storage.get_package(package_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    try:
        url = package.metadata.get("url", "")
        if not url:
            return jsonify({"error": "No URL in package metadata"}), 400

        model = Model(model=ModelResource(url=url))
        results = compute_all_metrics(model)
        license_metric = results.get("license")

        if license_metric:
            is_compatible = license_metric.value > 0.5
            return jsonify(is_compatible), 200
        else:
            return jsonify(False), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/artifacts", methods=["POST"])
def list_artifacts():
    """List artifacts matching query criteria.

    Request Body: Array of ArtifactQuery objects
    Query Param: offset (string, optional)
    Response Header: offset (string)

    Returns:
        tuple: (JSON array of ArtifactMetadata, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        logger.warning("list_artifacts: auth check failed")
        return error_response

    # Check search permission
    has_permission, permission_error = check_permission(user_info, "search")
    if not has_permission:
        return permission_error

    queries = request.get_json()
    logger.info(f"queries: {queries}")
    if not isinstance(queries, list) or len(queries) == 0:
        return jsonify(
            {
                "description": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."
            }
        ), 400

    for idx, query in enumerate(queries):
        if not isinstance(query, dict):
            return jsonify(
                {
                    "description": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."
                }
            ), 400
        if "name" not in query:
            return jsonify(
                {
                    "description": "There is missing field(s) in the artifact_query or it is formed improperly, or is invalid."
                }
            ), 400

    offset_str = request.args.get("offset", "0")
    try:
        offset = int(offset_str)
    except ValueError:
        return jsonify({"error": "Invalid offset parameter"}), 400

    artifact_types = None
    for query in queries:
        if isinstance(query, dict) and "types" in query:
            query_types = query.get("types")
            if isinstance(query_types, list) and len(query_types) > 0:
                if artifact_types is None:
                    artifact_types = []
                for query_type in query_types:
                    if query_type and query_type not in artifact_types:
                        artifact_types.append(query_type)

    try:
        packages, total_count = storage.get_artifacts_by_query(
            queries, artifact_types=artifact_types, offset=offset, limit=100
        )

        artifacts = []
        for package in packages:
            pkg_type = infer_artifact_type(package)
            artifacts.append(package_to_artifact_metadata(package, pkg_type))

        next_offset = (
            offset + len(packages) if offset + len(packages) < total_count else None
        )
        offset_header = str(next_offset) if next_offset is not None else ""

        response = jsonify(artifacts)
        if offset_header:
            response.headers["offset"] = offset_header
        if len(artifacts) > 100:
            return jsonify({"error": "Too many results"}), 413
        logger.info(f"artifacts: {artifacts}")
        return response, 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/artifacts/<artifact_type>/<artifact_id>", methods=["GET"])
def get_artifact(artifact_type, artifact_id):
    """Retrieve artifact by type and ID.

    Returns:
        tuple: (Artifact JSON, 200) or error response
    """
    logger.info(f"get_artifact called: id={artifact_id} type={artifact_type}")

    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check search permission
    has_permission, permission_error = check_permission(user_info, "search")
    if not has_permission:
        return permission_error

    if not validate_artifact_type(artifact_type):
        return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_artifact_by_type_and_id(artifact_type, artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    artifact = package_to_artifact(package, artifact_type)
    logger.info(f"returning: artifact={artifact}")
    return jsonify(artifact), 200


@app.route("/api/artifacts/<artifact_type>/<artifact_id>", methods=["PUT"])
def update_artifact(artifact_type, artifact_id):
    """Update artifact content.

    Request body must match path params (name and id).

    Returns:
        tuple: (200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_type(artifact_type):
        return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400
    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    metadata = data.get("metadata", {})
    if metadata.get("id") != artifact_id:
        return jsonify(
            {"error": "Artifact ID in body does not match path parameter"}
        ), 400

    if metadata.get("name") and metadata.get("name") != artifact_id:
        pass

    if metadata.get("type") != artifact_type:
        return jsonify(
            {"error": "Artifact type in body does not match path parameter"}
        ), 400

    package = storage.get_artifact_by_type_and_id(artifact_type, artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    artifact_data = data.get("data", {})
    if "url" in artifact_data:
        package.metadata["url"] = artifact_data["url"]
    if "download_url" in artifact_data:
        package.metadata["download_url"] = artifact_data["download_url"]

    if "name" in metadata:
        package.name = metadata["name"]

    storage.create_package(package)
    return jsonify({}), 200


@app.route("/api/artifacts/<artifact_type>/<artifact_id>", methods=["DELETE"])
def delete_artifact(artifact_type, artifact_id):
    """Delete an artifact from the registry.

    Uses only path parameters (artifact_type and artifact_id) to identify and delete the artifact.
    No request body is required.

    Args:
        artifact_type: Type of artifact (model, dataset, or code)
        artifact_id: Unique identifier for the artifact

    Returns:
        tuple: (200) on success, or error response (400/403/404)
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_type(artifact_type):
        return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400
    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_artifact_by_type_and_id(artifact_type, artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    storage.delete_package(package.id)
    return jsonify({}), 200


@app.route("/api/artifact/<artifact_type>", methods=["POST"])
def create_artifact(artifact_type):
    """Create new artifact from URL.

    Returns:
        tuple: (Artifact JSON, 201/202/424) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check upload permission
    has_permission, permission_error = check_permission(user_info, "upload")
    if not has_permission:
        return permission_error

    if not validate_artifact_type(artifact_type):
        return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400

    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "URL required in request body"}), 400
    logger.info(f"artifact data: {data}")

    url = data["url"]
    artifact_name = data["name"]

    # Check if artifact already exists (by URL)
    for package in storage.packages.values():
        if package.metadata.get("url") == url:
            return jsonify({"error": "Artifact with this URL already exists"}), 409

    # Ingest and compute metrics (similar to /api/ingest)
    try:
        if artifact_type == "dataset":
            # Must be a dataset
            dataset = DatasetResource(url=url)
            scores = {}
        elif artifact_type == "code":
            code = CodeResource(url=url)
            scores = {}
        else:
            model = Model(model=ModelResource(url=url))
            results = compute_all_metrics(model)
            # Compute net_score
            net_score = NetScore()
            net_score.evaluate(list(results.values()))
            results[net_score.name] = net_score

            # Extract artifact name from URL
            parts = url.rstrip("/").split("/")

            # Store scores
            scores = {}
            for name, metric in results.items():
                scores[name] = {"score": metric.value, "latency_ms": metric.latency_ms}

    except Exception as e:
        # If rating fails, return 424
        return jsonify({"error": f"Failed to compute metrics: {str(e)}"}), 424
    # Create package

    package_id = str(uuid.uuid4())
    
    # Always upload package to S3 (metadata only for URL-based packages)
    metadata = {"url": url, "scores": scores}
    s3_key = _upload_package_to_s3(package_id, None, metadata)
    if not s3_key:
        logger.warning(f"Failed to upload package to S3 for package {package_id}, continuing without S3 storage")
    
    package = Package(
        id=package_id,
        artifact_type=artifact_type,
        name=artifact_name,
        version="1.0.0",
        uploaded_by=DEFAULT_USERNAME,
        upload_timestamp=datetime.now(timezone.utc),
        size_bytes=0,
        metadata=metadata,
        s3_key=s3_key,
    )

    storage.create_package(package)

    storage.record_event(
        "model_ingested",
        package=package,
        actor="api",
        details={"source": "artifact_create", "url": url, "type": artifact_type},
    )

    # Convert to Artifact format
    artifact = package_to_artifact(package, artifact_type)
    return jsonify(artifact), 201


@app.route("/api/artifact/model/<artifact_id>/rate", methods=["GET"])
def get_model_rating(artifact_id):
    """Get rating metrics for model artifact.

    Returns:
        tuple: (ModelRating JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    url = package.metadata.get("url")
    if not url:
        return jsonify({"error": "No URL in package metadata"}), 400

    # Compute metrics if not already computed
    scores = package.metadata.get("scores", {})
    if not scores:
        try:
            model = Model(model=ModelResource(url=url))
            results = compute_all_metrics(model)
            net_score = NetScore()
            net_score.evaluate(list(results.values()))
            results[net_score.name] = net_score

            scores = {}
            for name, metric in results.items():
                scores[name] = {"score": metric.value, "latency_ms": metric.latency_ms}

            # Update package with scores
            package.metadata["scores"] = scores
            storage.create_package(package)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Convert to ModelRating format
    def get_metric_value(metric_name: str) -> tuple[float, float]:
        """Extract metric value and latency in seconds."""
        metric_data = scores.get(metric_name, {})
        score = metric_data.get("score", 0.0)
        latency_ms = metric_data.get("latency_ms", 0.0)

        # Ensure score is a valid float (handle None, preserve negative values like -1.0 for reviewedness)
        if score is None:
            score = 0.0
        else:
            try:
                score = float(score)
                # Preserve negative values (e.g., -1.0 for reviewedness on error)
                # Don't clamp to 0.0 as some metrics use -1.0 to indicate computation failure
            except (TypeError, ValueError):
                score = 0.0

        # Ensure latency is a valid float
        if latency_ms is None:
            latency_ms = 0.0
        else:
            try:
                latency_ms = float(latency_ms)
                if latency_ms < 0.0:
                    latency_ms = 0.0
            except (TypeError, ValueError):
                latency_ms = 0.0

        latency_seconds = latency_ms / 1000.0
        return score, latency_seconds

    # Extract all metric values and latencies
    net_score_val, net_score_latency = get_metric_value("net_score")
    ramp_up_time_val, ramp_up_time_latency = get_metric_value("ramp_up_time")
    bus_factor_val, bus_factor_latency = get_metric_value("bus_factor")
    performance_claims_val, performance_claims_latency = get_metric_value(
        "performance_claims"
    )
    license_val, license_latency = get_metric_value("license")
    dataset_and_code_score_val, dataset_and_code_score_latency = get_metric_value(
        "dataset_and_code_score"
    )
    dataset_quality_val, dataset_quality_latency = get_metric_value("dataset_quality")
    code_quality_val, code_quality_latency = get_metric_value("code_quality")
    size_score_val, size_score_latency = get_metric_value("size_score")
    reviewedness_val, reviewedness_latency = get_metric_value("reviewedness")

    # Handle size_score - must be a dict with device scores
    size_score_obj = size_score_val if isinstance(size_score_val, dict) else {}
    if not isinstance(size_score_obj, dict) or not all(
        key in size_score_obj
        for key in ["raspberry_pi", "jetson_nano", "desktop_pc", "aws_server"]
    ):
        size_score_obj = {
            "raspberry_pi": 1.0,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0,
        }

    tree_score_start = time.perf_counter()

    graph = build_lineage_graph(
        artifact_id,
        storage.list_packages(0, 10000),
        load_config_from_repo,
    )

    tree_score_val = compute_tree_score(
        artifact_id,
        graph,
        lambda pid: (
            storage.get_package(pid)
            .metadata.get("scores", {})
            .get("net_score", {})
            .get("score", 0.0)
            if storage.get_package(pid)
            else 0.0
        ),
    )

    tree_score_latency = time.perf_counter() - tree_score_start
    print("TREEEEEEEEEE", tree_score_val)

    reproducibility_val = 0.0
    reproducibility_latency = 0.0

    # Build complete ModelRating response with all required fields
    rating = {
        "name": package.name,
        "category": "MODEL",
        "net_score": net_score_val,
        "net_score_latency": net_score_latency,
        "ramp_up_time": ramp_up_time_val,
        "ramp_up_time_latency": ramp_up_time_latency,
        "bus_factor": bus_factor_val,
        "bus_factor_latency": bus_factor_latency,
        "performance_claims": performance_claims_val,
        "performance_claims_latency": performance_claims_latency,
        "license": license_val,
        "license_latency": license_latency,
        "dataset_and_code_score": dataset_and_code_score_val,
        "dataset_and_code_score_latency": dataset_and_code_score_latency,
        "dataset_quality": dataset_quality_val,
        "dataset_quality_latency": dataset_quality_latency,
        "code_quality": code_quality_val,
        "code_quality_latency": code_quality_latency,
        "size_score": size_score_obj,
        "size_score_latency": size_score_latency,
        "reproducibility": reproducibility_val,
        "reproducibility_latency": reproducibility_latency,
        "reviewedness": reviewedness_val,
        "reviewedness_latency": reviewedness_latency,
        "tree_score": tree_score_val,
        "tree_score_latency": tree_score_latency,
    }

    return jsonify(rating), 200


def get_artifact_dependencies(artifact_type: str, artifact_id: str) -> list[Package]:
    """Get all dependency packages for an artifact.

    For models, uses lineage information. For other types, returns empty list.

    Args:
        artifact_type: Type of artifact
        artifact_id: ID of artifact

    Returns:
        List of dependency packages
    """
    if artifact_type != "model":
        # Lineage/dependencies only available for models
        return []

    package = storage.get_package(artifact_id)
    if not package:
        return []

    url = package.metadata.get("url", "")
    if not url:
        return []

    dependencies = []

    try:
        model = Model(model=ModelResource(url=url))

        # Try to read config.json to extract lineage information
        try:
            with model.model.open_files(allow_patterns=["config.json"]) as repo:
                if repo.exists("config.json"):
                    config = repo.read_json("config.json")

                    # Extract base model information
                    base_model_path = None
                    if "_name_or_path" in config:
                        base_model_path = config["_name_or_path"]
                    elif "base_model" in config:
                        base_model_path = config["base_model"]

                    # Search for base model in storage
                    if base_model_path:
                        base_model_id = base_model_path
                        if "huggingface.co" in base_model_path.lower():
                            parsed = urlparse(base_model_path)
                            path_parts = [
                                x for x in parsed.path.strip("/").split("/") if x
                            ]
                            if len(path_parts) >= 2:
                                base_model_id = f"{path_parts[0]}/{path_parts[1]}"
                            elif len(path_parts) == 1:
                                base_model_id = path_parts[0]
                        elif "/" in base_model_path:
                            base_model_id = base_model_path
                        else:
                            base_model_id = base_model_path

                        found_parent = None
                        all_packages = storage.list_packages(offset=0, limit=10000)
                        for pkg in all_packages:
                            if pkg.id == artifact_id:
                                continue  # Skip self

                            pkg_url = pkg.metadata.get("url", "")
                            pkg_name = pkg.name.lower()

                            pkg_model_id = None
                            if pkg_url and "huggingface.co" in pkg_url.lower():
                                parsed = urlparse(pkg_url)
                                path_parts = [
                                    x for x in parsed.path.strip("/").split("/") if x
                                ]
                                if len(path_parts) >= 2:
                                    pkg_model_id = f"{path_parts[0]}/{path_parts[1]}"
                                elif len(path_parts) == 1:
                                    pkg_model_id = path_parts[0]

                            if (
                                pkg_model_id
                                and base_model_id.lower() == pkg_model_id.lower()
                            ):
                                found_parent = pkg
                                break

                            if (
                                "/" not in base_model_id
                                and pkg_name
                                and base_model_id.lower() == pkg_name
                            ):
                                found_parent = pkg
                                break

                            base_model_name = (
                                base_model_id.split("/")[-1].lower()
                                if "/" in base_model_id
                                else base_model_id.lower()
                            )
                            if (
                                pkg_url
                                and base_model_name in pkg_url.lower()
                                and "huggingface.co" in pkg_url.lower()
                            ):
                                if base_model_name in pkg_url.lower().split("/")[-1]:
                                    found_parent = pkg
                                    break

                        if found_parent:
                            dependencies.append(found_parent)

                    # Check for dataset information in config
                    dataset_name = None
                    if "dataset" in config:
                        dataset_name = config["dataset"]
                    elif "train_dataset" in config:
                        dataset_name = config["train_dataset"]

                    if dataset_name:
                        dataset_id = dataset_name
                        if "huggingface.co" in dataset_name.lower():
                            parsed = urlparse(dataset_name)
                            path_parts = [
                                x for x in parsed.path.strip("/").split("/") if x
                            ]
                            if path_parts and path_parts[0] == "datasets":
                                path_parts = path_parts[1:]
                            if len(path_parts) >= 2:
                                dataset_id = f"{path_parts[0]}/{path_parts[1]}"
                            elif len(path_parts) == 1:
                                dataset_id = path_parts[0]

                        all_packages = storage.list_packages(offset=0, limit=10000)
                        for pkg in all_packages:
                            if pkg.id == artifact_id:
                                continue  # Skip self

                            pkg_url = pkg.metadata.get("url", "")
                            pkg_name = pkg.name.lower()

                            if "huggingface.co/datasets/" in pkg_url.lower():
                                parsed = urlparse(pkg_url)
                                path_parts = [
                                    x for x in parsed.path.strip("/").split("/") if x
                                ]
                                if path_parts and path_parts[0] == "datasets":
                                    path_parts = path_parts[1:]
                                pkg_dataset_id = None
                                if len(path_parts) >= 2:
                                    pkg_dataset_id = f"{path_parts[0]}/{path_parts[1]}"
                                elif len(path_parts) == 1:
                                    pkg_dataset_id = path_parts[0]

                                dataset_id_lower = dataset_id.lower()
                                if (
                                    pkg_dataset_id
                                    and dataset_id_lower == pkg_dataset_id.lower()
                                ):
                                    dependencies.append(pkg)
                                    break

                                if (
                                    "/" not in dataset_id
                                    and dataset_id_lower == pkg_name
                                ):
                                    dependencies.append(pkg)
                                    break
        except Exception as e:
            logger.warning(f"Could not read config.json for dependencies: {str(e)}")
    except Exception as e:
        logger.warning(f"Error getting dependencies: {str(e)}")

    return dependencies


@app.route("/api/artifact/<artifact_type>/<artifact_id>/cost", methods=["GET"])
def get_artifact_cost(artifact_type, artifact_id):
    """Get artifact cost in MB.

    Query param: dependency (boolean, default false)

    Returns:
        tuple: (ArtifactCost JSON, 200) or error response
        Format when dependency=false: {"artifact_id": {"total_cost": value}}
        Format when dependency=true: {"artifact_id": {"standalone_cost": value, "total_cost": value}, ...}
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_type(artifact_type):
        return jsonify({"error": f"Invalid artifact type: {artifact_type}"}), 400

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    try:
        package = storage.get_artifact_by_type_and_id(artifact_type, artifact_id)
        if not package:
            return jsonify({"error": "Artifact not found"}), 404

        dependency = request.args.get("dependency", "false").lower() == "true"

        # Calculate cost in MB (size_bytes / (1024 * 1024))
        def calculate_cost_mb(size_bytes: int) -> float:
            """Convert size in bytes to cost in MB."""
            return round(size_bytes / (1024 * 1024), 2) if size_bytes > 0 else 0.0

        standalone_cost = calculate_cost_mb(package.size_bytes)

        if not dependency:
            # Return only total_cost for the artifact itself
            return jsonify({artifact_id: {"total_cost": standalone_cost}}), 200

        # When dependency=true, include all dependencies
        dependencies = get_artifact_dependencies(artifact_type, artifact_id)

        # Build cost map for all artifacts (self + dependencies)
        cost_map = {}

        # Add self
        total_cost = standalone_cost
        for dep in dependencies:
            dep_cost = calculate_cost_mb(dep.size_bytes)
            total_cost += dep_cost

        cost_map[artifact_id] = {
            "standalone_cost": standalone_cost,
            "total_cost": round(total_cost, 2),
        }

        # Add dependencies
        for dep in dependencies:
            dep_standalone = calculate_cost_mb(dep.size_bytes)
            # For dependencies, total_cost is just their standalone cost
            # (they don't include their own dependencies in this calculation)
            cost_map[dep.id] = {
                "standalone_cost": dep_standalone,
                "total_cost": dep_standalone,
            }

        return jsonify(cost_map), 200
    except Exception as e:
        logger.error(f"Error calculating artifact cost: {str(e)}")
        return jsonify(
            {"error": "The artifact cost calculator encountered an error."}
        ), 500


@app.route("/api/artifact/model/<artifact_id>/lineage", methods=["GET"])
def get_artifact_lineage(artifact_id):
    """Get lineage graph for model artifact.

    Extracts lineage information from model's config.json and recursively
    traverses all parent dependencies to build a complete lineage graph.

    Returns:
        tuple: (ArtifactLineageGraph JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    url = package.metadata.get("url", "")
    if not url:
        return jsonify({"error": "No URL in package metadata"}), 400

    try:
        # Get all packages for lineage graph construction
        all_packages = storage.list_packages(offset=0, limit=10000)
        
        # CRITICAL: Ensure root package is in the list
        if package not in all_packages:
            # Find it by ID or add it
            all_packages = [p for p in all_packages if p.id != artifact_id]
            all_packages.append(package)

        # Build lineage graph using the function from lineage.py
        lineage = build_lineage_graph(
            artifact_id,
            all_packages,
            load_config_from_repo,
        )

        return jsonify(lineage), 200

    except Exception as e:
        logger.error(f"Error building lineage graph: {str(e)}")
        return jsonify(
            {
                "error": "The lineage graph cannot be computed because the artifact metadata is missing or malformed."
            }
        ), 400


@app.route("/api/artifact/model/<artifact_id>/license-check", methods=["POST"])
def check_artifact_license(artifact_id):
    """Check license compatibility.

    Request body: {github_url: string}

    Returns:
        tuple: (boolean JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    github_url = data.get("github_url", "")
    if not github_url:
        return jsonify({"error": "github_url required in request body"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    try:
        url = package.metadata.get("url", "")
        if not url:
            return jsonify({"error": "No URL in package metadata"}), 400

        model = Model(model=ModelResource(url=url))
        results = compute_all_metrics(model)
        license_metric = results.get("license")

        if license_metric:
            is_compatible = license_metric.value > 0.5
            return jsonify(is_compatible), 200
        else:
            return jsonify(False), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/artifact/model/<artifact_id>/sensitive", methods=["POST", "PUT"])
def mark_model_sensitive(artifact_id):
    """Mark a model as sensitive and set monitoring script.

    Any user can mark models as sensitive.

    Request body: {
        "is_sensitive": bool,
        "monitoring_script": string (JavaScript code, optional)
    }

    Args:
        artifact_id: Model ID to mark as sensitive

    Returns:
        tuple: (Success message JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    if package.artifact_type != "model":
        return jsonify({"error": "Only models can be marked as sensitive"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    is_sensitive = data.get("is_sensitive", True)
    monitoring_script = data.get("monitoring_script", "")

    # Update package metadata
    package.metadata["is_sensitive"] = is_sensitive
    if monitoring_script:
        package.metadata["monitoring_script"] = monitoring_script
    elif "monitoring_script" in package.metadata:
        # Remove script if not provided and unsetting sensitive
        if not is_sensitive:
            del package.metadata["monitoring_script"]

    # Initialize download history if not present
    if "download_history" not in package.metadata:
        package.metadata["download_history"] = []

    storage.update_package(package)

    logger.info(
        f"Model '{package.name}' (ID: {artifact_id}) marked as sensitive={is_sensitive} by '{user_info['username']}'"
    )

    return jsonify(
        {
            "message": f"Model marked as {'sensitive' if is_sensitive else 'not sensitive'}",
            "is_sensitive": is_sensitive,
            "has_monitoring_script": bool(monitoring_script),
        }
    ), 200


@app.route("/api/artifact/model/<artifact_id>/sensitive", methods=["GET"])
def get_model_sensitive_status(artifact_id):
    """Get sensitive status and monitoring script for a model.

    Any user can query sensitive status.

    Args:
        artifact_id: Model ID to query

    Returns:
        tuple: (Sensitive info JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    if package.artifact_type != "model":
        return jsonify({"error": "Only models can be sensitive"}), 400

    is_sensitive = package.metadata.get("is_sensitive", False)
    monitoring_script = package.metadata.get("monitoring_script", "")

    return jsonify(
        {"is_sensitive": is_sensitive, "monitoring_script": monitoring_script}
    ), 200


@app.route("/api/artifact/model/<artifact_id>/sensitive", methods=["DELETE"])
def delete_model_sensitive_status(artifact_id):
    """Remove sensitive status from a model.

    Any user can remove sensitive status.

    Args:
        artifact_id: Model ID to update

    Returns:
        tuple: (Success message JSON, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    if package.artifact_type != "model":
        return jsonify({"error": "Only models can be sensitive"}), 400

    # Remove sensitive status and monitoring script
    package.metadata["is_sensitive"] = False
    if "monitoring_script" in package.metadata:
        del package.metadata["monitoring_script"]

    storage.update_package(package)

    logger.info(
        f"Model '{package.name}' (ID: {artifact_id}) sensitive status removed by '{user_info['username']}'"
    )

    return jsonify({"message": "Sensitive status removed"}), 200


@app.route("/api/artifact/model/<artifact_id>/download-history", methods=["GET"])
def get_model_download_history(artifact_id):
    """Get download history for a sensitive model.

    Args:
        artifact_id: Model ID to query

    Returns:
        tuple: (Download history JSON array, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    if not validate_artifact_id(artifact_id):
        return jsonify({"error": "Invalid artifact ID format"}), 400

    package = storage.get_package(artifact_id)
    if not package:
        return jsonify({"error": "Artifact not found"}), 404

    if package.artifact_type != "model":
        return jsonify({"error": "Only models can have download history"}), 400

    download_history = package.metadata.get("download_history", [])

    return jsonify(download_history), 200


@app.route("/api/artifact/byName/<artifact_name>", methods=["GET"])
def get_artifacts_by_name(artifact_name):
    """Get artifact metadata entries by name.

    Per OpenAPI spec: Returns metadata for each artifact matching the provided name.

    Args:
        artifact_name: Name of artifacts to find

    Returns:
        tuple: (Array of ArtifactMetadata JSON, 200) or error response
            - 200: Array of ArtifactMetadata objects
            - 400: Invalid artifact name
            - 403: Authentication failed
            - 404: No artifacts found with this name
    """
    logger.info(f"get_artifacts_by_name called with name: {artifact_name}")

    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        logger.warning("get_artifacts_by_name: auth check failed")
        return error_response

    # Check search permission
    has_permission, permission_error = check_permission(user_info, "search")
    if not has_permission:
        return permission_error

    if not artifact_name or not artifact_name.strip():
        return jsonify(
            {
                "description": "There is missing field(s) in the artifact_name or it is formed improperly, or is invalid."
            }
        ), 400

    matching_packages = []
    for package in storage.packages.values():
        if package.name == artifact_name:
            matching_packages.append(package)

    if not matching_packages:
        logger.info(f"No artifacts found with name: {artifact_name}")
        return jsonify({"error": "No such artifact."}), 404

    artifacts = []
    for package in matching_packages:
        artifact_metadata = package_to_artifact_metadata(package)
        artifacts.append(artifact_metadata)

    logger.info(f"Found {len(artifacts)} artifacts with name: {artifact_name}")
    return jsonify(artifacts), 200


@app.route("/api/artifact/byRegEx", methods=["POST"])
def search_artifacts_by_regex():
    """Search artifacts by regex pattern.

    Request body: {regex: string}

    Returns:
        tuple: (Array of ArtifactMetadata, 200) or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    regex_pattern = data.get("regex", "")
    if not regex_pattern:
        logger.warning("byRegEx endpoint called with missing regex in request body")
        return jsonify({"error": "regex required in request body"}), 400

    logger.info(f"byRegEx endpoint called with regex pattern: {regex_pattern}")

    try:
        packages = storage.search_packages(regex_pattern, use_regex=True)

        artifacts = []
        for package in packages:
            pkg_type = infer_artifact_type(package)
            artifacts.append(package_to_artifact_metadata(package, pkg_type))

        if len(artifacts) == 0:
            logger.info(
                f"byRegEx search found no artifacts matching pattern: {regex_pattern}"
            )
            return jsonify({"error": "No artifact found under this regex."}), 404

        logger.info(
            f"byRegEx search completed successfully: {len(artifacts)} artifacts found"
        )
        return jsonify(artifacts), 200
    except Exception as e:
        logger.error(
            f"byRegEx search failed with exception: {str(e)}, pattern: {regex_pattern}"
        )
        return jsonify({"error": str(e)}), 400


@app.route("/api/authenticate", methods=["PUT"])
def authenticate():
    """Authenticate user and return access token.

    Per OpenAPI spec: Returns AuthenticationToken as JSON string.
    Request Body: AuthenticationRequest with user and secret.

    Returns:
        tuple: (AuthenticationToken JSON string, 200) or error response
            Success (200): Token as JSON-encoded string
            Error (400): Missing or malformed request body
            Error (401): Invalid username or password
            Error (501): Authentication not supported (not implemented)
    """
    logger.info("authenticate endpoint called")
    
    # Ensure default user exists before authentication attempts
    try:
        initialize_default_admin_user()
    except Exception as e:
        logger.error(f"Failed to ensure default user exists: {e}")
    
    try:
        data = request.get_json()
        if not data:
            logger.warning("Auth failed: no request body")
            return jsonify(
                {
                    "error": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."
                }
            ), 400

        user = data.get("user")
        secret = data.get("secret")

        if not user or not isinstance(user, dict):
            logger.warning("Auth failed: missing or invalid user field")
            return jsonify(
                {
                    "error": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."
                }
            ), 400

        if not secret or not isinstance(secret, dict):
            logger.warning("Auth failed: missing or invalid secret field")
            return jsonify(
                {
                    "error": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."
                }
            ), 400

        username = user.get("name")
        password = secret.get("password")

        if not username or not password:
            logger.warning("Auth failed: missing username or password")
            return jsonify(
                {
                    "error": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."
                }
            ), 400

        logger.info(
            f"Auth attempt for username: {username}, password length: {len(password)}"
        )

        # Check new storage-based user system
        from auth import verify_password, generate_token
        from datetime import timedelta
        from registry_models import TokenInfo

        user = storage.get_user(username)
        if user and verify_password(password, user.password_hash):
            # Valid credentials - create new token
            token = f"bearer {generate_token()}"
            token_info = TokenInfo(
                token=token,
                user_id=user.user_id,
                username=username,
                created_at=datetime.now(timezone.utc),
                usage_count=0,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=10),
            )
            storage.create_token(token_info)

            logger.info(
                f"Auth successful (new system), token generated, valid_tokens count: {len(storage.tokens)}"
            )

            return jsonify(token), 200

        # User not found or password invalid
        logger.warning(f"Auth failed: invalid credentials for user '{username}'")
        return jsonify({"error": "The user or password is invalid."}), 401
    except Exception as e:
        logger.error(f"Auth exception: {str(e)}")
        return jsonify(
            {
                "error": "There is missing field(s) in the AuthenticationRequest or it is formed improperly."
            }
        ), 400


@app.route("/api/reset", methods=["DELETE"])
def reset_registry():
    """Reset the registry to a system default state.

    Per OpenAPI spec: Returns 200 with empty body, 401 for permission denied, 403 for auth failure.

    Returns:
        tuple: Response and HTTP status code
            Success (200): Empty response body (no content schema per spec)
            Error (401): Permission denied (not implemented - would require permission checking)
            Error (403): Authentication failed due to invalid or missing token
    """
    logger.info(
        f"reset_registry called, packages before reset: {len(storage.packages)}"
    )

    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        logger.warning("Reset failed: authentication check failed")
        return error_response

    try:
        logger.info("Performing storage reset...")
        storage.reset()
        logger.info(
            f"Storage reset complete, packages after reset: {len(storage.packages)}"
        )

        # Reinitialize default token if not present
        if DEFAULT_TOKEN not in _valid_tokens:
            initialize_default_token()
        logger.info(f"After reset, valid_tokens count: {len(_valid_tokens)}")

        # Ensure default user exists after reset
        initialize_default_admin_user()
        logger.info("Default admin user reinitialized after reset")

        storage.record_event(
            "registry_reset",
            actor="api",
            details={"initiator": "api"},
        )
        logger.info("Reset complete, returning 200")
        return Response(status=200)

    except Exception as e:
        logger.error(f"Reset failed with exception: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/tracks", methods=["GET"])
def get_tracks():
    """Return the list of tracks the student plans to implement.

    Returns:
        tuple: JSON response with plannedTracks array and 200 status code
            - plannedTracks (list): Array of track names the student plans to implement
        Error (500): System error during retrieval
    """
    try:
        return jsonify({"plannedTracks": ["Access control track"]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# User Management Endpoints (Security Track Phase 2)
@app.route("/api/users", methods=["POST"])
def register_user():
    """Register a new user (admin only).

    Request Body: UserRegistrationRequest with username, password, permissions
    Returns:
        tuple: (UserInfo JSON, 201) or error response
            Success (201): User created successfully
            Error (400): Invalid request body or missing fields
            Error (401): User already exists
            Error (403): Authentication failed or insufficient permissions
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check if user is admin
    if not user_info or not user_info.get("is_admin"):
        return jsonify(
            {"error": "Insufficient permissions. Admin access required."}
        ), 403

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        username = data.get("username")
        password = data.get("password")
        permissions = data.get("permissions", [])
        is_admin = data.get("is_admin", False)

        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        # Check if user already exists
        if storage.get_user(username):
            return jsonify({"error": "User already exists"}), 401

        # Create new user
        from auth import hash_password
        from registry_models import User

        new_user = User(
            user_id=str(uuid.uuid4()),
            username=username,
            password_hash=hash_password(password),
            permissions=permissions,
            is_admin=is_admin,
            created_at=datetime.now(timezone.utc),
        )

        storage.create_user(new_user)

        logger.info(
            f"User '{username}' registered successfully by '{user_info['username']}'"
        )

        return jsonify(new_user.to_dict()), 201

    except Exception as e:
        logger.error(f"User registration failed: {str(e)}")
        return jsonify({"error": str(e)}), 400


@app.route("/api/users/<username>", methods=["DELETE"])
def delete_user(username):
    """Delete a user.

    Users can delete their own account. Admins can delete any account.

    Args:
        username: Username to delete

    Returns:
        tuple: (Success message JSON, 200) or error response
            Success (200): User deleted successfully
            Error (403): Authentication failed or insufficient permissions
            Error (404): User not found
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check permissions: user can delete self OR admin can delete anyone
    if username != user_info.get("username") and not user_info.get("is_admin"):
        return jsonify({"error": "Insufficient permissions"}), 403

    # Prevent deletion of default admin
    if username == DEFAULT_USERNAME:
        return jsonify({"error": "Cannot delete default admin user"}), 403

    deleted_user = storage.delete_user(username)
    if not deleted_user:
        return jsonify({"error": "User not found"}), 404

    logger.info(f"User '{username}' deleted by '{user_info['username']}'")

    return jsonify({"message": f"User '{username}' deleted successfully"}), 200


@app.route("/api/users", methods=["GET"])
def list_users():
    """List all users (admin only).

    Returns:
        tuple: (Array of UserInfo JSON, 200) or error response
            Success (200): List of users (without password hashes)
            Error (403): Authentication failed or insufficient permissions
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check if user is admin
    if not user_info or not user_info.get("is_admin"):
        return jsonify(
            {"error": "Insufficient permissions. Admin access required."}
        ), 403

    users = storage.list_users()
    users_data = [user.to_dict() for user in users]

    return jsonify(users_data), 200


@app.route("/api/ingest", methods=["POST"])
def ingest_model():
    """Ingest and validate a HuggingFace model into the registry.

    Evaluates a HuggingFace model URL against quality thresholds and creates
    a package entry if all metrics pass. All non-latency metrics must score
    at least 0.5 to be accepted.

    Request Body (JSON):
        - url (str, required): HuggingFace model URL (must start with
          'https://huggingface.co/')

    Quality Thresholds (minimum 0.5):
        All non-latency metrics computed via compute_all_metrics

    Returns:
        tuple: JSON response and HTTP status code
            Success (201):
                - message (str): Success confirmation
                - package (dict): Created package with embedded scores
            Error (400): Invalid URL, missing URL, or failed quality threshold
            Error (500): Server error during ingestion or evaluation
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check upload permission
    has_permission, permission_error = check_permission(user_info, "upload")
    if not has_permission:
        return permission_error

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

        # Validate all non-latency metrics
        for metric_name, metric in results.items():
            if metric_name == "size_score":
                if isinstance(metric.value, dict) and len(metric.value) > 0:
                    max_score = max(metric.value.values())
                    if max_score < 0.5:
                        return jsonify(
                            {
                                "error": f"Failed threshold: {metric_name} max score {max_score:.3f} < 0.5"
                            }
                        ), 400
                else:
                    return jsonify(
                        {
                            "error": f"Failed threshold: {metric_name} is invalid or empty"
                        }
                    ), 400
            elif isinstance(metric.value, (int, float)):
                if metric.value < 0.5:
                    return jsonify(
                        {
                            "error": f"Failed threshold: {metric_name} {metric.value:.3f} < 0.5"
                        }
                    ), 400
            else:
                return jsonify(
                    {"error": f"Failed threshold: {metric_name} has invalid type"}
                ), 400

        parts = url.rstrip("/").split("/")
        model_name = parts[-1] if parts else "unknown"

        scores = {}
        for name, metric in results.items():
            scores[name] = {"score": metric.value, "latency_ms": metric.latency_ms}

        package_id = str(uuid.uuid4())
        # Infer artifact type from URL
        artifact_type = infer_artifact_type_from_url(url)

        # Always upload package to S3 (metadata only for URL-based packages)
        metadata = {"url": url, "scores": scores}
        s3_key = _upload_package_to_s3(package_id, None, metadata)
        if not s3_key:
            logger.warning(f"Failed to upload package to S3 for package {package_id}, continuing without S3 storage")

        package = Package(
            id=package_id,
            artifact_type=artifact_type,
            name=model_name,
            version="1.0.0",
            uploaded_by=DEFAULT_USERNAME,
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=0,
            metadata=metadata,
            s3_key=s3_key,
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


@app.route("/api/ingest/upload", methods=["POST"])
def ingest_upload():
    """Ingest packages from uploaded CSV or JSON file.

    Accepts a file upload (CSV or JSON format) containing package data.
    Validates and stores all packages from the file.

    Returns:
        tuple: JSON response and HTTP status code
            Success (201): Imported packages details
            Error (400): No file, invalid format, validation errors
            Error (500): Server error during processing
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check upload permission
    has_permission, permission_error = check_permission(user_info, "upload")
    if not has_permission:
        return permission_error

    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        allowed_extensions = {".csv", ".json"}
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            return jsonify(
                {
                    "error": f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
                }
            ), 400

        file_content = file.read().decode("utf-8")

        packages_data = []

        if file_ext == ".csv":
            packages_data = parse_csv_content(file_content)
        elif file_ext == ".json":
            packages_data = parse_json_content(file_content)

        if not packages_data:
            return jsonify({"error": "No valid package data found in file"}), 400

        created_packages = []
        errors = []

        for idx, pkg_data in enumerate(packages_data):
            try:
                if not pkg_data.get("name") or not pkg_data.get("version"):
                    errors.append(
                        f"Row {idx + 1}: Missing required fields (name, version)"
                    )
                    continue

                package_id = str(uuid.uuid4())
                # Infer artifact type from metadata URL
                metadata = pkg_data.get("metadata", {})
                artifact_type = "model"  # default
                if "url" in metadata:
                    artifact_type = infer_artifact_type_from_url(metadata["url"])

                # Always upload package to S3 (with content if provided, or metadata if not)
                content = pkg_data.get("content", "")
                s3_key = None
                try:
                    content_bytes = None
                    if content:
                        content_bytes = _decode_package_content(content)
                    
                    # Always upload to S3 (content if available, metadata otherwise)
                    s3_key = _upload_package_to_s3(package_id, content_bytes, metadata)
                    if not s3_key:
                        logger.warning(f"Failed to upload package to S3 for package {package_id}, continuing without S3 storage")
                except Exception as e:
                    logger.error(f"Error uploading package to S3: {e}, continuing without S3 storage")

                # Calculate size_bytes from content
                size_bytes = len(content.encode("utf-8")) if content else 0

                package = Package(
                    id=package_id,
                    artifact_type=artifact_type,
                    name=pkg_data["name"],
                    version=pkg_data["version"],
                    uploaded_by=DEFAULT_USERNAME,
                    upload_timestamp=datetime.now(timezone.utc),
                    size_bytes=size_bytes,
                    metadata=metadata,
                    s3_key=s3_key,
                )

                storage.create_package(package)
                created_packages.append(package.to_dict())

            except Exception as e:
                errors.append(f"Row {idx + 1}: {str(e)}")

        if not created_packages and errors:
            return jsonify(
                {"error": "Failed to import any packages", "details": errors}
            ), 400

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


@app.route("/health/dashboard", methods=["GET"])
def health_dashboard_redirect():
    """Backward-compatible alias for the health dashboard route."""
    return render_template("health.html")


@app.route("/download/<artifact_name>", methods=["GET"])
def download_artifact(artifact_name):
    """Download an artifact.

    For sensitive models, executes monitoring script before allowing download.

    Args:
        artifact_name: Name of artifact to download

    Returns:
        Redirect to download URL or error response
    """
    is_valid, error_response, user_info = check_auth_header()
    if not is_valid:
        return error_response

    # Check download permission
    has_permission, permission_error = check_permission(user_info, "download")
    if not has_permission:
        return permission_error

    if not artifact_name or not artifact_name.strip():
        return jsonify({"error": "Invalid artifact name"}), 400

    # Find the artifact by name (get latest version if multiple)
    matching_packages = []
    for package in storage.packages.values():
        if package.name == artifact_name:
            matching_packages.append(package)

    if not matching_packages:
        return jsonify({"error": "Artifact not found"}), 404

    # Get the most recent package
    package = max(matching_packages, key=lambda p: p.upload_timestamp)

    # Check if model is sensitive
    is_sensitive = package.metadata.get("is_sensitive", False)

    if is_sensitive and package.artifact_type == "model":
        monitoring_script = package.metadata.get("monitoring_script", "")

        if monitoring_script:
            # Execute Node.js monitoring script
            import tempfile
            import subprocess

            try:
                # Create temporary file for the script
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".js", delete=False
                ) as script_file:
                    script_file.write(monitoring_script)
                    script_path = script_file.name

                # Prepare arguments for the script
                model_name = package.name
                uploader_username = package.uploaded_by
                downloader_username = user_info.get("username", "unknown")
                zip_file_path = package.metadata.get(
                    "url", ""
                )  # Use URL as placeholder

                # Execute the script with Node.js
                logger.info(
                    f"Executing monitoring script for sensitive model '{model_name}'"
                )
                result = subprocess.run(
                    [
                        "node",
                        script_path,
                        model_name,
                        uploader_username,
                        downloader_username,
                        zip_file_path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,  # 30 second timeout
                )

                # Clean up temp file
                os.unlink(script_path)

                # Check exit code
                if result.returncode != 0:
                    logger.warning(
                        f"Monitoring script rejected download of '{model_name}' for user '{downloader_username}'"
                    )
                    error_msg = (
                        result.stdout.strip()
                        if result.stdout
                        else "Download rejected by monitoring script"
                    )
                    return jsonify(
                        {
                            "error": f"Download rejected: {error_msg}",
                            "monitoring_output": result.stdout,
                        }
                    ), 403

                logger.info(
                    f"Monitoring script approved download of '{model_name}' for user '{downloader_username}'"
                )

            except subprocess.TimeoutExpired:
                logger.error(f"Monitoring script timeout for model '{model_name}'")
                if os.path.exists(script_path):
                    os.unlink(script_path)
                return jsonify({"error": "Monitoring script timeout"}), 500
            except FileNotFoundError:
                logger.error("Node.js not found - cannot execute monitoring script")
                return jsonify(
                    {"error": "Node.js not available for monitoring script execution"}
                ), 500
            except Exception as e:
                logger.error(f"Error executing monitoring script: {str(e)}")
                if "script_path" in locals() and os.path.exists(script_path):
                    os.unlink(script_path)
                return jsonify({"error": f"Monitoring script error: {str(e)}"}), 500

    # Record download in history for sensitive models
    if is_sensitive and package.artifact_type == "model":
        if "download_history" not in package.metadata:
            package.metadata["download_history"] = []

        download_record = {
            "username": user_info.get("username", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        package.metadata["download_history"].append(download_record)
        storage.update_package(package)

        logger.info(
            f"Recorded download of sensitive model '{package.name}' by '{user_info['username']}'"
        )

    # Return download URL or redirect
    download_url = package.metadata.get("url", "")
    if download_url:
        logger.info(
            f"Artifact '{artifact_name}' downloaded by '{user_info['username']}'"
        )
        return jsonify({"download_url": download_url}), 200
    else:
        return jsonify({"error": "No download URL available for this artifact"}), 404


@app.route("/api/PackageConfusionAudit", methods=["GET"])
def package_confusion_audit():
    """Audit packages for potential confusion attacks (typosquatting, bot farms).

    Detects:
    1. Typosquatting - packages with names similar to existing ones
    2. Bot farm patterns - suspicious upload patterns from the same user

    Returns:
        JSON array of suspicious packages with risk scores and reasons
    """
    try:
        # Get all packages
        packages = storage.list_packages()
        suspicious_packages = []

        # Helper function to calculate Levenshtein distance
        def levenshtein_distance(s1, s2):
            """Calculate edit distance between two strings."""
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)

            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    # Cost of insertions, deletions, or substitutions
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        # 1. Detect typosquatting
        package_names = [p.name for p in packages]
        for i, pkg in enumerate(packages):
            reasons = []
            risk_score = 0.0

            # Check for similar names (typosquatting)
            for j, other_name in enumerate(package_names):
                if i == j or pkg.name == other_name:
                    continue

                # Calculate similarity
                distance = levenshtein_distance(pkg.name.lower(), other_name.lower())
                max_len = max(len(pkg.name), len(other_name))

                # If names are very similar (edit distance <= 2 or similarity > 80%)
                if distance <= 2 and distance > 0:
                    similarity = 1 - (distance / max_len)
                    if similarity > 0.8:
                        reasons.append(f"Typosquatting: Similar to '{other_name}' (distance: {distance})")
                        risk_score += 0.4

                # Check for common typosquatting patterns
                # Character substitution (0->o, 1->l, etc.)
                name_lower = pkg.name.lower()
                other_lower = other_name.lower()
                if name_lower.replace('0', 'o').replace('1', 'l') == other_lower or \
                   name_lower == other_lower.replace('0', 'o').replace('1', 'l'):
                    reasons.append(f"Character substitution attack: Similar to '{other_name}'")
                    risk_score += 0.5

            # 2. Detect bot farm patterns
            # Check if user uploaded many packages in short time
            user_packages = [p for p in packages if p.uploaded_by == pkg.uploaded_by]
            if len(user_packages) >= 5:
                # Check if packages have similar names (bot farm pattern)
                similar_name_count = 0
                for other_pkg in user_packages:
                    if other_pkg.id != pkg.id:
                        # Check for pattern-based naming (e.g., pkg1, pkg2, pkg3)
                        if any(c.isdigit() for c in pkg.name) and any(c.isdigit() for c in other_pkg.name):
                            base1 = ''.join(c for c in pkg.name if not c.isdigit())
                            base2 = ''.join(c for c in other_pkg.name if not c.isdigit())
                            if base1 == base2:
                                similar_name_count += 1

                if similar_name_count >= 3:
                    reasons.append(f"Bot farm pattern: {len(user_packages)} packages from '{pkg.uploaded_by}' with similar naming")
                    risk_score += 0.3

                # Check upload timestamps for rapid succession
                upload_times = sorted([p.upload_timestamp for p in user_packages])
                if len(upload_times) >= 5:
                    # Check if 5+ packages uploaded within 1 hour
                    time_diff = (upload_times[-1] - upload_times[0]).total_seconds()
                    if time_diff < 3600:  # 1 hour
                        reasons.append(f"Rapid upload pattern: {len(user_packages)} packages in {time_diff/60:.1f} minutes")
                        risk_score += 0.2

            # Add to suspicious list if risk score > 0
            if risk_score > 0:
                suspicious_packages.append({
                    "package_id": pkg.id,
                    "name": pkg.name,
                    "version": pkg.version,
                    "uploaded_by": pkg.uploaded_by,
                    "upload_timestamp": pkg.upload_timestamp.isoformat(),
                    "risk_score": min(risk_score, 1.0),  # Cap at 1.0
                    "reasons": reasons
                })

        # Sort by risk score (highest first)
        suspicious_packages.sort(key=lambda x: x["risk_score"], reverse=True)

        return jsonify(suspicious_packages), 200

    except Exception as e:
        logger.error(f"Package confusion audit failed: {str(e)}")
        return jsonify({"error": "Failed to perform package confusion audit"}), 500


if __name__ == "__main__":
    initialize_default_token()
    initialize_default_admin_user()
    # Read port from environment variable (AWS EB sets this) or default to 8000
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
