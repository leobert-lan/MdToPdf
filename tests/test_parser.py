"""Tests for MarkdownParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdtopdf.core.parser import MarkdownParser, ParseResult

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(md: str) -> ParseResult:
    return MarkdownParser().parse_string(md)


# ---------------------------------------------------------------------------
# Front Matter extraction
# ---------------------------------------------------------------------------


class TestFrontMatter:
    def test_extracts_title_and_author(self):
        md = "---\ntitle: My Doc\nauthor: Alice\n---\n\n# Hello"
        result = _parse(md)
        assert result.metadata["title"] == "My Doc"
        assert result.metadata["author"] == "Alice"

    def test_empty_front_matter(self):
        result = _parse("# No front matter here")
        assert result.metadata == {}

    def test_front_matter_does_not_appear_in_body(self):
        md = "---\ntitle: Test\n---\n\nBody text."
        result = _parse(md)
        assert "title:" not in result.html_body
        assert "Body text" in result.html_body


# ---------------------------------------------------------------------------
# Diagram interception
# ---------------------------------------------------------------------------


class TestDiagramInterception:
    def test_plantuml_block_intercepted(self):
        md = "```plantuml\n@startuml\nA -> B\n@enduml\n```"
        result = _parse(md)
        assert len(result.diagrams) == 1
        assert result.diagrams[0].type == "plantuml"
        assert "@startuml" in result.diagrams[0].code

    def test_mermaid_block_intercepted(self):
        md = "```mermaid\ngraph TD\n  A --> B\n```"
        result = _parse(md)
        assert len(result.diagrams) == 1
        assert result.diagrams[0].type == "mermaid"
        assert "graph TD" in result.diagrams[0].code

    def test_multiple_diagrams(self):
        md = (
            "```plantuml\n@startuml\nA->B\n@enduml\n```\n\n"
            "```mermaid\ngraph LR\n  X-->Y\n```"
        )
        result = _parse(md)
        assert len(result.diagrams) == 2
        types = {d.type for d in result.diagrams}
        assert types == {"plantuml", "mermaid"}

    def test_placeholder_div_in_html(self):
        md = "```plantuml\n@startuml\nA->B\n@enduml\n```"
        result = _parse(md)
        diagram_id = result.diagrams[0].id
        assert f'data-id="{diagram_id}"' in result.html_body
        assert 'class="diagram-placeholder"' in result.html_body

    def test_diagram_code_not_in_html_body(self):
        md = "```plantuml\n@startuml\nAlice -> Bob\n@enduml\n```"
        result = _parse(md)
        assert "Alice -> Bob" not in result.html_body


# ---------------------------------------------------------------------------
# Standard Markdown elements
# ---------------------------------------------------------------------------


class TestMarkdownElements:
    def test_table_rendered(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = _parse(md)
        assert "<table" in result.html_body
        assert "<th" in result.html_body
        assert "<td" in result.html_body

    def test_code_block_highlighted(self):
        md = "```python\nprint('hello')\n```"
        result = _parse(md)
        assert 'class="highlight"' in result.html_body

    def test_regular_code_block_not_intercepted(self):
        md = "```python\nprint('hello')\n```"
        result = _parse(md)
        assert len(result.diagrams) == 0

    def test_heading_rendered(self):
        result = _parse("# H1\n## H2\n### H3")
        # toc extension adds id attributes, so match the opening tag prefix
        assert "<h1" in result.html_body
        assert "<h2" in result.html_body
        assert "<h3" in result.html_body

    def test_bold_and_italic(self):
        result = _parse("**bold** and *italic*")
        assert "<strong>" in result.html_body
        assert "<em>" in result.html_body


# ---------------------------------------------------------------------------
# Fixture-based smoke tests
# ---------------------------------------------------------------------------


class TestFixtures:
    def test_basic_fixture_parses(self):
        result = MarkdownParser().parse(FIXTURES / "sample_basic.md")
        assert result.metadata.get("title") == "基础示例文档"
        assert len(result.html_body) > 100
        assert len(result.diagrams) == 0

    def test_diagrams_fixture_parses(self):
        result = MarkdownParser().parse(FIXTURES / "sample_with_diagrams.md")
        assert result.metadata.get("title") == "含图表的示例文档"
        # Should find 4 diagram blocks (2 plantuml + 2 mermaid)
        assert len(result.diagrams) == 4
        types = [d.type for d in result.diagrams]
        assert types.count("plantuml") == 2
        assert types.count("mermaid") == 2

