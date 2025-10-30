from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class RepoView:
    """A class to interact with a repository's file system."""

    root: Path

    def exists(self, rel: str) -> bool:
        """Check if a file or directory exists relative to the repository root.

        Args:
            rel (str): The relative path to the file or directory.

        Returns:
            bool: True if the file or directory exists, False otherwise.
        """
        return (self.root / rel).exists()

    def read_text(self, rel: str, encoding: str = "utf-8") -> str:
        """Read the contents of a text file relative to the repository root.

        Args:
            rel (str): The relative path to the text file.
            encoding (str): The encoding to use when reading the file.
                Defaults to "utf-8".

        Returns:
            str: The contents of the text file.
        """
        return (self.root / rel).read_text(encoding=encoding)

    def read_json(self, rel: str) -> Any:
        """Read and parse a JSON file relative to the repository root.

        Args:
            rel (str): The relative path to the JSON file.

        Returns:
            Any: The parsed JSON data.
        """
        return json.loads(self.read_text(rel))

    def glob(self, pattern: str) -> Iterable[Path]:
        """Find all files matching a glob pattern relative to the repository root.

        Args:
            pattern (str): The glob pattern to match files.

        Returns:
            Iterable[Path]: An iterable of Path objects matching the pattern.
        """
        return self.root.glob(pattern)

    def size_bytes(self, rel: str) -> int:
        """Get the size of a file in bytes relative to the repository root.

        Args:
            rel (str): The relative path to the file.

        Returns:
            int: The size of the file in bytes.
        """
        return (self.root / rel).stat().st_size
