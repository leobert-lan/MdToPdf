"""Markdown parser — extracts Front Matter + converts Markdown to HTML.

Key responsibilities
--------------------
1. Use ``python-frontmatter`` to separate YAML Front Matter from body.
2. Register ``DiagramExtension`` — a custom Python-Markdown extension that
   intercepts ``plantuml`` and ``mermaid`` fenced code blocks *before* the
   standard ``fenced_code`` extension sees them.
3. Replace intercepted blocks with ``<div class="diagram-placeholder"
   data-id="<uuid>">`` tags and collect ``Diagram`` objects.
4. All other fenced blocks go through Pygments via ``codehilite``.
5. Return a ``ParseResult`` containing metadata, HTML body, and diagrams.
"""

from __future__ import annotations

import logging
import base64
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import frontmatter
import markdown
import requests
from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor

from ..core.renderer.base import Diagram

try:
    from latex2mathml.converter import convert as _latex_to_mathml
except ImportError:  # pragma: no cover - optional dependency guard
    _latex_to_mathml = None

logger = logging.getLogger("mdtopdf.parser")
HAS_LATEX2MATHML = _latex_to_mathml is not None

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ParseResult:
    metadata: dict[str, Any]
    html_body: str
    diagrams: list[Diagram] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DiagramExtension for Python-Markdown
# ---------------------------------------------------------------------------

# Matches fenced code blocks whose language is plantuml or mermaid.
# Supports both ``` and ~~~ fences of any depth >= 3.
_FENCED_DIAGRAM_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>plantuml|mermaid)"
    r"(?:[ \t]+\S+)?[ \t]*\n"   # optional extra info string
    r"(?P<code>.*?)\n"
    r"^(?P=fence)[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

_MARKER_PREFIX = "MDTOPDF_DIAGRAM"
_MATH_MARKER_PREFIX = "MDTOPDF_MATH"

_BLOCK_DOLLAR_MATH_RE = re.compile(
    r"(?<!\\)\$\$(?P<expr>.+?)(?<!\\)\$\$",
    re.DOTALL,
)
_BLOCK_BRACKET_MATH_RE = re.compile(
    r"\\\[(?P<expr>.+?)\\\]",
    re.DOTALL,
)
_INLINE_PAREN_MATH_RE = re.compile(r"\\\((?P<expr>.+?)\\\)")
_INLINE_DOLLAR_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)(?P<expr>.+?)(?<!\\)\$")
_INLINE_BARE_EXPR_RE = re.compile(
    r"(?P<expr>(?:\\[A-Za-z]+|[A-Za-z0-9\{\}\[\]\(\)_\^\+\-\*/=<>,\.])"
    r"(?:[ \t]+(?:\\[A-Za-z]+|[A-Za-z0-9\{\}\[\]\(\)_\^\+\-\*/=<>,\.]))+)",
)
_INLINE_BARE_LATEX_RE = re.compile(
    r"(?<![\\$])(?P<expr>\\(?:"
    r"alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|vartheta|"
    r"iota|kappa|lambda|mu|nu|xi|pi|varpi|rho|varrho|sigma|varsigma|tau|"
    r"upsilon|phi|varphi|chi|psi|omega|"
    r"Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega|"
    r"sum|prod|int|oint|infty|cdot|times|leq|geq|neq|approx|angle|"
    r"sin|cos|tan|log|ln"
    r")(?=[^A-Za-z]|$)(?:\s*(?:_\{[^{}\n]+\}|\^\{[^{}\n]+\}|_[A-Za-z0-9]+|\^[A-Za-z0-9]+)){0,2})"
)


@dataclass
class MathFragment:
    expr: str
    source: str
    block: bool


def _store_bare_expression(expr: str, store_fn: Any) -> str:
    """Convert bare LaTeX-heavy inline expressions into a math marker.

    This targets undelimited expressions like ``\\omega = \\Omega T = 2\\pi f/f_s``.
    """
    stripped = expr.strip()
    if not stripped:
        return expr
    if _MATH_MARKER_PREFIX in stripped or _MARKER_PREFIX in stripped:
        return expr

    # Require both a LaTeX command and a math operator to reduce false positives.
    if "\\" not in stripped:
        return expr
    if not any(op in stripped for op in ("=", "+", "-", "/", "^", "_", "<", ">")):
        return expr

    return store_fn(expr=stripped, source=stripped, block=False)


