"""WeasyPrint wrapper — converts fully assembled HTML to PDF bytes or file."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("mdtopdf.pdf_generator")


def _fix_macos_locale() -> None:
    """Ensure LANG/LC_ALL are set to a fontconfig-compatible value on macOS.

    fontconfig prints "ignoring UTF-8: not a valid region tag" when the locale
    string uses a charset suffix that it cannot parse (e.g. ``zh_CN.UTF-8``
    exported from a shell with a non-standard LC_ALL).  Setting LANG to the
    POSIX-standard ``en_US.UTF-8`` silences the warning and avoids a related
    crash in pango_fc_font_map_load_fontset when called off the main thread.
    """
    if sys.platform != "darwin":
        return
    lang = os.environ.get("LANG", "")
    # Only override when the current value looks problematic for fontconfig
    # (contains a charset suffix that fontconfig rejects as a region tag).
    if ".UTF-8" in lang or ".utf-8" in lang or not lang:
        os.environ.setdefault("LANG", "en_US.UTF-8")
        os.environ.setdefault("LC_CTYPE", "en_US.UTF-8")


class PDFGenerator:
    """Thin wrapper around WeasyPrint's HTML-to-PDF conversion."""

    # Guards the one-time main-thread fontstack warm-up (macOS only).
    _fontstack_warmed_up: bool = False

    _MACOS_LIBRARY_PATTERNS: tuple[str, ...] = (
        "libffi*.dylib",
        "libglib-2.0*.dylib",
        "libgobject-2.0*.dylib",
        "libharfbuzz*.dylib",
        "libfreetype*.dylib",
        "libpango-1.0*.dylib",
        "libpangocairo-1.0*.dylib",
        "libgdk_pixbuf-2.0*.dylib",
        "libcairo*.dylib",
    )

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
        """Import WeasyPrint with platform-specific recovery/help text."""
        _fix_macos_locale()
        try:
            from weasyprint import HTML
            return HTML
        except OSError as exc:
            if sys.platform == "darwin" and PDFGenerator._attempt_preload_macos_runtime_libraries():
                PDFGenerator._clear_partial_weasyprint_modules()
                try:
                    from weasyprint import HTML

                    logger.info("已预加载 macOS WeasyPrint 原生依赖库")
                    return HTML
                except OSError as retry_exc:
                    raise PDFGenerator._build_runtime_error(retry_exc) from retry_exc
            raise PDFGenerator._build_runtime_error(exc) from exc

    @staticmethod
    def _clear_partial_weasyprint_modules() -> None:
        for name in tuple(sys.modules):
            if name == "weasyprint" or name.startswith("weasyprint."):
                sys.modules.pop(name, None)

    @classmethod
    def _attempt_preload_macos_runtime_libraries(cls) -> bool:
        if sys.platform != "darwin":
            return False

        loaded_any = False
        seen: set[Path] = set()
        rtld_global = getattr(ctypes, "RTLD_GLOBAL", 0)

        for directory in cls._candidate_library_dirs():
            for pattern in cls._MACOS_LIBRARY_PATTERNS:
                for candidate in sorted(directory.glob(pattern)):
                    resolved = candidate.resolve()
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    try:
                        ctypes.CDLL(str(resolved), mode=rtld_global)
                        loaded_any = True
                        logger.debug("已预加载 macOS 依赖库: %s", resolved)
                    except OSError as lib_exc:
                        logger.debug("预加载动态库失败 (%s): %s", resolved, lib_exc)

        return loaded_any

    @staticmethod
    def _candidate_library_dirs() -> list[Path]:
        candidates: list[Path] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.extend(
                [
                    Path(meipass),
                    Path(meipass) / "lib",
                    Path(meipass) / "Frameworks",
                ]
            )

        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            [
                exe_dir,
                exe_dir / "lib",
                exe_dir / "Frameworks",
                Path("/opt/homebrew/lib"),
                Path("/usr/local/lib"),
                Path("/opt/local/lib"),
            ]
        )

        unique_dirs: list[Path] = []
        seen: set[Path] = set()
        for directory in candidates:
            if directory.exists() and directory not in seen:
                unique_dirs.append(directory)
                seen.add(directory)
        return unique_dirs

    @classmethod
    def warmup(cls) -> None:
        """Fix locale and preload native libraries on macOS before any worker thread starts.

        This is a lightweight operation (no PDF rendering).  The actual root
        cause of macOS crashes is a mixed-library situation where Homebrew pango
        and conda fontconfig are loaded simultaneously; that must be fixed at the
        environment level (see :py:meth:`_build_runtime_error` for guidance).
        This method only handles the ``LC_CTYPE=UTF-8`` locale warning and
        pre-loads shared libraries so they resolve consistently.

        The method is idempotent — subsequent calls are a no-op.
        """
        if cls._fontstack_warmed_up:
            return
        cls._fontstack_warmed_up = True

        if sys.platform != "darwin":
            return

        _fix_macos_locale()
        cls._attempt_preload_macos_runtime_libraries()
        logger.debug("macOS 原生库预加载完成")

    @staticmethod
    def _build_runtime_error(exc: OSError) -> RuntimeError:
        detail = str(exc)
        if "libgobject" in detail or "error 0x7e" in detail:
            return RuntimeError(
                "WeasyPrint 无法加载 GTK3 运行时库（libgobject-2.0-0）。\n"
                "Windows 下请安装 GTK3 运行时：\n"
                "  https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                "安装完成后重启命令行窗口再试。"
            )

        if sys.platform == "darwin":
            return RuntimeError(
                "WeasyPrint 无法在 macOS 上加载 PDF 导出所需的原生库。\n\n"
                "【最常见原因】conda 环境中缺少 pango，导致 WeasyPrint 混用 Homebrew 的\n"
                "libpango/libpangoft2 和 conda 的 libfontconfig，两份 fontconfig 同时\n"
                "加载引发 SIGSEGV。\n\n"
                "修复方法（conda 环境）：\n"
                "  conda install -c conda-forge pango\n\n"
                "修复方法（系统 Python / pip 环境）：\n"
                "  brew install cairo pango gdk-pixbuf libffi\n\n"
                "如果你运行的是打包后的 .app，请确认这些库位于同一来源"
                "（全部 Homebrew 或全部 conda-forge）。\n"
                f"原始错误: {detail}"
            )

        return RuntimeError(f"WeasyPrint 加载失败: {detail}")

