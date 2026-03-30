"""Temporary file/directory lifecycle manager.

Creates a single temp directory per process and registers an atexit hook to
clean it up automatically.  All modules should obtain temp paths via
``get_temp_file()`` / ``get_temp_dir()`` rather than calling tempfile directly.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path


class TempManager:
    """Manages a private temp directory for the current process."""

    def __init__(self) -> None:
        self._root = Path(tempfile.mkdtemp(prefix="mdtopdf_"))
        atexit.register(self.cleanup)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_temp_file(self, suffix: str = "", prefix: str = "tmp") -> Path:
        """Return a *path* inside the temp directory (file not yet created)."""
        fd, path = tempfile.mkstemp(dir=self._root, suffix=suffix, prefix=prefix)
        import os

        os.close(fd)  # close the OS file descriptor; caller opens it themselves
        return Path(path)

    def get_temp_dir(self, prefix: str = "dir") -> Path:
        """Return a newly created sub-directory inside the temp directory."""
        return Path(tempfile.mkdtemp(dir=self._root, prefix=prefix))

    def cleanup(self) -> None:
        """Remove the entire temp directory tree (called on process exit)."""
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)


# Module-level singleton — import and use directly
_manager = TempManager()


def get_temp_file(suffix: str = "", prefix: str = "tmp") -> Path:
    """Convenience wrapper around the global TempManager."""
    return _manager.get_temp_file(suffix=suffix, prefix=prefix)


def get_temp_dir(prefix: str = "dir") -> Path:
    """Convenience wrapper around the global TempManager."""
    return _manager.get_temp_dir(prefix=prefix)


def cleanup() -> None:
    """Explicitly trigger cleanup (normally handled by atexit)."""
    _manager.cleanup()