class MathRenderer:
    """Render math by strategy with graceful fallback across available engines."""

    def __init__(
        self,
        mode: str = "auto",
        online_timeout: int = 10,
        online_providers: list[str] | None = None,
    ) -> None:
        normalized = (mode or "auto").strip().lower()
        self.mode = normalized if normalized in {"auto", "online", "latex2mathml"} else "online"
        self.online_timeout = max(1, int(online_timeout))
        self.online_providers = online_providers or ["codecogs_png", "vercel_svg", "mathnow_svg"]

    def render(self, fragment: MathFragment) -> str:
        ordered = self._ordered_engines()
        for engine in ordered:
            if engine == "online":
                rendered = self._render_by_online(fragment)
            else:
                rendered = self._render_by_latex2mathml(fragment)
            if rendered:
                return rendered

        fallback = escape(fragment.source)
        if fragment.block:
            return f'<pre class="math-fallback">{fallback}</pre>'
        return f'<code class="math-fallback">{fallback}</code>'

    def _ordered_engines(self) -> list[str]:
        if self.mode == "online":
            return ["online"]
        if self.mode == "latex2mathml":
            return ["latex2mathml", "online"]
        return ["online", "latex2mathml"]

    def _render_by_latex2mathml(self, fragment: MathFragment) -> str | None:
        if not HAS_LATEX2MATHML or _latex_to_mathml is None:
            return None
        try:
            mathml = _latex_to_mathml(fragment.expr)
            if fragment.block:
                return f'<div class="math-block">{mathml}</div>'
            return f'<span class="math-inline">{mathml}</span>'
        except Exception as exc:
            logger.warning("latex2mathml 公式渲染失败，尝试其他策略: %s", exc)
            return None

    def _render_by_online(self, fragment: MathFragment) -> str | None:
        for provider in self.online_providers:
            rendered = self._render_by_online_provider(provider, fragment)
            if rendered:
                return rendered
        logger.warning("在线公式渲染链全部失败，已回退其他策略")
        return None

    def _render_by_online_provider(self, provider: str, fragment: MathFragment) -> str | None:
        encoded = quote_plus(fragment.expr)
        provider_name = provider.strip().lower()
        if provider_name == "codecogs_png":
            # CodeCogs accepts raw LaTeX query; avoid '+' introduced by quote_plus.
            url = f"https://latex.codecogs.com/png.image?{fragment.expr}"
            mime = "image/png"
        elif provider_name == "codecogs_svg":
            url = f"https://latex.codecogs.com/svg.image?{fragment.expr}"
            mime = "image/svg+xml"
        elif provider_name == "mathnow_svg":
            url = f"https://math.now.sh?from={encoded}"
            mime = "image/svg+xml"
        elif provider_name == "vercel_svg":
            url = f"https://math.vercel.app/?from={encoded}"
            mime = "image/svg+xml"
        else:
            return None

        try:
            resp = requests.get(
                url,
                timeout=self.online_timeout,
                headers={"User-Agent": "mdtopdf/0.1"},
            )
        except Exception as exc:
            logger.warning("在线公式节点 %s 调用失败: %s", provider_name, exc)
            return None

        if resp.status_code != 200 or not resp.content:
            logger.warning("在线公式节点 %s 返回异常状态: %s", provider_name, resp.status_code)
            return None

        content = resp.content
        if mime == "image/svg+xml" and b"<svg" not in content:
            logger.warning("在线公式节点 %s 未返回有效 SVG", provider_name)
            return None

        b64 = base64.b64encode(content).decode("ascii")
        src = f"data:{mime};base64,{b64}"
        cls = "math-img math-img-block" if fragment.block else "math-img math-img-inline"
        if fragment.block:
            return f'<div class="math-block"><img class="{cls}" src="{src}" alt="math formula"></div>'
        return f'<span class="math-inline"><img class="{cls}" src="{src}" alt="math formula"></span>'



