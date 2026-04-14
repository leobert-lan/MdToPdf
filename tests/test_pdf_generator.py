"""Tests for PDFGenerator platform-specific runtime handling."""

from __future__ import annotations

from pathlib import Path

from mdtopdf.core.pdf_generator import PDFGenerator


class TestPDFGeneratorRuntimeErrors:
    def test_windows_error_mentions_gtk3(self, monkeypatch):
        monkeypatch.setattr("mdtopdf.core.pdf_generator.sys.platform", "win32")

        err = PDFGenerator._build_runtime_error(OSError("libgobject-2.0-0.dll missing"))

        assert "GTK3" in str(err)
        assert "Windows" in str(err)

    def test_macos_error_mentions_homebrew_dependencies(self, monkeypatch):
        monkeypatch.setattr("mdtopdf.core.pdf_generator.sys.platform", "darwin")

        err = PDFGenerator._build_runtime_error(OSError("dlopen(libpango-1.0.dylib) failed"))

        text = str(err)
        assert "macOS" in text
        assert "brew install cairo pango gdk-pixbuf libffi" in text
        assert "libpango-1.0.dylib" in text


class TestPDFGeneratorMacOSPreload:
    def test_preload_scans_candidate_dirs_and_loads_matching_dylibs(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("mdtopdf.core.pdf_generator.sys.platform", "darwin")
        lib_a = tmp_path / "libffi.8.dylib"
        lib_b = tmp_path / "libgobject-2.0.0.dylib"
        lib_a.write_bytes(b"")
        lib_b.write_bytes(b"")

        loaded: list[str] = []

        def fake_cdll(path: str, mode: int = 0):
            loaded.append(path)
            return object()

        monkeypatch.setattr(PDFGenerator, "_MACOS_LIBRARY_PATTERNS", ("libffi*.dylib", "libgobject-2.0*.dylib"))
        monkeypatch.setattr(PDFGenerator, "_candidate_library_dirs", staticmethod(lambda: [tmp_path]))
        monkeypatch.setattr("ctypes.CDLL", fake_cdll)

        assert PDFGenerator._attempt_preload_macos_runtime_libraries() is True
        assert loaded == [str(lib_a.resolve()), str(lib_b.resolve())]

    def test_preload_returns_false_outside_macos(self, monkeypatch):
        monkeypatch.setattr("mdtopdf.core.pdf_generator.sys.platform", "linux")
        assert PDFGenerator._attempt_preload_macos_runtime_libraries() is False

