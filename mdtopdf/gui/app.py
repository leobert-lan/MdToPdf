"""Main GUI window for mdtopdf.

Architecture
------------
- Main thread : tkinter event loop + queue polling (every 100 ms)
- Worker thread: runs the full conversion pipeline, forwards log records
  and the final result through a queue.Queue

Queue message shapes
--------------------
("log",     tag: str,        text: str)
("success", pdf_bytes: bytes, output_path: Path, preview: bool)
("error",   msg: str,        traceback: str)
"""

from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any, Optional

import frontmatter

# ── DPI awareness (Windows) ───────────────────────────────────────────────────
try:
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ── GUI log handler ───────────────────────────────────────────────────────────


class GUILogHandler(logging.Handler):
    """Forwards log records to a queue so the main thread can display them."""

    _TAG_MAP = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "ERROR",
    }

    def __init__(self, result_queue: queue.Queue) -> None:  # type: ignore[type-arg]
        super().__init__()
        self._queue = result_queue
        self.setFormatter(
            logging.Formatter(
                "[%(levelname)-8s] %(asctime)s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tag = self._TAG_MAP.get(record.levelname, "INFO")
            self._queue.put_nowait(("log", tag, self.format(record)))
        except Exception:  # pragma: no cover
            self.handleError(record)


# ── Main application window ───────────────────────────────────────────────────


class MDToPDFApp:
    """Tkinter GUI for mdtopdf."""

    def __init__(self) -> None:
        self._root = tk.Tk()
        self._root.title("mdtopdf — Markdown 转 PDF 工具")
        self._root.resizable(True, True)
        self._root.minsize(750, 620)

        # ── StringVars ──────────────────────────────────────────────────────
        self._input_var = tk.StringVar()
        self._output_var = tk.StringVar()
        self._plantuml_mode_var = tk.StringVar(value="online")
        self._plantuml_jar_var = tk.StringVar()
        self._mermaid_mode_var = tk.StringVar(value="online")
        self._math_mode_var = tk.StringVar(value="online")
        self._math_timeout_var = tk.StringVar(value="10")
        self._math_providers_var = tk.StringVar(value="codecogs_png,vercel_svg,mathnow_svg")
        self._custom_css_var = tk.StringVar()

        # ── BoolVars ─────────────────────────────────────────────────────────
        self._preview_var = tk.BooleanVar(value=False)
        self._open_var = tk.BooleanVar(value=False)
        self._verbose_var = tk.BooleanVar(value=False)
        self._math_bare_latex_var = tk.BooleanVar(value=True)

        # ── Runtime state ─────────────────────────────────────────────────
        self._converting = False
        self._queue: queue.Queue = queue.Queue()  # type: ignore[type-arg]

        self._build_ui()
        self._poll_queue()
        self._input_var.trace_add("write", self._auto_fill_output)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        style = ttk.Style()
        # 'vista' on Windows gives native look; fall back to 'clam'
        for theme in ("vista", "clam"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue

        outer = ttk.Frame(self._root, padding=(12, 10, 12, 4))
        outer.pack(fill=tk.BOTH, expand=True)

        self._build_file_section(outer)
        self._build_options_section(outer)
        self._build_action_row(outer)
        self._build_log_section(outer)

        # Status bar
        self._status_var = tk.StringVar(value="  就绪")
        ttk.Label(
            self._root,
            textvariable=self._status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(6, 2),
        ).pack(side=tk.BOTTOM, fill=tk.X)

    # ── File section ─────────────────────────────────────────────────────────

    def _build_file_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 文件 ", padding=(10, 6))
        frame.pack(fill=tk.X, pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        # Input row
        ttk.Label(frame, text="输入文件 (.md):").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8)
        )
        ttk.Entry(frame, textvariable=self._input_var).grid(
            row=0, column=1, sticky=tk.EW, padx=4
        )
        ttk.Button(frame, text="浏览…", width=7, command=self._browse_input).grid(
            row=0, column=2
        )

        # Output row
        ttk.Label(frame, text="输出文件 (.pdf):").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8), pady=(6, 0)
        )
        ttk.Entry(frame, textvariable=self._output_var).grid(
            row=1, column=1, sticky=tk.EW, padx=4, pady=(6, 0)
        )
        ttk.Button(frame, text="浏览…", width=7, command=self._browse_output).grid(
            row=1, column=2, pady=(6, 0)
        )

    # ── Options section ───────────────────────────────────────────────────────

    def _build_options_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 渲染选项 ", padding=(10, 6))
        frame.pack(fill=tk.X, pady=(0, 8))
        frame.columnconfigure(3, weight=1)

        # Row 0 — PlantUML
        ttk.Label(frame, text="PlantUML:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        ttk.Combobox(
            frame,
            textvariable=self._plantuml_mode_var,
            values=["local", "online"],
            state="readonly",
            width=9,
        ).grid(row=0, column=1, sticky=tk.W, padx=(0, 16))
        ttk.Label(frame, text="JAR 路径:").grid(row=0, column=2, sticky=tk.W, padx=(0, 6))
        ttk.Entry(frame, textvariable=self._plantuml_jar_var).grid(
            row=0, column=3, sticky=tk.EW, padx=4
        )
        ttk.Button(frame, text="浏览…", width=7, command=self._browse_jar).grid(
            row=0, column=4
        )

        # Row 1 — Mermaid
        ttk.Label(frame, text="Mermaid:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 6), pady=(6, 0)
        )
        ttk.Combobox(
            frame,
            textvariable=self._mermaid_mode_var,
            values=["local", "online"],
            state="readonly",
            width=9,
        ).grid(row=1, column=1, sticky=tk.W, padx=(0, 16), pady=(6, 0))

        # Row 2 — Math
        ttk.Label(frame, text="Math:").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 6), pady=(6, 0)
        )
        ttk.Combobox(
            frame,
            textvariable=self._math_mode_var,
            values=["online", "auto", "latex2mathml"],
            state="readonly",
            width=12,
        ).grid(row=2, column=1, sticky=tk.W, padx=(0, 16), pady=(6, 0))
        ttk.Label(frame, text="在线超时(秒):").grid(
            row=2, column=2, sticky=tk.W, padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(frame, textvariable=self._math_timeout_var, width=6).grid(
            row=2, column=3, sticky=tk.W, padx=(6, 0), pady=(6, 0)
        )

        ttk.Label(frame, text="在线节点链:").grid(
            row=3, column=0, sticky=tk.W, padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(frame, textvariable=self._math_providers_var).grid(
            row=3, column=1, columnspan=5, sticky=tk.EW, padx=4, pady=(6, 0)
        )

        # Row 4 — Custom CSS
        ttk.Label(frame, text="自定义 CSS:").grid(
            row=4, column=0, sticky=tk.W, padx=(0, 6), pady=(6, 0)
        )
        ttk.Entry(frame, textvariable=self._custom_css_var).grid(
            row=4, column=1, columnspan=4, sticky=tk.EW, padx=4, pady=(6, 0)
        )
        ttk.Button(frame, text="浏览…", width=7, command=self._browse_css).grid(
            row=4, column=5, pady=(6, 0)
        )

        # Row 5 — Checkboxes
        checks = ttk.Frame(frame)
        checks.grid(row=5, column=0, columnspan=6, sticky=tk.W, pady=(10, 2))
        ttk.Checkbutton(
            checks, text="转换前预览 PDF", variable=self._preview_var
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(
            checks, text="完成后自动打开", variable=self._open_var
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(
            checks, text="详细日志", variable=self._verbose_var
        ).pack(side=tk.LEFT)
        ttk.Checkbutton(
            checks,
            text="启用裸 LaTeX 识别",
            variable=self._math_bare_latex_var,
        ).pack(side=tk.LEFT, padx=(20, 0))

    # ── Action row ────────────────────────────────────────────────────────────

    def _build_action_row(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 6))

        self._convert_btn = ttk.Button(
            frame,
            text="▶  开始转换",
            command=self._start_conversion,
        )
        self._convert_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(frame, text="清除日志", command=self._clear_log).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        self._progress = ttk.Progressbar(frame, mode="indeterminate", length=220)
        self._progress.pack(side=tk.LEFT, padx=(8, 0))

    # ── Log section ───────────────────────────────────────────────────────────

    def _build_log_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" 日志输出 ", padding=(4, 4))
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        self._log_text = scrolledtext.ScrolledText(
            frame,
            state="disabled",
            height=13,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#cccccc",
            insertbackground="white",
            selectbackground="#264f78",
            wrap=tk.NONE,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)

        self._log_text.tag_configure("INFO", foreground="#4ec9b0")
        self._log_text.tag_configure("WARNING", foreground="#ce9178")
        self._log_text.tag_configure("ERROR", foreground="#f44747")
        self._log_text.tag_configure("DEBUG", foreground="#808080")
        self._log_text.tag_configure("SEP", foreground="#555555")

    # ── File browsing ─────────────────────────────────────────────────────────

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Markdown 文件",
            filetypes=[("Markdown 文件", "*.md *.markdown"), ("所有文件", "*.*")],
        )
        if path:
            self._input_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择输出 PDF 路径",
            defaultextension=".pdf",
            filetypes=[("PDF 文件", "*.pdf")],
        )
        if path:
            self._output_var.set(path)

    def _browse_jar(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 PlantUML JAR",
            filetypes=[("JAR 文件", "*.jar"), ("所有文件", "*.*")],
        )
        if path:
            self._plantuml_jar_var.set(path)

    def _browse_css(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 CSS 文件",
            filetypes=[("CSS 文件", "*.css"), ("所有文件", "*.*")],
        )
        if path:
            self._custom_css_var.set(path)

    def _auto_fill_output(self, *_: Any) -> None:
        """Auto-populate the output field when the input path is set."""
        src = self._input_var.get().strip()
        if src and not self._output_var.get().strip():
            self._output_var.set(str(Path(src).with_suffix(".pdf")))

    # ── Conversion ────────────────────────────────────────────────────────────

    def _start_conversion(self) -> None:
        if self._converting:
            return

        input_str = self._input_var.get().strip()
        if not input_str:
            messagebox.showerror("错误", "请先选择输入的 Markdown 文件。")
            return

        input_path = Path(input_str)
        if not input_path.exists():
            messagebox.showerror("错误", f"文件不存在：\n{input_path}")
            return

        output_str = self._output_var.get().strip()
        output_path = Path(output_str) if output_str else input_path.with_suffix(".pdf")

        cli_overrides: dict[str, Any] = {
            "plantuml_mode": self._plantuml_mode_var.get(),
            "mermaid_mode": self._mermaid_mode_var.get(),
            "math_mode": self._math_mode_var.get(),
            "math_enable_bare_latex": self._math_bare_latex_var.get(),
        }
        if self._plantuml_jar_var.get().strip():
            cli_overrides["plantuml_jar_path"] = self._plantuml_jar_var.get().strip()
        if self._custom_css_var.get().strip():
            cli_overrides["custom_css"] = self._custom_css_var.get().strip()
        timeout_text = self._math_timeout_var.get().strip()
        if timeout_text:
            try:
                cli_overrides["math_online_timeout"] = int(timeout_text)
            except ValueError:
                messagebox.showerror("错误", "数学公式超时必须是整数秒。")
                return
        if self._math_providers_var.get().strip():
            cli_overrides["math_online_providers"] = self._math_providers_var.get().strip()

        from ..utils.logger import setup_logger

        setup_logger(self._verbose_var.get())

        self._converting = True
        self._convert_btn.configure(state="disabled")
        self._progress.start(12)
        self._set_status("  ⟳ 正在转换…")
        self._append_log("─" * 52, "SEP")
        self._append_log(f"开始转换：{input_path.name}", "INFO")

        thread = threading.Thread(
            target=self._worker_conversion,
            args=(input_path, output_path, cli_overrides, self._preview_var.get()),
            daemon=True,
        )
        thread.start()

    def _worker_conversion(
        self,
        input_path: Path,
        output_path: Path,
        cli_overrides: dict[str, Any],
        preview: bool,
    ) -> None:
        """Runs on a background thread — must not touch tkinter widgets."""
        gui_handler = GUILogHandler(self._queue)
        mdtopdf_logger = logging.getLogger("mdtopdf")
        mdtopdf_logger.addHandler(gui_handler)

        try:
            from ..config.config_loader import load_config
            from ..core.assembler import HTMLAssembler
            from ..core.parser import MarkdownParser
            from ..core.pdf_generator import PDFGenerator

            raw_markdown = input_path.read_text(encoding="utf-8")
            front_matter = dict(frontmatter.loads(raw_markdown).metadata)
            config = load_config(
                cli_args=cli_overrides,
                front_matter=front_matter,
            )
            parser = MarkdownParser(
                math_mode=config.math.mode,
                enable_bare_latex=config.math.enable_bare_latex,
                online_timeout=config.math.online_timeout,
                online_providers=config.math.online_providers,
            )
            parse_result = parser.parse_string(raw_markdown)
            html = HTMLAssembler(config).assemble(parse_result, base_dir=input_path.parent)
            pdf_bytes = PDFGenerator().generate_bytes(html)

            self._queue.put_nowait(("success", pdf_bytes, output_path, preview))

        except Exception as exc:
            import traceback as _tb

            self._queue.put_nowait(("error", str(exc), _tb.format_exc()))
        finally:
            mdtopdf_logger.removeHandler(gui_handler)

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    _, tag, text = msg
                    self._append_log(text, tag)
                elif kind == "success":
                    _, pdf_bytes, output_path, preview = msg
                    self._on_success(pdf_bytes, output_path, preview)
                elif kind == "error":
                    _, err_msg, tb_text = msg
                    self._on_error(err_msg, tb_text)
        except queue.Empty:
            pass
        self._root.after(100, self._poll_queue)

    # ── Result handlers ───────────────────────────────────────────────────────

    def _on_success(
        self, pdf_bytes: bytes, output_path: Path, preview: bool
    ) -> None:
        self._stop_converting()

        if preview:
            from .preview import show_preview

            def _after_save() -> None:
                self._save_pdf(pdf_bytes, output_path)
                self._append_log(f"✓ 已保存：{output_path}", "INFO")
                self._set_status(f"  ✓ 已保存：{output_path.name}")
                if self._open_var.get():
                    self._open_file(output_path)

            show_preview(
                self._root,
                pdf_bytes,
                output_path=output_path,
                on_save=_after_save,
            )
        else:
            self._save_pdf(pdf_bytes, output_path)
            self._append_log(f"✓ 已生成 PDF：{output_path}", "INFO")
            self._set_status(f"  ✓ {output_path.name}")
            if self._open_var.get():
                self._open_file(output_path)

    def _on_error(self, msg: str, tb_text: str) -> None:
        self._stop_converting()
        self._append_log(f"✗ 错误：{msg}", "ERROR")
        self._set_status("  ✗ 转换失败")
        if self._verbose_var.get():
            self._append_log(tb_text, "ERROR")
        messagebox.showerror(
            "转换失败",
            f"{msg}\n\n勾选「详细日志」可查看完整堆栈信息。",
        )

    def _stop_converting(self) -> None:
        self._converting = False
        self._convert_btn.configure(state="normal")
        self._progress.stop()

    # ── File operations ───────────────────────────────────────────────────────

    @staticmethod
    def _save_pdf(pdf_bytes: bytes, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)

    @staticmethod
    def _open_file(path: Path) -> None:
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
        except Exception:
            pass

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _append_log(self, text: str, level: str = "INFO") -> None:
        self._log_text.configure(state="normal")
        self._log_text.insert(tk.END, text + "\n", level)
        self._log_text.see(tk.END)
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state="disabled")

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────


def launch() -> None:
    """Create and run the GUI application."""
    app = MDToPDFApp()
    app.run()


if __name__ == "__main__":
    launch()

