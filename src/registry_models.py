from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import re


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

    def check_version(self, version: str) -> bool:
        """Check if the package matches the given version string.

        Returns:
            bool: Whether or not the package matches the version string.
        """
        # A version can have the following syntaxes (a leading 'v' can be specified, and will be ignored):
        # x.y.z - Exact value (x = major, y = minor, z = patch)
        # x.y.a - x.y.b - Bounded range
        # ~x.y.z - Allows patch-level changes (z can change)
        # ~x.y - Equivalent to above
        # ~x - Allows minor-level changes
        # ^x.y.z - Allow changes that don't modify the left-most non-zero element in the [major, minor, patch] tuple
        if version[0] == "v":
            version = version[1:]  # Strip the 'v' at the beginning

        if version[0] == "~":
            version = version[1:]  # Strip the tilde out so we can handle the rest
            p = re.compile(r"(\d+)(?:\.(\d+)(?:\.(\d+))?)?")
            matches = p.match(version)
            if matches is None:
                return False
            if matches.lastindex is None or matches.lastindex > 3:
                return False  # Malformed version
            major = int(matches.group(1))
            minor = int(matches.group(2)) if matches.lastindex >= 2 else -1
            patch = int(matches.group(3)) if matches.lastindex == 3 else -1
