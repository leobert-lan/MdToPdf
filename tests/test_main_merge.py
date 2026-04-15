"""Tests for multi-file merge helpers in CLI pipeline."""

from __future__ import annotations

from pathlib import Path

from mdtopdf.core.parser import ParseResult
from mdtopdf.core.renderer.base import Diagram
from mdtopdf.main import (
    _absolutize_local_image_sources,
    _extract_markdown_links,
    _merge_parse_results,
    _resolve_input_files,
)


class TestTocLinkExtraction:
    def test_extracts_local_markdown_links_in_order(self, tmp_path: Path):
        toc = tmp_path / "toc.md"
        ch1 = tmp_path / "01_intro.md"
        ch2 = tmp_path / "chapters" / "02_body.md"
        ch2.parent.mkdir(parents=True)
        ch1.write_text("# 1", encoding="utf-8")
        ch2.write_text("# 2", encoding="utf-8")
        toc.write_text(
            "\n".join(
                [
                    "# 目录",
                    "- [第一章](01_intro.md)",
                    "- [远程](https://example.com/x.md)",
                    "- [第二章](chapters/02_body.md)",
                ]
            ),
            encoding="utf-8",
        )

        links = _extract_markdown_links(toc)
        assert links == [ch1.resolve(), ch2.resolve()]

    def test_supports_encoded_and_angle_wrapped_paths(self, tmp_path: Path):
        toc = tmp_path / "toc.md"
        chapter_a = tmp_path / "Chapter One.md"
        chapter_b = tmp_path / "docs" / "Chapter Two.md"
        chapter_b.parent.mkdir(parents=True)
        chapter_a.write_text("# A", encoding="utf-8")
        chapter_b.write_text("# B", encoding="utf-8")
        toc.write_text(
            "\n".join(
                [
                    "# TOC",
                    "- [A](Chapter%20One.md)",
                    "- [B](<docs/Chapter Two.md>)",
                ]
            ),
            encoding="utf-8",
        )

        links = _extract_markdown_links(toc)
        assert links == [chapter_a.resolve(), chapter_b.resolve()]


class TestResolveInputFiles:
    def test_directory_mode_collects_all_markdown(self, tmp_path: Path):
        root = tmp_path / "book"
        (root / "a").mkdir(parents=True)
        f1 = root / "01.md"
        f2 = root / "a" / "02.md"
        f1.write_text("# 1", encoding="utf-8")
        f2.write_text("# 2", encoding="utf-8")

        files = _resolve_input_files(root, merge_toc=False)
        assert files == [f1, f2]

    def test_merge_toc_mode_uses_toc_then_links(self, tmp_path: Path):
        toc = tmp_path / "toc.md"
        ch1 = tmp_path / "01.md"
        ch1.write_text("# 1", encoding="utf-8")
        toc.write_text("- [第一章](01.md)", encoding="utf-8")

        files = _resolve_input_files(toc, merge_toc=True)
        assert files == [toc, ch1.resolve()]


class TestMergeParseResults:
    def test_merges_html_metadata_and_diagrams(self):
        d1 = Diagram(id="d1", type="plantuml", code="@startuml")
        d2 = Diagram(id="d2", type="mermaid", code="graph TD")
        r1 = ParseResult(metadata={"title": "Book"}, html_body="<h1>A</h1>", diagrams=[d1])
        r2 = ParseResult(metadata={"title": "Ignored"}, html_body="<h1>B</h1>", diagrams=[d2])

        merged = _merge_parse_results([(Path("a.md"), r1), (Path("b.md"), r2)])

        assert merged.metadata["title"] == "Book"
        assert len(merged.diagrams) == 2
        assert "mdtopdf-merged-chapter" in merged.html_body
        assert "chapter-divider" in merged.html_body

    def test_rebalances_headings_down_when_top_level_is_too_high(self):
        r1 = ParseResult(metadata={}, html_body='<h1 id="a">A</h1><h2>B</h2>', diagrams=[])
        merged = _merge_parse_results([(Path("a.md"), r1)])

        assert '<h3 id="a">A</h3>' in merged.html_body
        assert "<h4>B</h4>" in merged.html_body

    def test_rebalances_headings_up_when_top_level_is_too_low(self):
        r1 = ParseResult(metadata={}, html_body="<h4>A</h4><h6>B</h6>", diagrams=[])
        merged = _merge_parse_results([(Path("b.md"), r1)])

        assert "<h3>A</h3>" in merged.html_body
        assert "<h5>B</h5>" in merged.html_body


class TestAbsolutizeImageSources:
    def test_rewrites_relative_img_src(self, tmp_path: Path):
        images = tmp_path / "assets"
        images.mkdir(parents=True)
        pic = images / "a.png"
        pic.write_bytes(b"fake")

        html = '<p><img alt="x" src="assets/a.png"></p>'
        rewritten = _absolutize_local_image_sources(html, tmp_path)

        assert pic.resolve().as_posix() in rewritten

