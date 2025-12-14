"""Registry data models for packages, users, and authentication.

This module defines the core data structures used by the Model Registry,
including Package, User, and TokenInfo classes. It provides functionality
for version comparison, package serialization, and user/token management.
All models use dataclasses for simplicity and type safety.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


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
    """

    id: str
    artifact_type: str
    name: str
    version: str
    uploaded_by: str
    upload_timestamp: datetime
    size_bytes: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert package to dictionary with ISO timestamp.

        Returns:
            Dict[str, Any]: Package data as dictionary
        """
        return {
            "id": self.id,
            "artifact_type": self.artifact_type,
            "name": self.name,
            "version": self.version,
            "uploaded_by": self.uploaded_by,
            "upload_timestamp": self.upload_timestamp.isoformat(),
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }

    def get_version_int(self) -> int:
        """Returns the package's version as an integer, with the major, minor and
        patch concatenated with each other.

        Returns:
            int: The package's version as an integer."""
        expr = re.compile(r"(\d+)(?:\.(\d+)(?:\.(\d+))?)?")
        packageMatches = expr.match(self.version)
        packageMajor = int(packageMatches.group(1))
        packageMinor = (
            int(packageMatches.group(2)) if packageMatches.lastindex >= 2 else 0
        )
        packagePatch = (
            int(packageMatches.group(3)) if packageMatches.lastindex == 3 else 0
        )

        return int(str(packageMajor) + str(packageMinor) + str(packagePatch))

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

        singleVersion = re.compile(r"(\d+)(?:\.(\d+)(?:\.(\d+))?)?")
        versionRange = re.compile(
            r"(\d+)(?:\.(\d+)(?:\.(\d+))?)?(?: )*\-(?: )*(\d+)(?:\.(\d+)(?:\.(\d+))?)?"
        )
        # Parse package version
        packageMatches = singleVersion.match(self.version)
        if packageMatches is None:
            return False
        if packageMatches.lastindex is None or packageMatches.lastindex > 3:
            return False  # Malformed version
        packageMajor = int(packageMatches.group(1))
        packageMinor = (
            int(packageMatches.group(2)) if packageMatches.lastindex >= 2 else -1
        )
        packagePatch = (
            int(packageMatches.group(3)) if packageMatches.lastindex == 3 else -1
        )
        if version[0] == "v":
            version = version[1:]  # Strip the 'v' at the beginning

        tildeFound: bool = False
        caretFound: bool = False
        if version[0] == "~":
            version = version[1:]  # Strip the tilde out so we can handle the rest
            tildeFound = True
        if version[0] == "^":
            version = version[1:]
            caretFound = True
        if caretFound or tildeFound:
            testMatches = singleVersion.match(version)
            if testMatches is None:
                return False
            if testMatches.lastindex is None or testMatches.lastindex > 3:
                return False  # Malformed version
            testMajor = int(testMatches.group(1))
            testMinor = int(testMatches.group(2)) if testMatches.lastindex >= 2 else -1
            testPatch = int(testMatches.group(3)) if testMatches.lastindex == 3 else -1

            if tildeFound:
                if testMinor == -1:
                    # Minor number can change
                    return testMajor == packageMajor
                else:
                    return testMajor == packageMajor and testMinor == packageMinor
            elif caretFound:
                if testMajor == 0:
                    if testMinor <= 0:
                        return testPatch == -1 or testPatch == packagePatch
                    else:
                        return testMinor == packageMinor
                else:
                    return testMajor == packageMajor
        else:
            # Check if we are given a version range
            testMatches = versionRange.match(version)
            if testMatches is None:
                # Must be just 1 version
                testMatches = singleVersion.match(version)
                if testMatches is None:
                    return False
                if testMatches.lastindex is None or testMatches.lastindex > 3:
                    return False  # Malformed version
                testMajor = int(testMatches.group(1))
                testMinor = (
                    int(testMatches.group(2)) if testMatches.lastindex >= 2 else -1
                )
                testPatch = (
                    int(testMatches.group(3)) if testMatches.lastindex == 3 else -1
                )
                if testMinor == -1:
                    return testMajor == packageMajor
                elif testPatch == -1:
                    return testMajor == packageMajor and testMinor == packageMinor
                else:
                    return (
                        testMajor == packageMajor
                        and testMinor == packageMinor
                        and testPatch == packagePatch
                    )
            else:
                if testMatches.lastindex is None or testMatches.lastindex > 6:
                    return False  # Malformed version
                lowerTestMajor = int(testMatches.group(1))
                lowerTestMinor = (
                    int(testMatches.group(2)) if testMatches.lastindex >= 2 else 0
                )
                lowerTestPatch = (
                    int(testMatches.group(3)) if testMatches.lastindex >= 3 else 0
                )

                upperTestMajor = int(testMatches.group(4))
                upperTestMinor = (
                    int(testMatches.group(5)) if testMatches.lastindex >= 5 else 0
                )
                upperTestPatch = (
                    int(testMatches.group(6)) if testMatches.lastindex == 6 else 0
                )

                if lowerTestMajor < packageMajor and packageMajor < upperTestMajor:
                    return True
                elif lowerTestMajor == packageMajor or packageMajor == upperTestMajor:
                    if lowerTestMinor < packageMinor and packageMinor < upperTestMinor:
                        return True
                    elif (
                        lowerTestMinor == packageMinor or packageMinor == upperTestMinor
                    ):
                        if (
                            lowerTestPatch <= packagePatch
                            and packagePatch <= upperTestPatch
                        ):
                            return True
                        else:
                            return False
                    else:
                        return False
                else:
                    return False
        # Catch all
        return False


@dataclass
class User:
    """Represents a user in the registry.

    Attributes:
        user_id: Unique user identifier (UUID)
        username: Unique username
        password_hash: Hashed password (never store plaintext!)
        permissions: List of permissions ('upload', 'search', 'download', 'admin')
        is_admin: Whether user has admin privileges
        created_at: When user was created
    """

    user_id: str
    username: str
    password_hash: str
    permissions: List[str] = field(default_factory=list)
    is_admin: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary (without password hash).

        Returns:
            Dict[str, Any]: User data as dictionary (password_hash excluded for security)
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "permissions": self.permissions,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class TokenInfo:
    """Represents an authentication token.

    Attributes:
        token: The authentication token string
        user_id: User ID this token belongs to
        username: Username for convenience
        created_at: When token was created
        usage_count: Number of times token has been used
        expires_at: When token expires
    """

    token: str
    user_id: str
    username: str
    created_at: datetime
    usage_count: int = 0
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        """Check if token has expired (based on time or usage count).

        Returns:
            bool: True if token is expired
        """
        # Token expires after 1000 uses OR 10 hours
        if self.usage_count >= 1000:
            return True
        if datetime.now(timezone.utc) >= self.expires_at:
            return True
        return False

    def increment_usage(self) -> None:
        """Increment usage counter."""
        self.usage_count += 1
