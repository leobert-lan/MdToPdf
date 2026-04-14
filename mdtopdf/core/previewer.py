"""PDF previewer.

MVP: write PDF bytes to a temp file and open it with the system default PDF
viewer.

Enhanced (future): tkinter window with PyMuPDF page rendering.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.file_utils import open_with_default_app
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
        open_with_default_app(path)

