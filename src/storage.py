from typing import Dict, List, Optional
from registry_models import Package
import re


class RegistryStorage:
    """In-memory storage for package registry.

    Provides CRUD operations and search functionality for packages.
    All data is stored in memory and will be lost on restart.
    """

    def __init__(self):
        """Initialize empty package storage."""
        self.packages: Dict[str, Package] = {}
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

    def delete_package(self, package_id: str) -> bool:
        """Delete a package by ID.

        Args:
            package_id: Unique package identifier

        Returns:
            bool: True if deleted, False if not found
        """
        if package_id in self.packages:
            del self.packages[package_id]
            return True
        return False

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


storage = RegistryStorage()
