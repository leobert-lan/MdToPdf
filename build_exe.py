"""
build_exe.py — 将 mdtopdf GUI 打包为 Windows 单文件 EXE
===========================================================

用法：
    python build_exe.py               # 默认打包 GUI（--onefile --windowed）
    python build_exe.py --onedir      # 打包为文件夹（启动更快，便于调试）
    python build_exe.py --with-cli    # 同时打包 CLI 版本（带控制台窗口）
    python build_exe.py --gtk3-bin "C:\\GTK3\\bin"  # 手动指定 GTK3 bin 目录

前提条件
--------
1. 已激活虚拟环境：  .venv\\Scripts\\activate
2. 已安装 GTK3 运行时（WeasyPrint 必须）：
   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
3. GTK3 bin 目录已加入系统 PATH，或通过 --gtk3-bin 参数指定

输出
----
  dist/mdtopdf-gui.exe   （或 dist/mdtopdf-gui/ 目录）
  dist/mdtopdf.exe       （仅 --with-cli 时生成）
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── 常量 ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

# 应用图标（可替换为实际 .ico 文件路径，不存在则忽略）
ICON_PATH = ROOT / "mdtopdf.ico"

# 内置资源文件（必须随 EXE 一起打包）
DATA_FILES: list[tuple[str, str]] = [
    (str(ROOT / "mdtopdf" / "assets"), "mdtopdf/assets"),
    (str(ROOT / "mdtopdf" / "config" / "default_config.yaml"), "mdtopdf/config"),
]

# 必须显式声明的 hidden imports（避免 PyInstaller 遗漏）
HIDDEN_IMPORTS: list[str] = [
    "mdtopdf",
    "mdtopdf.gui",
    "mdtopdf.gui.app",
    "mdtopdf.gui.preview",
    "mdtopdf.core",
    "mdtopdf.core.parser",
    "mdtopdf.core.assembler",
    "mdtopdf.core.pdf_generator",
    "mdtopdf.core.previewer",
    "mdtopdf.core.renderer",
    "mdtopdf.core.renderer.base",
    "mdtopdf.core.renderer.plantuml_renderer",
    "mdtopdf.core.renderer.mermaid_renderer",
    "mdtopdf.config",
    "mdtopdf.config.config_loader",
    "mdtopdf.config.models",
    "mdtopdf.utils",
    "mdtopdf.utils.logger",
    "mdtopdf.utils.temp_manager",
    "mdtopdf.utils.file_utils",
    # WeasyPrint internals
    "weasyprint",
    "weasyprint.css",
    "weasyprint.document",
    "weasyprint.drawing",
    "weasyprint.fonts",
    "weasyprint.html",
    "weasyprint.images",
    "weasyprint.layout",
    "weasyprint.stacking",
    "weasyprint.text",
    "weasyprint.text.ffi",
    "weasyprint.text.fonts",
    "weasyprint.text.line_break",
    # PDF / image / templating
    "fitz",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "PIL._imaging",
    "pygments",
    "pygments.formatters",
    "pygments.formatters.html",
    "pygments.lexers",
    "pygments.lexers._mapping",
    "pygments.styles",
    "jinja2",
    "jinja2.ext",
    "yaml",
    "frontmatter",
    # WeasyPrint C-level dependencies
    "cffi",
    "pydyf",
    "tinycss2",
    "tinyhtml5",
    "cssselect2",
    "pyphen",
    "fonttools",
    "zopfli",
    "brotli",
]

# collect-all packages（让 PyInstaller 递归收集整个包）
COLLECT_ALL: list[str] = [
    "weasyprint",
    "pygments",
    "fitz",
]


# ── GTK3 检测 ─────────────────────────────────────────────────────────────────


def find_gtk3_bin(hint: str | None = None) -> Path | None:
    """寻找 GTK3 bin 目录（包含 libgobject-2.0-0.dll 的目录）。"""
    candidates: list[Path] = []

    if hint:
        candidates.append(Path(hint))

    # 从 PATH 中查找
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if p:
            candidates.append(Path(p))

    # Windows 常见安装位置
    candidates += [
        Path(r"C:\Program Files\GTK3-Runtime Win64\bin"),
        Path(r"C:\Program Files (x86)\GTK3-Runtime Win32\bin"),
        Path(r"C:\msys64\mingw64\bin"),
        Path(r"C:\msys64\ucrt64\bin"),
        Path(r"C:\gtk\bin"),
    ]

    for cand in candidates:
        if cand.is_dir() and (cand / "libgobject-2.0-0.dll").exists():
            return cand

    return None


# ── PyInstaller 参数构建 ──────────────────────────────────────────────────────


def build_args(
    entry_point: Path,
    exe_name: str,
    windowed: bool,
    onefile: bool,
    gtk3_bin: Path | None,
) -> list[str]:
    sep = os.pathsep  # ';' on Windows, ':' on POSIX

    args = [
        sys.executable, "-m", "PyInstaller",
        str(entry_point),
        "--name", exe_name,
        "--clean",
        "--noconfirm",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
    ]

    # Windowed / console
    if windowed:
        args.append("--windowed")
    else:
        args.append("--console")

    # One-file vs one-dir
    if onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    # Optional icon
    if ICON_PATH.exists():
        args += ["--icon", str(ICON_PATH)]

    # Data files
    for src, dst in DATA_FILES:
        args += ["--add-data", f"{src}{sep}{dst}"]

    # Hidden imports
    for hi in HIDDEN_IMPORTS:
        args += ["--hidden-import", hi]

    # collect-all
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]

    # GTK3 DLLs — bundle only key WeasyPrint DLLs (keeps EXE smaller)
    if gtk3_bin:
        print(f"  ✓ 找到 GTK3: {gtk3_bin}")
        key_dlls = [
            "libgobject-2.0-0.dll",
            "libglib-2.0-0.dll",
            "libgio-2.0-0.dll",
            "libgmodule-2.0-0.dll",
            "libpango-1.0-0.dll",
            "libpangocairo-1.0-0.dll",
            "libpangoft2-1.0-0.dll",
            "libpangowin32-1.0-0.dll",
            "libcairo-2.dll",
            "libcairo-gobject-2.dll",
            "libharfbuzz-0.dll",
            "libfreetype-6.dll",
            "libfontconfig-1.dll",
            "libpixman-1-0.dll",
            "libpng16-16.dll",
            "zlib1.dll",
            "libffi-8.dll",
            "libintl-8.dll",
            "libwinpthread-1.dll",
            "libgcc_s_seh-1.dll",
            "libstdc++-6.dll",
        ]
        bundled = 0
        for dll_name in key_dlls:
            dll_path = gtk3_bin / dll_name
            if dll_path.exists():
                args += ["--add-binary", f"{dll_path}{sep}."]
                bundled += 1
        print(f"  ✓ 已添加 {bundled}/{len(key_dlls)} 个 GTK3 DLL")
    else:
        print("  ⚠ 未找到 GTK3 DLL 目录")
        print("    EXE 将依赖系统已安装的 GTK3（推荐做法）。")
        print("    若目标机器未安装 GTK3，请使用 --gtk3-bin 指定目录后重新打包。")

    return args


# ── 主流程 ────────────────────────────────────────────────────────────────────


def ensure_pyinstaller() -> None:
    """如果 PyInstaller 未安装，自动安装。"""
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller 未安装，正在安装…")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="将 mdtopdf GUI 打包为 Windows EXE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        default=False,
        help="打包为文件夹（默认：单文件 --onefile）",
    )
    parser.add_argument(
        "--with-cli",
        action="store_true",
        default=False,
        help="同时打包 CLI 版本（mdtopdf.exe，带控制台窗口）",
    )
    parser.add_argument(
        "--gtk3-bin",
        metavar="DIR",
        default=None,
        help="GTK3 bin 目录路径（含 libgobject-2.0-0.dll）",
    )
    args = parser.parse_args()

    onefile = not args.onedir
    gtk3_bin = find_gtk3_bin(args.gtk3_bin)

    print("=" * 60)
    print("  mdtopdf EXE 打包工具")
    print("=" * 60)
    print(f"  模式   : {'单文件 (--onefile)' if onefile else '文件夹 (--onedir)'}")
    print(f"  GTK3   : {gtk3_bin or '(依赖系统 PATH)'}")
    print(f"  输出   : {DIST_DIR}")
    print()

    # 1. 确保 PyInstaller 可用
    ensure_pyinstaller()

    # 2. 打包 GUI（无控制台窗口）
    print("▶ 打包 GUI（mdtopdf-gui.exe）…")
    gui_args = build_args(
        entry_point=ROOT / "gui_entry.py",
        exe_name="mdtopdf-gui",
        windowed=True,
        onefile=onefile,
        gtk3_bin=gtk3_bin,
    )
    subprocess.run(gui_args, check=True, cwd=ROOT)

    # 3. （可选）打包 CLI
    if args.with_cli:
        print()
        print("▶ 打包 CLI（mdtopdf.exe）…")
        # CLI entry point: use the installed console script wrapper
        cli_entry = ROOT / "cli_entry.py"
        cli_entry.write_text(
            "from mdtopdf.main import cli\nif __name__ == '__main__': cli()\n",
            encoding="utf-8",
        )
        cli_args = build_args(
            entry_point=cli_entry,
            exe_name="mdtopdf",
            windowed=False,
            onefile=onefile,
            gtk3_bin=gtk3_bin,
        )
        subprocess.run(cli_args, check=True, cwd=ROOT)
        cli_entry.unlink(missing_ok=True)

    # 4. 结果
    print()
    print("=" * 60)
    if onefile:
        gui_exe = DIST_DIR / "mdtopdf-gui.exe"
        size_mb = gui_exe.stat().st_size / 1024 / 1024 if gui_exe.exists() else 0
        print(f"  ✓ GUI EXE : {gui_exe}  ({size_mb:.1f} MB)")
        if args.with_cli:
            cli_exe = DIST_DIR / "mdtopdf.exe"
            print(f"  ✓ CLI EXE : {cli_exe}")
    else:
        print(f"  ✓ 输出目录: {DIST_DIR}")
    print()
    print("  注意：目标机器必须安装 GTK3 运行时，否则无法生成 PDF。")
    print("  GTK3 下载: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases")
    print("=" * 60)


if __name__ == "__main__":
    main()

