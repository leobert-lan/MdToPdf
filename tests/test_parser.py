"""Tests for MarkdownParser."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote_plus

import pytest

import mdtopdf.core.parser as parser_module
from mdtopdf.core.parser import HAS_LATEX2MATHML, MarkdownParser, ParseResult

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



class TestMathRendering:
    def test_inline_dollar_math(self):
        result = _parse("质能方程是 $E=mc^2$。")
        if HAS_LATEX2MATHML:
            assert "math-inline" in result.html_body
            assert "<math" in result.html_body or "math-img-inline" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_inline_parenthesis_math(self):
        result = _parse("欧拉恒等式：\\(e^{i\\pi}+1=0\\)")
        if HAS_LATEX2MATHML:
            assert "math-inline" in result.html_body
            assert "<math" in result.html_body or "math-img-inline" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_block_math(self):
        result = _parse("$$\\int_0^1 x^2 dx = \\frac{1}{3}$$")
        if HAS_LATEX2MATHML:
            assert "math-block" in result.html_body
            assert "<math" in result.html_body or "math-img-block" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_bare_latex_commands_are_supported(self):
        result = _parse("数字频率记为 \\omega，范围包含 \\pi，求和符号是 \\sum_{n=0}^N。")
        if HAS_LATEX2MATHML:
            assert result.html_body.count("math-inline") >= 3
            assert "<math" in result.html_body or "math-img-inline" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_bare_expression_with_operators_grouped(self):
        result = _parse("频率关系为 \\omega = \\Omega T = 2\\pi f/f_s。")
        if HAS_LATEX2MATHML:
            assert "math-inline" in result.html_body
            assert "<math" in result.html_body or "math-img-inline" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_disable_bare_latex_keeps_plain_text(self):
        parser = MarkdownParser(enable_bare_latex=False)
        result = parser.parse_string("数字频率 \\omega 与 \\pi。")
        assert "math-inline" not in result.html_body


class TestMathStrategySwitch:
    def test_formula_not_rendered_twice_across_postprocess_passes(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        calls = {"n": 0}

        def fake_get(*args, **kwargs):
            calls["n"] += 1
            return SimpleNamespace(status_code=200, content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(math_mode="online", online_providers=["vercel_svg"])
        parser.parse_string("$x$")
        assert calls["n"] == 1

    def test_dtft_formulas_extract_and_build_online_urls(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        captured_urls: list[str] = []

        def fake_get(url, **kwargs):
            captured_urls.append(url)
            return SimpleNamespace(
                status_code=200,
                content=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            )

        monkeypatch.setattr(parser_module.requests, "get", fake_get)

        md = (
            "对于一个绝对可和的离散时间序列 x[n]，其离散时间傅里叶变换定义为：\n"
            "\\[\n"
            "X(e^{j\\omega}) = \\sum_{n=-\\infty}^{\\infty} x[n] e^{-j\\omega n}\n"
            "\\]\n"
            "其中：\\( e^{-j\\omega n} = \\cos(\\omega n) - j\\sin(\\omega n) \\)\n"
            "结果 \\( X(e^{j\\omega}) \\) 是一个复数函数。\n"
        )

        parser = MarkdownParser(
            math_mode="online",
            online_providers=["codecogs_png"],
            enable_bare_latex=False,
        )
        parser.parse_string(md)

        assert len(captured_urls) >= 3
        assert all(url.startswith("https://latex.codecogs.com/png.image?") for url in captured_urls)

        unique_urls = set(captured_urls)

        expected_block_expr = (
            "X(e^{j\\omega}) = \\sum_{n=-\\infty}^{\\infty} x[n] e^{-j\\omega n}"
        )
        expected_inline_expr = "e^{-j\\omega n} = \\cos(\\omega n) - j\\sin(\\omega n)"

        decoded_queries = [unquote_plus(url.split("?", 1)[1]) for url in unique_urls if "?" in url]
        assert any(expected_block_expr in q for q in decoded_queries)
        assert any(expected_inline_expr in q for q in decoded_queries)
        assert any("X(e^{j\\omega})" in q for q in decoded_queries)

    def test_online_mode_renders_base64_image(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        def fake_get(*args, **kwargs):
            return SimpleNamespace(status_code=200, content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(math_mode="online", online_providers=["vercel_svg"])
        result = parser.parse_string("$x^2$")
        assert "data:image/svg+xml;base64," in result.html_body
        assert "math-img-inline" in result.html_body

    def test_online_mode_falls_back_to_next_provider(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        state = {"n": 0}

        def fake_get(url, **kwargs):
            state["n"] += 1
            if state["n"] == 1:
                return SimpleNamespace(status_code=500, content=b"")
            return SimpleNamespace(status_code=200, content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(
            math_mode="online",
            online_providers=["codecogs_png", "vercel_svg"],
        )
        result = parser.parse_string("$x$")
        assert state["n"] >= 2
        assert "math-img-inline" in result.html_body

    def test_auto_mode_falls_back_to_latex2mathml_when_online_fails(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        def fake_get(*args, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(math_mode="auto", online_providers=["vercel_svg"])
        result = parser.parse_string("$x^2$")
        if HAS_LATEX2MATHML:
            assert "math-inline" in result.html_body
        else:
            assert "math-fallback" in result.html_body

    def test_online_timeout_uses_configured_value(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        observed: dict[str, int] = {}

        def fake_get(*args, **kwargs):
            observed["timeout"] = kwargs.get("timeout")
            return SimpleNamespace(status_code=200, content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(math_mode="online", online_timeout=3, online_providers=["vercel_svg"])
        parser.parse_string("$x$")
        assert observed["timeout"] == 3

    def test_parallel_online_rendering_for_multiple_formulas(self, monkeypatch: pytest.MonkeyPatch):
        parser_module.MathRenderer._GLOBAL_CACHE.clear()
        import threading
        import time

        thread_ids: set[int] = set()

        def fake_get(*args, **kwargs):
            thread_ids.add(threading.get_ident())
            time.sleep(0.03)
            return SimpleNamespace(status_code=200, content=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

        monkeypatch.setattr(parser_module.requests, "get", fake_get)
        parser = MarkdownParser(math_mode="online", online_providers=["vercel_svg"])
        parser.parse_string("$a$ $b$ $c$ $d$ $e$ $f$")
        assert len(thread_ids) >= 2


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

