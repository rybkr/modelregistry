from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional, Tuple
import regex as re
import threading
import logging

from registry_models import Package

logger = logging.getLogger('storage')


def is_safe_regex(pattern: str) -> bool:
    """Validate regex pattern to prevent ReDoS attacks.

    Checks for dangerous patterns that can cause catastrophic backtracking:
    - Nested quantifiers like (a+)+ or (a*)*
    - Adjacent quantifiers like a++ or a**
    - Excessive length

    Args:
        pattern: Regex pattern string to validate

    Returns:
        bool: True if pattern is safe, False if potentially dangerous
    """
    logger.info(f"Validating regex pattern: {pattern}")

    # Reject patterns that are too long
    if len(pattern) > 100:
        logger.warning(f"Regex pattern rejected: pattern too long ({len(pattern)} > 100)")
        return False

    # Check for nested quantifiers: (...)+ or (...)* or (...)?
    # followed by another quantifier
    dangerous_patterns = [
        r'\([^)]*[+*?]\s*\)\s*[+*?]',  # (x+)+ or (x*)* or (x?)?
        r'[+*?]\s*[+*?]',               # ++ or ** or +* etc.
        r'\([^)]*[+*?]\s*\)\s*\{',      # (x+){n,m}
        r'\{[^}]*\}\s*[+*?]',           # {n,m}+ or {n,m}*
        r'\([^)]*}\s*\)\s*\{',          #(x{n,m}){n,m}
    ]

    for danger_pattern in dangerous_patterns:
        timed_out, match = regex_validate_with_timeout(danger_pattern, pattern, timeout_seconds=0.1)
        if timed_out:
            # Timeout or exception occurred - treat as unsafe
            logger.warning(f"Regex pattern validation timed out or failed for pattern: {pattern}")
            return False
        if match:
            logger.warning(f"Regex pattern rejected: dangerous pattern detected ({danger_pattern})")
            return False
        logger.info(f"Passed check against: {danger_pattern}")

    logger.info(f"Regex pattern passed validation: {pattern}")
    return True


def regex_validate_with_timeout(pattern_str: str, text: str, timeout_seconds: float = 0.1) -> (bool, Optional[re.Match]):
    """Execute regex validation search with timeout protection.

    Used for validating regex patterns against dangerous patterns.
    Uses threading to implement timeout since signal.alarm() doesn't work
    in multi-threaded Flask applications.

    Args:
        pattern_str: Regex pattern string to compile and use
        text: Text to search
        timeout_seconds: Maximum time allowed for search (default 0.1s)

    Returns:
        bool: true if timed out, false otherwise
        Optional[re.Match]: Match object if found within timeout, None otherwise
    """
    result = [None]  # Use list to allow modification in nested function
    exception = [None]

    def search():
        try:
            compiled_pattern = re.compile(pattern_str)
            result[0] = compiled_pattern.search(text)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=search)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Timeout occurred - thread is still running
        # Note: We can't actually kill the thread, but we return None
        # The thread will eventually finish in background
        return True, None

    if exception[0]:
        # Exception occurred during search
        return True, None

    return False, result[0]


def regex_search_with_timeout(pattern: re.Pattern, text: str, timeout_seconds: float = 0.5) -> Optional[re.Match]:
    """Execute regex search with timeout protection.

    Uses threading to implement timeout since signal.alarm() doesn't work
    in multi-threaded Flask applications.

    Args:
        pattern: Compiled regex pattern
        text: Text to search
        timeout_seconds: Maximum time allowed for search (default 0.5s)

    Returns:
        Optional[re.Match]: Match object if found within timeout, None otherwise
    """
    result = [None]  # Use list to allow modification in nested function
    exception = [None]

    def search():
        try:
            result[0] = pattern.search(text)
        except Exception as e:
            exception[0] = e

    thread = threading.Thread(target=search)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Timeout occurred - thread is still running
        # Note: We can't actually kill the thread, but we return None
        # The thread will eventually finish in background
        return None

    if exception[0]:
        # Exception occurred during search
        return None

    return result[0]


