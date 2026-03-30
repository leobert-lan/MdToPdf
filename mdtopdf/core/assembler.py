"""HTML Assembler — combines parser output, rendered diagrams, CSS, and the
document template into a single fully self-contained HTML string.

Pipeline:
  ParseResult  +  RenderResults  →  complete HTML (no external references)

Diagram rendering is performed concurrently via ThreadPoolExecutor.
"""

from __future__ import annotations

import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pygments.formatters import HtmlFormatter

from ..config.models import AppConfig
from .parser import ParseResult
from .renderer.base import Diagram, DiagramRenderer, RenderResult
from .renderer.mermaid_renderer import MermaidRenderer
from .renderer.plantuml_renderer import PlantUMLRenderer

logger = logging.getLogger("mdtopdf.assembler")

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
_STYLES_DIR = _ASSETS_DIR / "styles"
_TEMPLATES_DIR = _ASSETS_DIR / "templates"

# ── Image inlining helpers ────────────────────────────────────────────────────
# Matches the src attribute inside any <img> tag
_IMG_SRC_RE = re.compile(
    r'(<img\b[^>]*?\bsrc=)(["\'])(.*?)\2',
    re.IGNORECASE | re.DOTALL,
)

_IMG_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


class HTMLAssembler:
    """Assembles a complete, self-contained HTML document from a ParseResult."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._plantuml_renderer = PlantUMLRenderer(config.plantuml)
        self._mermaid_renderer = MermaidRenderer(config.mermaid)

        self._jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=False,  # We handle escaping ourselves
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(self, parse_result: ParseResult, base_dir: Optional[Path] = None) -> str:
        """Return a complete HTML string ready for WeasyPrint.

        Args:
            parse_result: Output from MarkdownParser.
            base_dir: Directory of the source .md file, used to resolve
                      relative image paths.  When None, local images are
                      left as-is (WeasyPrint may not be able to load them).
        """
        # ① Render all diagrams (concurrently)
        render_results = self._render_diagrams(parse_result.diagrams)

        # ② Replace diagram placeholders in the HTML body
        html_body = self._substitute_placeholders(
            parse_result.html_body, parse_result.diagrams, render_results
        )

        # ② ½  Inline local images as base64 data URIs (self-contained HTML)
        if base_dir is not None:
            html_body = self._inline_local_images(html_body, base_dir)

        # ③ Build the CSS bundle
        css = self._build_css()

        # ④ Determine document metadata
        title = self._config.title or parse_result.metadata.get("title", "")
        author = self._config.author or parse_result.metadata.get("author", "")
        date = self._config.date or str(parse_result.metadata.get("date", ""))

        # ⑤ Render Jinja2 template
        template = self._jinja_env.get_template("document.html")
        html = template.render(
            title=escape(title) if title else "",
            author=escape(author) if author else "",
            date=escape(date) if date else "",
            css=css,
            body=html_body,
        )

        logger.info("HTML 组装完成 (%d 字符)", len(html))
        return html

    # ------------------------------------------------------------------
    # Diagram rendering
    # ------------------------------------------------------------------

    def _render_diagrams(
        self, diagrams: list[Diagram]
    ) -> dict[str, RenderResult]:
        """Render all diagrams concurrently; return a dict keyed by diagram id."""
        if not diagrams:
            return {}

        results: dict[str, RenderResult] = {}
        max_workers = min(8, len(diagrams))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_diagram = {
                executor.submit(self._render_one, d): d for d in diagrams
            }
            for future in as_completed(future_to_diagram):
                diagram = future_to_diagram[future]
                try:
                    result = future.result()
                except Exception as exc:
                    logger.warning(
                        "渲染图表时发生意外异常 (%s): %s", diagram.id[:8], exc
                    )
                    result = RenderResult(
                        diagram_id=diagram.id,
                        success=False,
                        image_data=None,
                        image_format="png",
                        error_message=str(exc),
                    )
                results[diagram.id] = result

        return results

    def _render_one(self, diagram: Diagram) -> RenderResult:
        if diagram.type == "plantuml":
            return self._plantuml_renderer.render(diagram)
        elif diagram.type == "mermaid":
            return self._mermaid_renderer.render(diagram)
        else:
            return RenderResult(
                diagram_id=diagram.id,
                success=False,
                image_data=None,
                image_format="png",
                error_message=f"未知图表类型: {diagram.type}",
            )

    # ------------------------------------------------------------------
    # Placeholder substitution
    # ------------------------------------------------------------------

    def _substitute_placeholders(
        self,
        html_body: str,
        diagrams: list[Diagram],
        render_results: dict[str, RenderResult],
    ) -> str:
        for diagram in diagrams:
            placeholder = (
                f'<div class="diagram-placeholder" data-id="{diagram.id}"></div>'
            )
            result = render_results.get(diagram.id)

            if result and result.success and result.image_data:
                b64 = base64.b64encode(result.image_data).decode("ascii")
                mime = f"image/{result.image_format}"
                replacement = (
                    f'<div class="diagram-wrapper">'
                    f'<img class="diagram-img" '
                    f'src="data:{mime};base64,{b64}" '
                    f'alt="{escape(diagram.type)} diagram">'
                    f"</div>"
                )
                logger.debug(
                    "图表 %s 替换为 Base64 图片 (%d bytes)",
                    diagram.id[:8],
                    len(result.image_data),
                )
            else:
                error_msg = (result.error_message if result else "未知错误") or "未知错误"
                safe_code = escape(diagram.code)
                replacement = (
                    f'<div class="diagram-error">'
                    f'<p class="error-header">⚠&nbsp;图表渲染失败'
                    f"（{escape(diagram.type)}）</p>"
                    f"<p class=\"error-detail\">{escape(error_msg)}</p>"
                    f"<pre>{safe_code}</pre>"
                    f"</div>"
                )
                logger.warning(
                    "图表 %s 渲染失败，已保留原始代码块: %s",
                    diagram.id[:8],
                    error_msg,
                )

            html_body = html_body.replace(placeholder, replacement)

        return html_body

    # ------------------------------------------------------------------
    # CSS assembly
    # ------------------------------------------------------------------

    def _build_css(self) -> str:
        parts: list[str] = []

        # 1. Default CSS
        default_css_path = _STYLES_DIR / "default.css"
        if default_css_path.exists():
            parts.append(default_css_path.read_text(encoding="utf-8"))
        else:
            logger.warning("默认 CSS 文件不存在: %s", default_css_path)

        # 2. Pygments syntax-highlight CSS  (friendly → GitHub-Light-compatible)
        pygments_css = HtmlFormatter(
            style="friendly", cssclass="highlight"
        ).get_style_defs(".highlight")
        parts.append(pygments_css)

        # 3. Dynamic @page rule from config
        parts.append(self._build_page_css())

        # 4. User-supplied custom CSS (highest priority)
        custom_css_path: Optional[str] = self._config.style.custom_css
        if custom_css_path:
            p = Path(custom_css_path)
            if p.exists():
                parts.append(p.read_text(encoding="utf-8"))
                logger.debug("已加载自定义 CSS: %s", p)
            else:
                logger.warning("自定义 CSS 文件不存在，已忽略: %s", p)

        return "\n\n".join(parts)

    def _build_page_css(self) -> str:
        pg = self._config.page
        st = self._config.style
        return f"""
