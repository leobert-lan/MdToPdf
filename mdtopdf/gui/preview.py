"""PDF preview window.

If PyMuPDF + Pillow are installed: renders pages inside a Toplevel canvas
with navigation and zoom controls.

Fallback (no PyMuPDF): writes bytes to a temp file and opens it with the
system default PDF viewer, then asks the user whether to save.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable, Optional

logger = logging.getLogger("mdtopdf.gui.preview")

# ── Optional dependency detection ────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageTk

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    logger.debug("PyMuPDF 未安装，将使用系统查看器作为预览回退方案")


# ── Internal preview window ───────────────────────────────────────────────────


class PDFPreviewWindow:
    """Internal PDF preview using PyMuPDF + Pillow (requires both packages)."""

    _MIN_ZOOM = 0.3
    _MAX_ZOOM = 4.0
    _ZOOM_STEP = 1.25
    _DEFAULT_ZOOM = 1.35

    def __init__(
        self,
        parent: tk.Misc,
        pdf_bytes: bytes,
        output_path: Optional[Path] = None,
        on_save: Optional[Callable[[], None]] = None,
    ) -> None:
        self._parent = parent
        self._pdf_bytes = pdf_bytes
        self._output_path = output_path
        self._on_save = on_save

        self._doc = fitz.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[name-defined]
        self._page_count = len(self._doc)
        self._current_page = 0
        self._zoom = self._DEFAULT_ZOOM
        self._photo: Optional[ImageTk.PhotoImage] = None  # must keep a reference!

        self._build_window()
        self._render_page()

    # ── Window construction ───────────────────────────────────────────────────

    def _build_window(self) -> None:
        win = tk.Toplevel(self._parent)
        name = self._output_path.name if self._output_path else "预览"
        win.title(f"PDF 预览 — {name}")
        win.minsize(640, 720)
        win.resizable(True, True)
        win.grab_set()  # modal: blocks the main window
        self._win = win

        self._build_toolbar()
        self._build_canvas_area()
        self._build_bottom_bar()

        win.bind("<Left>", lambda _e: self._prev_page())
        win.bind("<Right>", lambda _e: self._next_page())
        win.bind("<Prior>", lambda _e: self._prev_page())   # Page Up
        win.bind("<Next>", lambda _e: self._next_page())    # Page Down
        win.bind("<plus>", lambda _e: self._zoom_in())
        win.bind("<minus>", lambda _e: self._zoom_out())
        win.bind("<KP_Add>", lambda _e: self._zoom_in())
        win.bind("<KP_Subtract>", lambda _e: self._zoom_out())

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self._win, padding=(6, 4))
        bar.pack(fill=tk.X, side=tk.TOP)

        # Navigation
        ttk.Button(bar, text="◀", width=3, command=self._prev_page).pack(side=tk.LEFT)
        self._page_label = ttk.Label(bar, text="─ / ─", width=12, anchor=tk.CENTER)
        self._page_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="▶", width=3, command=self._next_page).pack(side=tk.LEFT)

        ttk.Separator(bar, orient="vertical").pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Zoom
        ttk.Button(bar, text="放大 ＋", command=self._zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="缩小 −", command=self._zoom_out).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="适合", command=self._zoom_reset).pack(side=tk.LEFT, padx=2)

        self._zoom_label = ttk.Label(bar, text="135%", width=6, anchor=tk.CENTER)
        self._zoom_label.pack(side=tk.LEFT, padx=(4, 0))

    def _build_canvas_area(self) -> None:
        container = ttk.Frame(self._win)
        container.pack(fill=tk.BOTH, expand=True, padx=4, pady=(2, 0))

        self._canvas = tk.Canvas(container, bg="#525659", highlightthickness=0)
        v_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        h_scroll = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self._canvas.xview)

        self._canvas.configure(
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
        )

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>", lambda _e: self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind("<Button-5>", lambda _e: self._canvas.yview_scroll(1, "units"))

    def _build_bottom_bar(self) -> None:
        bar = ttk.Frame(self._win, padding=(6, 6))
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        if self._on_save is not None:
            ttk.Button(
                bar,
                text="✓  保存 PDF",
                command=self._save_and_close,
            ).pack(side=tk.LEFT, padx=(0, 8))
            ttk.Button(bar, text="✗  放弃", command=self._win.destroy).pack(side=tk.LEFT)
        else:
            ttk.Button(bar, text="关闭", command=self._win.destroy).pack(side=tk.RIGHT)

    # ── Page rendering ────────────────────────────────────────────────────────

    def _render_page(self) -> None:
        page = self._doc[self._current_page]
        mat = fitz.Matrix(self._zoom, self._zoom)  # type: ignore[name-defined]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)  # type: ignore[name-defined]

        img = Image.frombytes("RGB", (pix.width, pix.height), bytes(pix.samples))
        self._photo = ImageTk.PhotoImage(img)

        self._canvas.delete("all")
        # Centre the page on the dark canvas background
        self._canvas.create_image(4, 4, anchor="nw", image=self._photo)
        self._canvas.configure(
            scrollregion=(0, 0, pix.width + 8, pix.height + 8)
        )
        self._canvas.yview_moveto(0)

        self._page_label.configure(
            text=f"{self._current_page + 1} / {self._page_count}"
        )
        self._zoom_label.configure(text=f"{int(self._zoom * 100)}%")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()

    def _next_page(self) -> None:
        if self._current_page < self._page_count - 1:
            self._current_page += 1
            self._render_page()

    # ── Zoom ─────────────────────────────────────────────────────────────────

    def _zoom_in(self) -> None:
        self._zoom = min(self._zoom * self._ZOOM_STEP, self._MAX_ZOOM)
        self._render_page()

    def _zoom_out(self) -> None:
        self._zoom = max(self._zoom / self._ZOOM_STEP, self._MIN_ZOOM)
        self._render_page()

    def _zoom_reset(self) -> None:
        self._zoom = self._DEFAULT_ZOOM
        self._render_page()

    # ── Mouse wheel ───────────────────────────────────────────────────────────

    def _on_mousewheel(self, event: tk.Event) -> None:  # type: ignore[type-arg]
        if event.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save_and_close(self) -> None:
        if self._on_save:
            self._on_save()
        self._win.destroy()


# ── Public API ────────────────────────────────────────────────────────────────


def show_preview(
    parent: tk.Misc,
    pdf_bytes: bytes,
    output_path: Optional[Path] = None,
    on_save: Optional[Callable[[], None]] = None,
) -> None:
    """Show PDF preview — uses internal window (PyMuPDF) or system viewer."""
    if HAS_PYMUPDF:
        PDFPreviewWindow(parent, pdf_bytes, output_path=output_path, on_save=on_save)
    else:
        _system_viewer_fallback(parent, pdf_bytes, output_path, on_save)


def _system_viewer_fallback(
    parent: tk.Misc,
    pdf_bytes: bytes,
    output_path: Optional[Path],
    on_save: Optional[Callable[[], None]],
) -> None:
    """Write bytes to a temp file, open with system viewer, then ask to save."""
    from ..utils.temp_manager import get_temp_file

    tmp = get_temp_file(suffix=".pdf", prefix="preview_")
    tmp.write_bytes(pdf_bytes)
    logger.info("预览文件（系统查看器）: %s", tmp)
    _open_with_system(tmp)

    if on_save is not None:
        dest = str(output_path) if output_path else "输出 PDF"
        confirmed = messagebox.askyesno(
            "预览已打开",
            f"PDF 已在系统查看器中打开。\n\n确认后将保存到：\n{dest}",
            parent=parent,
        )
        if confirmed:
            on_save()


def _open_with_system(path: Path) -> None:
    import os

    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.run(["open", str(path)], check=False)
        else:
            import subprocess

            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:
        logger.warning("无法打开系统查看器: %s", exc)