class DiagramPreprocessor(Preprocessor):
    """Intercepts plantuml/mermaid fenced blocks before fenced_code runs.

    Runs at priority 175 — higher than FencedBlockPreprocessor (25) so our
    blocks are removed from the source before fenced_code can touch them.
    """

    def run(self, lines: list[str]) -> list[str]:
        text = "\n".join(lines)
        diagrams: dict[str, Diagram] = {}

        def _replace(m: re.Match) -> str:
            lang = m.group("lang").lower()
            code = m.group("code")
            diagram_id = str(uuid.uuid4()).replace("-", "")
            diagrams[diagram_id] = Diagram(id=diagram_id, type=lang, code=code)
            # Return a uniquely identifiable marker on its own line.
            # Surrounding blank lines ensure Markdown wraps it in a <p> tag.
            return f"\n\n{_MARKER_PREFIX}_{diagram_id}\n\n"

        text = _FENCED_DIAGRAM_RE.sub(_replace, text)

        # Store on the Markdown instance so the postprocessor can access it.
        if not hasattr(self.md, "diagram_map"):
            self.md.diagram_map = {}
        self.md.diagram_map.update(diagrams)

        return text.split("\n")


class DiagramPostprocessor(Postprocessor):
    """Replaces paragraph-wrapped markers with proper placeholder <div> tags."""

    def run(self, text: str) -> str:
        diagram_map: dict[str, Diagram] = getattr(self.md, "diagram_map", {})
        for diagram_id, diagram in diagram_map.items():
            marker = f"{_MARKER_PREFIX}_{diagram_id}"
            placeholder = (
                f'<div class="diagram-placeholder" data-id="{diagram_id}"></div>'
            )
            # The marker may have been wrapped in <p>...</p> by the paragraph
            # processor.  Handle optional whitespace inside the tags.
            text = re.sub(
                rf"<p>\s*{re.escape(marker)}\s*</p>",
                placeholder,
                text,
            )
            # Fallback: bare marker (shouldn't happen but be defensive)
            text = text.replace(marker, placeholder)
        return text


class MathPreprocessor(Preprocessor):
    """Intercepts inline/block LaTeX fragments and replaces them with markers."""

    def run(self, lines: list[str]) -> list[str]:
        text = "\n".join(lines)
        math_map: dict[str, MathFragment] = getattr(self.md, "math_map", {})
        enable_bare_latex = bool(getattr(self.md, "enable_bare_latex", True))

        def _store(expr: str, source: str, block: bool) -> str:
            math_id = str(uuid.uuid4()).replace("-", "")
            math_map[math_id] = MathFragment(
                expr=expr.strip(),
                source=source,
                block=block,
            )
            marker = f"{_MATH_MARKER_PREFIX}_{math_id}"
            return f"\n\n{marker}\n\n" if block else marker

        text = _BLOCK_DOLLAR_MATH_RE.sub(
            lambda m: _store(
                expr=m.group("expr"),
                source=f"$${m.group('expr')}$$",
                block=True,
            ),
            text,
        )
        text = _BLOCK_BRACKET_MATH_RE.sub(
            lambda m: _store(
                expr=m.group("expr"),
                source=f"\\[{m.group('expr')}\\]",
                block=True,
            ),
            text,
        )
        text = _INLINE_PAREN_MATH_RE.sub(
            lambda m: _store(
                expr=m.group("expr"),
                source=f"\\({m.group('expr')}\\)",
                block=False,
            ),
            text,
        )
        text = _INLINE_DOLLAR_MATH_RE.sub(
            lambda m: _store(
                expr=m.group("expr"),
                source=f"${m.group('expr')}$",
                block=False,
            ),
            text,
        )

        if enable_bare_latex:
            text = _INLINE_BARE_EXPR_RE.sub(
                lambda m: _store_bare_expression(m.group("expr"), _store),
                text,
            )
            text = _INLINE_BARE_LATEX_RE.sub(
                lambda m: _store(
                    expr=m.group("expr"),
                    source=m.group("expr"),
                    block=False,
                ),
                text,
            )

        self.md.math_map = math_map
        return text.split("\n")