/* --- Dynamic config overrides --- */
@page {{
    size: {pg.size};
    margin: {pg.margin_top} {pg.margin_right} {pg.margin_bottom} {pg.margin_left};
}}
body {{
    font-family: {st.font_family};
    font-size: {st.font_size};
    line-height: {st.line_height};
}}
.highlight pre, code {{
    font-family: {st.code_font_family};
    font-size: {st.code_font_size};
}}
"""

    @staticmethod
    def _inline_local_images(html: str, base_dir: Path) -> str:
        """Replace local image ``src`` paths with base64 data URIs.

        Only relative and absolute *file* paths are processed.
        ``http://``, ``https://``, ``data:`` and ``//`` sources are skipped.
        """

        def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
            prefix = m.group(1)  # e.g. '<img alt="x" src='
            src = m.group(3)     # the raw src value

            # Skip remote / already-inlined sources
            if not src or src.startswith(
                ("data:", "http://", "https://", "//", "ftp://", "#")
            ):
                return m.group(0)

            try:
                img_path = Path(src)
                if not img_path.is_absolute():
                    img_path = (base_dir / src).resolve()
                else:
                    img_path = img_path.resolve()

                if not img_path.exists():
                    logger.warning("图片文件不存在，跳过内联: %s", img_path)
                    return m.group(0)

                mime = _IMG_MIME_MAP.get(img_path.suffix.lower(), "image/octet-stream")
                b64 = base64.b64encode(img_path.read_bytes()).decode()
                logger.debug(
                    "内联图片: %s (%d KB)",
                    img_path.name,
                    img_path.stat().st_size // 1024,
                )
                return f'{prefix}"data:{mime};base64,{b64}"'

            except Exception as exc:
                logger.warning("内联图片失败 (%s): %s", src, exc)
                return m.group(0)

        return _IMG_SRC_RE.sub(_replace, html)
