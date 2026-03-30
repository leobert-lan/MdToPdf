"""Tests for local image inlining in HTMLAssembler."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdtopdf.core.assembler import HTMLAssembler
from mdtopdf.config.models import AppConfig
from mdtopdf.core.parser import MarkdownParser


def _make_config() -> AppConfig:
    return AppConfig()


class TestImageInlining:
    """Unit-test _inline_local_images via assemble() with base_dir."""

    def test_png_image_is_inlined(self, tmp_path: Path) -> None:
        # Create a minimal valid PNG (8x8 white, ~70 bytes)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
            b"\x08\x02\x00\x00\x00Km)\x87\x00\x00\x00\x1eIDATx\x9cc\xf8\x0f\x00"
            b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        img_file = tmp_path / "photo.png"
        img_file.write_bytes(png_bytes)

        md = f"# Test\n\n![photo](photo.png)\n"
        pr = MarkdownParser().parse_string(md)
        # Temporarily set html_body to contain the img
        pr.html_body = f'<img alt="photo" src="photo.png">'

        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert "data:image/png;base64," in html
        assert "photo.png" not in html  # original path replaced

    def test_http_image_is_not_inlined(self, tmp_path: Path) -> None:
        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="https://example.com/img.png">'
        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert "https://example.com/img.png" in html
        assert "data:image" not in html

    def test_data_uri_not_double_inlined(self, tmp_path: Path) -> None:
        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="data:image/png;base64,abc123">'
        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert html.count("data:image/png;base64,abc123") == 1

    def test_missing_image_logs_warning_and_keeps_src(
        self, tmp_path: Path, caplog
    ) -> None:
        import logging

        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="nonexistent.png">'
        with caplog.at_level(logging.WARNING):
            html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert "nonexistent.png" in html  # original kept
        assert any("不存在" in r.message or "nonexistent" in r.message
                   for r in caplog.records)

    def test_no_base_dir_leaves_src_unchanged(self) -> None:
        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="./local.png">'
        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=None)
        assert "./local.png" in html

    def test_svg_mime_type(self, tmp_path: Path) -> None:
        svg_file = tmp_path / "diagram.svg"
        svg_file.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>',
            encoding="utf-8",
        )
        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="diagram.svg">'
        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert "data:image/svg+xml;base64," in html

    def test_subdirectory_relative_path(self, tmp_path: Path) -> None:
        subdir = tmp_path / "images"
        subdir.mkdir()
        img = subdir / "logo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 30)

        pr = MarkdownParser().parse_string("content")
        pr.html_body = '<img src="images/logo.png">'
        html = HTMLAssembler(_make_config()).assemble(pr, base_dir=tmp_path)
        assert "data:image/png;base64," in html