class MathPostprocessor(Postprocessor):
    """Renders math markers to MathML HTML blocks/spans."""

    def run(self, text: str) -> str:
        math_map: dict[str, MathFragment] = getattr(self.md, "math_map", {})
        if not math_map:
            return text

        rendered_map: dict[str, str] = {}
        max_workers = min(8, len(math_map))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {
                executor.submit(self._render, fragment): math_id
                for math_id, fragment in math_map.items()
            }
            for future in as_completed(future_to_id):
                math_id = future_to_id[future]
                fragment = math_map[math_id]
                try:
                    rendered_map[math_id] = future.result()
                except Exception as exc:
                    logger.warning("并行渲染公式失败，已降级为原文: %s", exc)
                    fallback = escape(fragment.source)
                    rendered_map[math_id] = (
                        f'<pre class="math-fallback">{fallback}</pre>'
                        if fragment.block
                        else f'<code class="math-fallback">{fallback}</code>'
                    )

        for math_id, fragment in math_map.items():
            marker = f"{_MATH_MARKER_PREFIX}_{math_id}"
            rendered = rendered_map.get(math_id, self._render(fragment))
            if fragment.block:
                text = re.sub(
                    rf"<p>\s*{re.escape(marker)}\s*</p>",
                    lambda _: rendered,
                    text,
                )
            text = text.replace(marker, rendered)
        return text

    def _render(self, fragment: MathFragment) -> str:
        renderer: MathRenderer | None = getattr(self.md, "math_renderer", None)
        if renderer is None:
            renderer = MathRenderer(
                mode="online",
                online_timeout=10,
                online_providers=["codecogs_png", "vercel_svg", "mathnow_svg"],
            )
        return renderer.render(fragment)


class DiagramExtension(Extension):
    """Python-Markdown extension that intercepts diagram code blocks."""

    def extendMarkdown(self, md: markdown.Markdown) -> None:  # type: ignore[override]
        md.preprocessors.register(
            DiagramPreprocessor(md), "diagram_pre", 175
        )
        md.postprocessors.register(
            DiagramPostprocessor(md), "diagram_post", 5
        )
        md.diagram_map = {}


class MathExtension(Extension):
    """Python-Markdown extension that renders inline/block LaTeX formulas."""

    def __init__(
        self,
        math_mode: str = "online",
        enable_bare_latex: bool = True,
        online_timeout: int = 10,
        online_providers: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._math_mode = math_mode
        self._enable_bare_latex = enable_bare_latex
        self._online_timeout = online_timeout
        self._online_providers = online_providers

    def extendMarkdown(self, md: markdown.Markdown) -> None:  # type: ignore[override]
        # Run after fenced_code preprocessor so code blocks are not interpreted as formulas.
        md.preprocessors.register(MathPreprocessor(md), "math_pre", 20)
        md.postprocessors.register(MathPostprocessor(md), "math_post", 6)
        md.math_map = {}
        md.enable_bare_latex = self._enable_bare_latex
        md.math_renderer = MathRenderer(
            mode=self._math_mode,
            online_timeout=self._online_timeout,
            online_providers=self._online_providers,
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class MarkdownParser:
    """Parses a Markdown file and returns a ParseResult."""

    def __init__(
        self,
        math_mode: str = "online",
        enable_bare_latex: bool = True,
        online_timeout: int = 10,
        online_providers: list[str] | None = None,
    ) -> None:
        self._math_mode = math_mode
        self._enable_bare_latex = enable_bare_latex
        self._online_timeout = online_timeout
        self._online_providers = online_providers

    def parse(self, filepath: Path) -> ParseResult:
        """Parse *filepath* and return HTML body, metadata, and diagram list."""
        raw = filepath.read_text(encoding="utf-8")
        return self.parse_string(raw)

    def parse_string(self, raw: str) -> ParseResult:
        """Parse a raw Markdown string (useful for testing)."""
        # ① Separate YAML Front Matter
        post = frontmatter.loads(raw)
        metadata: dict[str, Any] = dict(post.metadata)
        body: str = post.content

        # ② Build a fresh Markdown instance with our extensions
        md = markdown.Markdown(
            extensions=[
                DiagramExtension(),
                MathExtension(
                    math_mode=self._math_mode,
                    enable_bare_latex=self._enable_bare_latex,
                    online_timeout=self._online_timeout,
                    online_providers=self._online_providers,
                ),
                "tables",
                "fenced_code",
                "codehilite",
                "toc",
                "attr_list",
                "nl2br",
            ],
            extension_configs={
                "codehilite": {
                    "css_class": "highlight",
                    "guess_lang": False,
                    "use_pygments": True,
                },
                "toc": {
                    "permalink": False,
                },
            },
        )

        # ③ Convert to HTML
        html_body: str = md.convert(body)

        # ④ Collect diagrams from the extension's diagram_map
        diagram_map: dict[str, Diagram] = getattr(md, "diagram_map", {})
        diagrams: list[Diagram] = list(diagram_map.values())

        logger.info(
            "解析完成: %d 个图表, %d 字符 HTML",
            len(diagrams),
            len(html_body),
        )

        return ParseResult(
            metadata=metadata,
            html_body=html_body,
            diagrams=diagrams,
        )

