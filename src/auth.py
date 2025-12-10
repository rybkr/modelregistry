"""Authentication and authorization utilities for the Model Registry.

This module provides secure password hashing and verification using
hashlib with SHA-256 and salt. For production, consider using bcrypt or argon2.
"""

import hashlib
import secrets
from typing import Tuple


def hash_password(password: str) -> str:
    """Hash a password securely using SHA-256 with salt.

    Args:
        password: Plain text password to hash

    Returns:
        str: Hashed password in format 'salt$hash'
    """
    # Generate a random salt (32 bytes = 256 bits)
    salt = secrets.token_hex(32)

    # Hash password with salt
    pwd_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

    # Return salt and hash combined
    return f"{salt}${pwd_hash}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: Plain text password to verify
        password_hash: Stored hash in format 'salt$hash'

    Returns:
        bool: True if password matches, False otherwise
    """
    try:
        # Extract salt and hash
        salt, stored_hash = password_hash.split('$', 1)

        # Hash the provided password with the stored salt
        pwd_hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

        # Use secrets.compare_digest to prevent timing attacks
        return secrets.compare_digest(pwd_hash, stored_hash)
    except (ValueError, AttributeError):
        # Invalid hash format
        return False


def generate_token() -> str:
    """Generate a secure random authentication token.

    Returns:
        str: 64-character hexadecimal token
    """
    return secrets.token_hex(32)
