from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Package:
    """Represents a package in the registry.

    Attributes:
        id: Unique package identifier (UUID)
        name: Package name
        version: Package version string
        uploaded_by: Username of uploader
        upload_timestamp: When package was uploaded
        size_bytes: Package size in bytes
        metadata: Additional package metadata (e.g., URL, scores, readme)
        s3_key: Optional S3 storage key for package content
    """
    id: str
    name: str
    version: str
    uploaded_by: str
    upload_timestamp: datetime
    size_bytes: int
    metadata: Dict[str, Any]
    s3_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert package to dictionary with ISO timestamp.

        Returns:
            Dict[str, Any]: Package data as dictionary
        """
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "uploaded_by": self.uploaded_by,
            "upload_timestamp": self.upload_timestamp.isoformat(),
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
            "s3_key": self.s3_key,
        }
