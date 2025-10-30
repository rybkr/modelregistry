"""
Simple storage layer for the Model Registry.
Initially in-memory, to be upgraded to AWS services.
"""

from typing import Dict, List, Optional
from datetime import datetime
from registry_models import Package


class RegistryStorage:
    def __init__(self):
        self.packages: Dict[str, Package] = {}
        self.reset()
    
    def reset(self):
        self.packages.clear()
    
    def create_package(self, package: Package) -> Package:
        self.packages[package.id] = package
        return package
    
    def get_package(self, package_id: str) -> Optional[Package]:
        return self.packages.get(package_id)
    
    def list_packages(self, offset: int = 0, limit: int = 100) -> List[Package]:
        all_packages = list(self.packages.values())
        return all_packages[offset:offset + limit]
    
    def delete_package(self, package_id: str) -> bool:
        if package_id in self.packages:
            del self.packages[package_id]
            return True
        return False
    
    def search_packages(self, query: str) -> List[Package]:
        results = []
        query_lower = query.lower()
        for package in self.packages.values():
            if query_lower in package.name.lower():
                results.append(package)
        return results


# Global storage instance
storage = RegistryStorage()
