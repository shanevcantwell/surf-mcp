"""
FileSystemDriver - Navigate and operate on local filesystem.

Provides:
- cwd-based navigation with history
- Sandbox boundary enforcement
- File read/write operations
- Directory listing with metadata
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import HistoryEntry, NavigatorDriver, NavigatorState

logger = logging.getLogger(__name__)


class FileSystemDriver(NavigatorDriver):
    """
    Navigate and operate on local filesystem.

    Maintains current working directory (cwd) and navigation history.
    Optionally enforces sandbox boundary (cannot escape root).
    """

    driver_type = "filesystem"

    def __init__(self, root: str, sandbox: bool = True):
        """
        Initialize filesystem driver.

        Args:
            root: Root directory for navigation
            sandbox: If True, cannot navigate above root
        """
        self.root = Path(root).resolve()
        self.cwd = self.root
        self.sandbox = sandbox
        self.history: List[HistoryEntry] = []
        self.history_index = -1

        # Tracking for session summary
        self.files_read: List[str] = []
        self.files_written: List[str] = []

        # Ensure root exists
        self.root.mkdir(parents=True, exist_ok=True)

        # Add initial location to history so back() works after first goto()
        self._add_history("init", str(self.root))

        logger.info(f"FileSystemDriver initialized: root={self.root}, sandbox={sandbox}")

    def _is_in_sandbox(self, path: Path) -> bool:
        """Check if path is within sandbox boundary."""
        if not self.sandbox:
            return True
        try:
            path.relative_to(self.root)
            return True
        except ValueError:
            return False

    def _sandbox_error(self, action: str) -> NavigatorState:
        """Return NavigatorState error for sandbox violation."""
        return NavigatorState(
            location=str(self.cwd),
            success=False,
            error=f"Cannot {action} outside sandbox: {self.root}",
        )

    async def goto(self, location: str) -> NavigatorState:
        """
        Change directory (relative or absolute).

        Args:
            location: Target directory (relative to cwd or absolute)

        Returns:
            NavigatorState with success status
        """
        target = (self.cwd / location).resolve()

        if not self._is_in_sandbox(target):
            return self._sandbox_error("navigate")

        if not target.exists():
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=f"Path does not exist: {target}",
            )

        if not target.is_dir():
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=f"Not a directory: {target}",
            )

        self.cwd = target
        self._add_history("goto", str(target))

        return NavigatorState(
            location=str(self.cwd),
            success=True,
            snapshot=await self.snapshot(),
        )

    async def current(self) -> str:
        """Return current working directory."""
        return str(self.cwd)

    async def back(self) -> NavigatorState:
        """Go to previous location in history."""
        if self.history_index <= 0:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error="No previous location in history",
            )

        self.history_index -= 1
        prev_location = self.history[self.history_index].location
        self.cwd = Path(prev_location)

        return NavigatorState(
            location=str(self.cwd),
            success=True,
            snapshot=await self.snapshot(),
        )

    async def forward(self) -> NavigatorState:
        """Go to next location in history."""
        if self.history_index >= len(self.history) - 1:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error="No forward location in history",
            )

        self.history_index += 1
        next_location = self.history[self.history_index].location
        self.cwd = Path(next_location)

        return NavigatorState(
            location=str(self.cwd),
            success=True,
            snapshot=await self.snapshot(),
        )

    async def list(self) -> List[Dict[str, Any]]:
        """
        List directory contents with metadata.

        Returns:
            List of entries with name, type, size, modified
        """
        entries = []
        try:
            for item in self.cwd.iterdir():
                stat = item.stat()
                entries.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
        except PermissionError as e:
            logger.warning(f"Permission error listing {self.cwd}: {e}")

        # Sort: directories first, then alphabetically
        return sorted(entries, key=lambda x: (x["type"] != "directory", x["name"]))

    async def read(self, target: Optional[str] = None) -> str:
        """
        Read file content.

        Args:
            target: Relative path to file (required for filesystem)

        Returns:
            File content as string

        Raises:
            ValueError: If target is not a file
        """
        if not target:
            raise ValueError("Target file path required for filesystem read")

        path = (self.cwd / target).resolve()

        if not self._is_in_sandbox(path):
            raise ValueError(f"Cannot read outside sandbox: {self.root}")

        if not path.is_file():
            raise ValueError(f"Cannot read: {path} is not a file")

        content = path.read_text()
        self.files_read.append(str(path))
        logger.debug(f"Read file: {path} ({len(content)} chars)")

        return content

    async def write(self, target: str, content: str) -> NavigatorState:
        """
        Write content to file.

        Args:
            target: Relative path to file
            content: Content to write

        Returns:
            NavigatorState with success status
        """
        path = (self.cwd / target).resolve()

        if not self._is_in_sandbox(path):
            return self._sandbox_error("write")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            self.files_written.append(str(path))
            logger.info(f"Wrote file: {path} ({len(content)} chars)")

            return NavigatorState(
                location=str(self.cwd),
                success=True,
            )
        except Exception as e:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=str(e),
            )

    async def delete(self, target: str, recursive: bool = False) -> NavigatorState:
        """
        Delete file or directory.

        Args:
            target: Relative path to delete
            recursive: If True, delete directories recursively

        Returns:
            NavigatorState with success status
        """
        path = (self.cwd / target).resolve()

        if not self._is_in_sandbox(path):
            return self._sandbox_error("delete")

        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                if recursive:
                    shutil.rmtree(path)
                else:
                    path.rmdir()  # Only works if empty
            else:
                return NavigatorState(
                    location=str(self.cwd),
                    success=False,
                    error=f"Path does not exist: {path}",
                )

            logger.info(f"Deleted: {path}")
            return NavigatorState(
                location=str(self.cwd),
                success=True,
            )
        except Exception as e:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=str(e),
            )

    async def copy(self, source: str, destination: str) -> NavigatorState:
        """
        Copy file or directory.

        Args:
            source: Relative source path
            destination: Relative destination path

        Returns:
            NavigatorState with success status
        """
        src_path = (self.cwd / source).resolve()
        dst_path = (self.cwd / destination).resolve()

        if not self._is_in_sandbox(src_path) or not self._is_in_sandbox(dst_path):
            return self._sandbox_error("copy")

        try:
            if src_path.is_file():
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
            elif src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            else:
                return NavigatorState(
                    location=str(self.cwd),
                    success=False,
                    error=f"Source does not exist: {src_path}",
                )

            logger.info(f"Copied: {src_path} -> {dst_path}")
            return NavigatorState(
                location=str(self.cwd),
                success=True,
            )
        except Exception as e:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=str(e),
            )

    async def move(self, source: str, destination: str) -> NavigatorState:
        """
        Move/rename file or directory.

        Args:
            source: Relative source path
            destination: Relative destination path

        Returns:
            NavigatorState with success status
        """
        src_path = (self.cwd / source).resolve()
        dst_path = (self.cwd / destination).resolve()

        if not self._is_in_sandbox(src_path) or not self._is_in_sandbox(dst_path):
            return self._sandbox_error("move")

        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))

            logger.info(f"Moved: {src_path} -> {dst_path}")
            return NavigatorState(
                location=str(self.cwd),
                success=True,
            )
        except Exception as e:
            return NavigatorState(
                location=str(self.cwd),
                success=False,
                error=str(e),
            )

    async def find(self, pattern: str, recursive: bool = True) -> List[str]:
        """
        Find files matching glob pattern.

        Args:
            pattern: Glob pattern (e.g., "*.py", "**/*.txt")
            recursive: If True and pattern has no **, search recursively

        Returns:
            List of matching file paths (relative to cwd)
        """
        if recursive and "**" not in pattern:
            pattern = f"**/{pattern}"

        matches = []
        for path in self.cwd.glob(pattern):
            if not self._is_in_sandbox(path):
                continue

            rel_path = path.relative_to(self.cwd)
            matches.append(str(rel_path))

        return sorted(matches)

    async def snapshot(self) -> str:
        """
        Return JSON representation of directory listing.

        Returns:
            JSON string with cwd, root, and entries
        """
        listing = await self.list()
        return json.dumps(
            {
                "cwd": str(self.cwd),
                "root": str(self.root),
                "entries": listing,
            },
            indent=2,
        )

    async def cleanup(self) -> None:
        """No cleanup needed for filesystem."""
        logger.debug(f"FileSystemDriver cleanup: {len(self.files_read)} reads, {len(self.files_written)} writes")