class RegistryStorage:
    """In-memory storage for package registry.

    Provides CRUD operations and search functionality for packages.
    All data is stored in memory and will be lost on restart.
    """

    def __init__(self):
        """Initialize empty package storage."""
        self.packages: Dict[str, Package] = {}
        self._activity_log: deque[dict] = deque(maxlen=1024)
        self._log_entries: deque[dict] = deque(maxlen=2048)
        self._lock = Lock()
        self._known_event_types = [
            "package_uploaded",
            "model_ingested",
            "package_deleted",
            "metrics_evaluated",
            "registry_reset",
        ]
        self.reset()

    def reset(self):
        """Clear all packages and activity logs from storage.

        Performs a complete reset to initial state, clearing:
        - All packages (artifacts)
        - Activity logs
        - Log entries

        This method is thread-safe and ensures complete cleanup.
        """
        with self._lock:
            # Create a new empty dict to ensure complete reset
            self.packages = {}
            self._activity_log.clear()
            self._log_entries.clear()

    def create_package(self, package: Package) -> Package:
        """Store a new package.

        Args:
            package: Package to store

        Returns:
            Package: The stored package
        """
        self.packages[package.id] = package
        return package

    def get_package(self, package_id: str) -> Optional[Package]:
        """Retrieve a package by ID.

        Args:
            package_id: Unique package identifier

        Returns:
            Optional[Package]: Package if found, None otherwise
        """
        return self.packages.get(package_id)

    def list_packages(self, offset: int = 0, limit: int = 100) -> List[Package]:
        """List packages with pagination.

        Args:
            offset: Starting index for pagination
            limit: Maximum number of packages to return

        Returns:
            List[Package]: Paginated list of packages
        """
        all_packages = list(self.packages.values())
        return all_packages[offset : offset + limit]

    def delete_package(self, package_id: str) -> Optional[Package]:
        """Delete a package by ID.

        Args:
            package_id: Unique package identifier

        Returns:
            Optional[Package]: Deleted package if found, None otherwise
        """
        return self.packages.pop(package_id, None)

    def search_packages(self, query: str, use_regex: bool = False) -> List[Package]:
        """Search packages by name or README content.

        Searches package names and README metadata for matches.
        Implements ReDoS protection for regex searches with pattern validation
        and timeout mechanisms.

        Args:
            query: Search string or regex pattern
            use_regex: If True, treat query as regex pattern

        Returns:
            List[Package]: Matching packages, empty list if regex invalid or unsafe
        """
        results = []
        if use_regex:
            logger.info(f"Regex search initiated with pattern: {query}")
            # Validate regex pattern for safety
            if not is_safe_regex(query):
                # Reject potentially dangerous patterns
                logger.warning(f"Regex search rejected: pattern failed safety validation: {query}")
                return []

            # Compile pattern
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                logger.warning(f"Regex pattern compilation failed: {query}, error: {str(e)}")
                return []

            # Search with timeout protection
            for package in self.packages.values():
                # Limit name length for search
                package_name = package.name[:1000] if len(package.name) > 1000 else package.name

                # Search name with timeout
                match = regex_search_with_timeout(pattern, package_name, timeout_seconds=0.5)
                if match:
                    results.append(package)
                    continue  # Skip readme search if name matched

                # Search readme if present
                if "readme" in package.metadata:
                    readme_text = str(package.metadata.get("readme", ""))
                    # Limit readme length for search
                    if len(readme_text) > 10000:
                        readme_text = readme_text[:10000]

                    # Search readme with timeout
                    match = regex_search_with_timeout(pattern, readme_text, timeout_seconds=0.5)
                    if match:
                        results.append(package)

            logger.debug(f"Regex search completed: {len(results)} packages found")
        else:
            query_lower = query.lower()
            for package in self.packages.values():
                if query_lower in package.name.lower():
                    results.append(package)
                elif (
                    "readme" in package.metadata
                    and query_lower in str(package.metadata.get("readme", "")).lower()
                ):
                    results.append(package)
        return results

    def get_artifacts_by_query(
        self, queries: List[dict], artifact_types: Optional[List[str]] = None, offset: int = 0, limit: int = 100
    ) -> Tuple[List[Package], int]:
        """Get packages matching artifact query criteria.

        Processes ArtifactQuery array. Handles name: "*" for enumerate all.
        Filters by artifact_types if provided.

        Args:
            queries: List of ArtifactQuery objects (dicts with name, types, etc.)
            artifact_types: Optional list of types to filter by
            offset: Pagination offset
            limit: Maximum number of results

        Returns:
            tuple: (matching packages list, total count)
        """
        with self._lock:
            matching_packages = []

            # Handle enumerate all case
            enumerate_all = False
            for query in queries:
                if isinstance(query, dict) and query.get("name") == "*":
                    enumerate_all = True
                    break

            if enumerate_all:
                # Return all packages
                all_packages = list(self.packages.values())
                # Filter by type if specified
                #if artifact_types:
                #    filtered = []
                #    for pkg in all_packages:
                #        # Infer type from URL
                #        url = pkg.metadata.get("url", "")
                #        pkg_type = "model"
                #        if "huggingface.co/datasets/" in url:
                #            pkg_type = "dataset"
                #        elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
                #            pkg_type = "code"
                #        if pkg_type in artifact_types:
                #            filtered.append(pkg)
                #    all_packages = filtered
                matching_packages = all_packages
            else:
                # Process individual queries
                for query in queries:
                    if not isinstance(query, dict):
                        continue
                    query_name = query.get("name", "")
                    # Per OpenAPI spec: ArtifactQuery uses 'types' (plural, array) not 'type' (singular)
                    query_types = query.get("types", [])
                    if not isinstance(query_types, list):
                        query_types = []

                    # Filter by name
                    if query_name and query_name != "*":
                        for pkg in self.packages.values():
                            if query_name.lower() in pkg.name.lower():
                                # Filter by types if specified
                                if query_types:
                                    url = pkg.metadata.get("url", "")
                                    pkg_type = "model"
                                    if "huggingface.co/datasets/" in url:
                                        pkg_type = "dataset"
                                    elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
                                        pkg_type = "code"
                                    if pkg_type not in query_types:
                                        continue
                                if pkg not in matching_packages:
                                    matching_packages.append(pkg)
                    elif query_types:
                        # Filter by types only (when name is "*" or empty)
                        for pkg in self.packages.values():
                            url = pkg.metadata.get("url", "")
                            pkg_type = "model"
                            if "huggingface.co/datasets/" in url:
                                pkg_type = "dataset"
                            elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
                                pkg_type = "code"
                            if pkg_type in query_types and pkg not in matching_packages:
                                matching_packages.append(pkg)

            # Apply type filter if provided
            if artifact_types and not enumerate_all:
                filtered = []
                for pkg in matching_packages:
                    url = pkg.metadata.get("url", "")
                    pkg_type = "model"
                    if "huggingface.co/datasets/" in url:
                        pkg_type = "dataset"
                    elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
                        pkg_type = "code"
                    if pkg_type in artifact_types:
                        filtered.append(pkg)
                matching_packages = filtered

            total_count = len(matching_packages)

            # Apply pagination
            start_idx = min(offset, total_count)
            end_idx = min(offset + limit, total_count)
            paginated = matching_packages[start_idx:end_idx]

            return paginated, total_count

    def get_artifact_by_type_and_id(self, artifact_type: str, artifact_id: str) -> Optional[Package]:
        """Retrieve package by ID, optionally validating type.

        Args:
            artifact_type: Expected artifact type (for validation)
            artifact_id: Package ID to retrieve

        Returns:
            Optional[Package]: Package if found, None otherwise
        """
        package = self.packages.get(artifact_id)
        if not package:
            return None

        # Validate type if provided
        if artifact_type:
            url = package.metadata.get("url", "")
            pkg_type = "model"
            if "huggingface.co/datasets/" in url:
                pkg_type = "dataset"
            elif "huggingface.co/spaces/" in url or "github.com" in url or "gitlab.com" in url:
                pkg_type = "code"
            if pkg_type != artifact_type:
                return None

        return package

    # Activity & log tracking -------------------------------------------------
    def record_event(
        self,
        event_type: str,
        *,
        package: Optional[Package] = None,
        actor: str = "system",
        level: str = "INFO",
        message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Record an operational event for health monitoring."""

        timestamp = datetime.now(timezone.utc)
        package_info: Optional[dict] = None
        if package is not None:
            package_info = {
                "id": package.id,
                "name": package.name,
                "version": package.version,
            }

        event_details = details.copy() if details else {}
        event: dict = {
            "timestamp": timestamp,
            "type": event_type,
            "actor": actor,
            "package": package_info,
            "details": event_details,
            "level": level,
        }

        if message is None:
            event["message"] = self._default_event_message(event_type, package_info, event_details)
        else:
            event["message"] = message

        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "type": event_type,
            "message": event["message"],
        }

        with self._lock:
            self._activity_log.append(event)
            self._log_entries.append(log_entry)

    def get_activity_summary(
        self,
        *,
        window_minutes: int = 60,
        event_limit: int = 50,
    ) -> dict:
        """Return activity metrics for the specified time window."""

        now = datetime.now(timezone.utc)
        window_end = now
        window_start = now - timedelta(minutes=window_minutes)

        with self._lock:
            relevant_events = [
                event for event in self._activity_log if event["timestamp"] >= window_start
            ]

        counts = Counter(event["type"] for event in relevant_events)
        counts_map = {
            key: counts.get(key, 0) for key in self._known_event_types
        }
        counts_map["other"] = sum(
            count for event_type, count in counts.items() if event_type not in self._known_event_types
        )

        events_for_client = [
            {
                "timestamp": event["timestamp"].isoformat(),
                "type": event["type"],
                "actor": event["actor"],
                "level": event["level"],
                "package": event["package"],
                "message": event["message"],
                "details": event["details"],
            }
            for event in sorted(relevant_events, key=lambda e: e["timestamp"], reverse=True)[:event_limit]
        ]

        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "total_events": len(relevant_events),
            "counts": counts_map,
            "events": events_for_client,
        }

    def get_recent_logs(self, *, limit: int = 100, level: Optional[str] = None) -> List[dict]:
        """Return recent log-style entries for inspection."""

        with self._lock:
            entries = list(self._log_entries)

        if level:
            level_upper = level.upper()
            entries = [entry for entry in entries if entry["level"].upper() == level_upper]

        selected = entries[-limit:]

        return [
            {
                "timestamp": entry["timestamp"].isoformat(),
                "level": entry["level"],
                "type": entry["type"],
                "message": entry["message"],
            }
            for entry in selected
        ]

    def _default_event_message(
        self,
        event_type: str,
        package_info: Optional[dict],
        details: dict,
    ) -> str:
        """Generate a human-friendly default message for an event."""

        if event_type == "package_uploaded":
            return self._format_package_message("Uploaded package", package_info, details)
        if event_type == "model_ingested":
            return self._format_package_message("Ingested model package", package_info, details)
        if event_type == "package_deleted":
            return self._format_package_message("Deleted package", package_info, details)
        if event_type == "metrics_evaluated":
            metric_list = ", ".join(details.get("metrics", []))
            return self._format_package_message(
                f"Computed metrics ({metric_list}) for package", package_info, details
            )
        if event_type == "registry_reset":
            initiator = details.get("initiator", "unknown")
            return f"Registry reset initiated by {initiator}"

        label = event_type.replace("_", " ").title()
        return self._format_package_message(label, package_info, details)

    @staticmethod
    def _format_package_message(prefix: str, package_info: Optional[dict], details: dict) -> str:
        if not package_info:
            return prefix
        name = package_info.get("name", "unknown")
        version = package_info.get("version", "unknown")
        suffix = ""
        source = details.get("source")
        if source:
            suffix = f" (source: {source})"
        return f"{prefix} '{name}' v{version}{suffix}"


storage = RegistryStorage()
