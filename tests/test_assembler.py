"""Tests for HTMLAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mdtopdf.config.models import AppConfig
from mdtopdf.core.assembler import HTMLAssembler
from mdtopdf.core.parser import MarkdownParser, ParseResult
from mdtopdf.core.renderer.base import Diagram, RenderResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> AppConfig:
    config = AppConfig()
    for k, v in kwargs.items():
        setattr(config, k, v)
    return config


def _fake_success_result(diagram: Diagram) -> RenderResult:
    return RenderResult(
        diagram_id=diagram.id,
        success=True,
        image_data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,  # minimal fake PNG
        image_format="png",
        error_message=None,
    )


def _fake_failure_result(diagram: Diagram, msg: str = "渲染失败") -> RenderResult:
    return RenderResult(
        diagram_id=diagram.id,
        success=False,
        image_data=None,
        image_format="png",
        error_message=msg,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHTMLAssemblerNoDiagrams:
    """Assemble documents without any diagram blocks."""

    def test_produces_valid_html(self):
        parse_result = MarkdownParser().parse_string("# Hello\n\nWorld")
        config = _make_config(title="Test", author="Author")
        assembler = HTMLAssembler(config)
        html = assembler.assemble(parse_result)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "Hello" in html
        assert "World" in html

    def test_title_and_author_in_output(self):
        parse_result = MarkdownParser().parse_string("Some content.")
        config = _make_config(title="我的标题", author="张三")
        html = HTMLAssembler(config).assemble(parse_result)

        assert "我的标题" in html
        assert "张三" in html

    def test_css_inlined(self):
        parse_result = MarkdownParser().parse_string("Content.")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        assert "<style>" in html

    def test_no_external_references(self):
        parse_result = MarkdownParser().parse_string("Content.")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        # Should not have src= pointing to file paths
        assert 'src="file' not in html
        assert "src='file" not in html

    def test_table_preserved(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        parse_result = MarkdownParser().parse_string(md)
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        assert "<table" in html


class TestHTMLAssemblerWithDiagrams:
    """Assemble documents with diagram blocks."""

    def _assemble_with_mock_renderers(
        self, md: str, success: bool = True
    ) -> tuple[str, list[Diagram]]:
        """Parse *md*, mock renderers, return (html, diagrams)."""
        parse_result = MarkdownParser().parse_string(md)
        config = _make_config()
        assembler = HTMLAssembler(config)

        if success:
            side_effect = _fake_success_result
        else:
            side_effect = lambda d: _fake_failure_result(d)

        with patch.object(assembler, "_render_one", side_effect=side_effect):
            html = assembler.assemble(parse_result)

        return html, parse_result.diagrams

    def test_successful_diagram_produces_img_tag(self):
        md = "```plantuml\n@startuml\nA->B\n@enduml\n```"
        html, diagrams = self._assemble_with_mock_renderers(md, success=True)
        assert 'data:image/png;base64,' in html
        assert "<img" in html

    def test_successful_diagram_no_placeholder_div_remains(self):
        md = "```plantuml\n@startuml\nA->B\n@enduml\n```"
        html, diagrams = self._assemble_with_mock_renderers(md, success=True)
        for d in diagrams:
            assert f'data-id="{d.id}"' not in html

    def test_failed_diagram_produces_error_div(self):
        md = "```mermaid\ngraph TD\nA-->B\n```"
        html, _ = self._assemble_with_mock_renderers(md, success=False)
        assert 'class="diagram-error"' in html

    def test_failed_diagram_preserves_original_code(self):
        md = "```mermaid\ngraph TD\n  UniqueNode123-->B\n```"
        html, _ = self._assemble_with_mock_renderers(md, success=False)
        assert "UniqueNode123" in html

    def test_multiple_diagrams_all_replaced(self):
        md = (
            "```plantuml\n@startuml\nA->B\n@enduml\n```\n\n"
            "```mermaid\ngraph LR\nX-->Y\n```"
        )
        html, diagrams = self._assemble_with_mock_renderers(md, success=True)
        assert html.count("data:image/png;base64,") == 2
        for d in diagrams:
            assert f'data-id="{d.id}"' not in html


class TestHTMLAssemblerCSS:
    def test_pygments_css_present(self):
        parse_result = MarkdownParser().parse_string("```python\nx=1\n```")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        # Pygments generates .highlight rules
        assert ".highlight" in html

    def test_custom_css_injected(self, tmp_path):
        css_file = tmp_path / "custom.css"
        css_file.write_text("body { background: red; }", encoding="utf-8")
        config = _make_config()
        config.style.custom_css = str(css_file)
        parse_result = MarkdownParser().parse_string("Content.")
        html = HTMLAssembler(config).assemble(parse_result)
        assert "background: red" in html

    def test_missing_custom_css_does_not_crash(self):
        config = _make_config()
        config.style.custom_css = "/nonexistent/path/custom.css"
        parse_result = MarkdownParser().parse_string("Content.")
        # Should log a warning but not raise
        html = HTMLAssembler(config).assemble(parse_result)
        assert "<!DOCTYPE html>" in html

    def test_code_soft_wrap_css_present(self):
        parse_result = MarkdownParser().parse_string("`very_long_inline_code_token`")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        assert "white-space: pre-wrap" in html
        assert "overflow-wrap: anywhere" in html

    def test_table_layout_css_present(self):
        parse_result = MarkdownParser().parse_string("| A | B |\n|---|---|\n| longlonglong | value |")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        assert "table-layout: fixed" in html

    def test_math_css_present(self):
        parse_result = MarkdownParser().parse_string("$a+b$")
        html = HTMLAssembler(_make_config()).assemble(parse_result)
        assert ".math-inline" in html
        assert ".math-block" in html

