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
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import markdown
from markdown import Extension
from markdown.postprocessors import Postprocessor
from markdown.preprocessors import Preprocessor

from ..core.renderer.base import Diagram

logger = logging.getLogger("mdtopdf.parser")

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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class MarkdownParser:
    """Parses a Markdown file and returns a ParseResult."""

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

