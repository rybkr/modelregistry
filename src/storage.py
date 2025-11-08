from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Dict, List, Optional
import re

from registry_models import Package


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
        """Clear all packages from storage."""
        self.packages.clear()

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

        Args:
            query: Search string or regex pattern
            use_regex: If True, treat query as regex pattern

        Returns:
            List[Package]: Matching packages, empty list if regex invalid
        """
        results = []
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                return []
            for package in self.packages.values():
                if pattern.search(package.name):
                    results.append(package)
                elif "readme" in package.metadata and pattern.search(
                    str(package.metadata.get("readme", ""))
                ):
                    results.append(package)
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
