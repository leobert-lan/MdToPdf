"""PDF previewer.

MVP: write PDF bytes to a temp file and open with the system default viewer
     via ``os.startfile()`` (Windows native API — no extra dependency).

Enhanced (future): tkinter window with PyMuPDF page rendering.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from ..utils.temp_manager import get_temp_file

logger = logging.getLogger("mdtopdf.previewer")


class Previewer:
    """Opens a PDF for inspection before the final file is written."""

    def preview(self, pdf_bytes: bytes) -> None:
        """Write *pdf_bytes* to a temp file and open it with the system viewer."""
        tmp = get_temp_file(suffix=".pdf", prefix="preview_")
        tmp.write_bytes(pdf_bytes)
        logger.info("预览文件: %s", tmp)
        self._open(tmp)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _open(path: Path) -> None:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.run(["open", str(path)], check=False)
        else:
            import subprocess

            subprocess.run(["xdg-open", str(path)], check=False)

