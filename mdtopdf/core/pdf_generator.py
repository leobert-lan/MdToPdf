"""WeasyPrint wrapper — converts fully assembled HTML to PDF bytes or file."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("mdtopdf.pdf_generator")


class PDFGenerator:
    """Thin wrapper around WeasyPrint's HTML-to-PDF conversion."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_bytes(self, html: str) -> bytes:
        """Convert *html* to PDF and return the raw bytes (no disk I/O)."""
        HTML = self._import_weasyprint()
        logger.debug("开始 WeasyPrint HTML → PDF 转换 (内存模式)")
        pdf_bytes: bytes = HTML(string=html).write_pdf()
        logger.debug("WeasyPrint 转换完成 (%d bytes)", len(pdf_bytes))
        return pdf_bytes

    def generate_file(self, html: str, output_path: Path) -> None:
        """Convert *html* to PDF and write to *output_path*."""
        HTML = self._import_weasyprint()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.debug("开始 WeasyPrint HTML → PDF 转换 → %s", output_path)
        HTML(string=html).write_pdf(str(output_path))
        size_kb = output_path.stat().st_size / 1024
        logger.info("已生成 PDF: %s (%.1f KB)", output_path, size_kb)

    @staticmethod
    def _import_weasyprint():
        """Import WeasyPrint with a user-friendly error for missing GTK3."""
        try:
            from weasyprint import HTML
            return HTML
        except OSError as exc:
            if "libgobject" in str(exc) or "error 0x7e" in str(exc):
                raise RuntimeError(
                    "WeasyPrint 无法加载 GTK3 运行时库（libgobject-2.0-0）。\n"
                    "Windows 下请安装 GTK3 运行时：\n"
                    "  https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                    "安装完成后重启命令行窗口再试。"
                ) from exc
            raise

