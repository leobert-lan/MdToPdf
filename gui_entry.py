"""Entry point script for PyInstaller EXE packaging.

Usage:
    python gui_entry.py          # run GUI directly
    pyinstaller build_exe.py     # (handled by build_exe.py)
"""
from mdtopdf.gui.app import launch

if __name__ == "__main__":
    launch()

