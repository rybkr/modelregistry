from typing import Dict, List, Optional
from datetime import datetime
from registry_models import Package
import re


class RegistryStorage:
    
    def __init__(self) -> None:
        self.packages: Dict[str, Package] = {}
        self.reset()
    
    def reset(self) -> None:
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
    
    def search_packages(self, query: str, use_regex: bool = False) -> List[Package]:
        results = []
        
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error:
                return []
            
            for package in self.packages.values():
                if pattern.search(package.name):
                    results.append(package)
                elif 'readme' in package.metadata and pattern.search(str(package.metadata.get('readme', ''))):
                    results.append(package)
        else:
            query_lower = query.lower()
            for package in self.packages.values():
                if query_lower in package.name.lower():
                    results.append(package)
                elif 'readme' in package.metadata and query_lower in str(package.metadata.get('readme', '')).lower():
                    results.append(package)
        
        return results


storage = RegistryStorage()
