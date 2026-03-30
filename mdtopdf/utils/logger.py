"""Centralised logging setup.

Call ``setup_logger(verbose)`` once from main.py.
Everywhere else, call ``get_logger(__name__)`` to obtain a child logger.
"""

from __future__ import annotations

import logging
import sys


_FMT = "[%(levelname)-8s] %(asctime)s [%(name)s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logger(verbose: bool = False) -> logging.Logger:
    """Configure root logger and return the top-level mdtopdf logger."""
    level = logging.DEBUG if verbose else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))

    root = logging.getLogger("mdtopdf")
    root.setLevel(level)
    # Avoid adding duplicate handlers when called multiple times (e.g., in tests)
    if not root.handlers:
        root.addHandler(handler)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger scoped to *name* under the mdtopdf namespace."""
    if not name.startswith("mdtopdf"):
        name = f"mdtopdf.{name}"
    return logging.getLogger(name)

