"""mdtopdf CLI entry point.

Usage examples:
    mdtopdf input.md
    mdtopdf input.md output/doc.pdf --preview
    mdtopdf input.md --plantuml-mode online --mermaid-mode online
    mdtopdf input.md --css theme.css --plantuml-jar /opt/plantuml.jar -v
"""

from __future__ import annotations

import sys
import re
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

import click
import frontmatter

from . import __version__

if TYPE_CHECKING:
    from .core.parser import ParseResult


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_path", type=click.Path(exists=True, file_okay=True, dir_okay=True, path_type=Path))
@click.argument("output_file", required=False, type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--preview/--no-preview",
    default=False,
    show_default=True,
    help="生成 PDF 前用系统默认查看器预览。",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="外部配置文件路径（YAML）。",
)
@click.option(
    "--plantuml-jar",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="PlantUML JAR 文件路径。",
)
@click.option(
    "--plantuml-mode",
    type=click.Choice(["local", "online"], case_sensitive=False),
    default=None,
    help="PlantUML 渲染模式：local（本地 JAR）或 online（plantuml.com）。",
)
@click.option(
    "--mermaid-mode",
    type=click.Choice(["local", "online"], case_sensitive=False),
    default=None,
    help="Mermaid 渲染模式：local（mmdc）或 online（mermaid.ink）。",
)
@click.option(
    "--css",
    "custom_css",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="自定义 CSS 文件路径，覆盖默认样式。",
)
@click.option(
    "--math-mode",
    type=click.Choice(["online", "auto", "latex2mathml"], case_sensitive=False),
    default=None,
    help="数学公式渲染策略：online / auto / latex2mathml。",
)
@click.option(
    "--math-online-timeout",
    type=int,
    default=None,
    help="在线公式 API 超时（秒）。",
)
@click.option(
    "--math-online-providers",
    type=str,
    default=None,
    help="在线公式节点链，逗号分隔，例如 codecogs_png,vercel_svg,mathnow_svg。",
)
@click.option(
    "--math-bare-latex/--no-math-bare-latex",
    default=None,
    help="是否启用裸 LaTeX（如 \\omega、\\sum）自动识别。",
)
@click.option(
    "--merge-toc/--no-merge-toc",
    default=False,
    show_default=True,
    help="当输入为单个 Markdown 文件时，按该文件中的链接顺序合并章节 Markdown。",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    default=False,
    help="生成完成后自动打开 PDF 文件。",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="输出详细处理日志。",
)
@click.version_option(version=__version__, prog_name="mdtopdf")
def cli(
    input_path: Path,
    output_file: Path | None,
    preview: bool,
    config_file: Path | None,
    plantuml_jar: Path | None,
    plantuml_mode: str | None,
    mermaid_mode: str | None,
    custom_css: Path | None,
    math_mode: str | None,
    math_online_timeout: int | None,
    math_online_providers: str | None,
    math_bare_latex: bool | None,
    merge_toc: bool,
    open_after: bool,
    verbose: bool,
) -> None:
    """将 Markdown 文件转换为 PDF（支持表格、代码高亮、PlantUML、Mermaid 图表）。

    INPUT_PATH  输入 Markdown 文件路径，或用于合并模式的目录路径。

    OUTPUT_FILE 输出 PDF 路径（可选，默认与输入文件同目录同名）。
    """
    # ── 初始化日志 ──────────────────────────────────────────────────────────
    from .utils.logger import setup_logger

    logger = setup_logger(verbose)

    # ── 推导输出路径 ─────────────────────────────────────────────────────────
    from .utils.file_utils import derive_output_path, validate_input_path

    try:
        validate_input_path(input_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    output_seed = input_path
    if input_path.is_dir() and output_file is None:
        output_seed = input_path.parent / f"{input_path.name}.md"
    resolved_output = derive_output_path(output_seed, output_file)

    # ── 组装 CLI 覆盖参数 ────────────────────────────────────────────────────
    cli_overrides: dict = {}
    if plantuml_jar:
        cli_overrides["plantuml_jar_path"] = str(plantuml_jar)
    if plantuml_mode:
        cli_overrides["plantuml_mode"] = plantuml_mode
    if mermaid_mode:
        cli_overrides["mermaid_mode"] = mermaid_mode
    if custom_css:
        cli_overrides["custom_css"] = str(custom_css)
    if math_mode:
        cli_overrides["math_mode"] = math_mode
    if math_online_timeout is not None:
        cli_overrides["math_online_timeout"] = math_online_timeout
    if math_online_providers:
        cli_overrides["math_online_providers"] = math_online_providers
    if math_bare_latex is not None:
        cli_overrides["math_enable_bare_latex"] = math_bare_latex
    if open_after:
        cli_overrides["open_after_export"] = True

    # ── 执行转换 ─────────────────────────────────────────────────────────────
    try:
        _run_conversion(
            input_path=input_path,
            output_file=resolved_output,
            preview=preview,
            config_file=config_file,
            cli_overrides=cli_overrides,
            open_after=open_after,
            merge_toc=merge_toc,
        )
    except Exception as exc:
        logger.error("转换失败: %s", exc)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


# ---------------------------------------------------------------------------
# Conversion pipeline
# ---------------------------------------------------------------------------


def _run_conversion(
    input_path: Path,
    output_file: Path,
    preview: bool,
    config_file: Path | None,
    cli_overrides: dict,
    open_after: bool,
    merge_toc: bool,
) -> None:
    import logging

    logger = logging.getLogger("mdtopdf")

    # Step 1 — Load config
    from .config.config_loader import load_config

    # Step 2 — Resolve all markdown inputs (single, directory, or toc-merge)
    input_files = _resolve_input_files(input_path, merge_toc)
    raw_markdowns = [p.read_text(encoding="utf-8") for p in input_files]
    front_matter = dict(frontmatter.loads(raw_markdowns[0]).metadata)

    # Merge config with front matter + CLI overrides
    config = load_config(
        cli_args=cli_overrides,
        front_matter=front_matter,
        extra_config_path=config_file,
    )

    # Step 3 — Parse Markdown with configured math strategy
    from .core.parser import MarkdownParser

    logger.info("解析 Markdown: %d 个文件", len(input_files))
    parser = MarkdownParser(
        math_mode=config.math.mode,
        enable_bare_latex=config.math.enable_bare_latex,
        online_timeout=config.math.online_timeout,
        online_providers=config.math.online_providers,
    )
    parsed_results = []
    for file_path, raw_markdown in zip(input_files, raw_markdowns):
        logger.info("解析文件: %s", file_path)
        chapter_result = parser.parse_string(raw_markdown)
        chapter_result.html_body = _absolutize_local_image_sources(
            chapter_result.html_body,
            file_path.parent,
        )
        parsed_results.append((file_path, chapter_result))

    parse_result = _merge_parse_results(parsed_results)

    # Step 4 — Assemble HTML
    from .core.assembler import HTMLAssembler

    logger.info(
        "渲染 %d 个图表并组装 HTML …", len(parse_result.diagrams)
    )
    assembler = HTMLAssembler(config)
    base_dir = input_path.parent if input_path.is_file() else input_path
    html = assembler.assemble(parse_result, base_dir=base_dir)

    # Step 5 — Generate PDF
    from .core.pdf_generator import PDFGenerator

    generator = PDFGenerator()

    if preview:
        from .core.previewer import Previewer

        logger.info("生成预览 PDF …")
        pdf_bytes = generator.generate_bytes(html)
        Previewer().preview(pdf_bytes)
        click.pause(info="按任意键继续保存最终 PDF，或 Ctrl+C 取消 …")

    logger.info("写入 PDF: %s", output_file)
    generator.generate_file(html, output_file)

    if open_after:
        import os

        os.startfile(str(output_file))  # type: ignore[attr-defined]

    click.echo(f"✓ 已生成 PDF: {output_file}")


_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.m(?:d|arkdown))(?:#[^)]+)?\)", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=)(["\'])(.*?)\2', re.IGNORECASE | re.DOTALL)


def _resolve_input_files(input_path: Path, merge_toc: bool) -> list[Path]:
    from .utils.file_utils import collect_markdown_files

    if input_path.is_dir():
        files = collect_markdown_files(input_path)
        if not files:
            raise ValueError(f"目录内未找到 Markdown 文件: {input_path}")
        return files

    if not merge_toc:
        return [input_path]

    linked = _extract_markdown_links(input_path)
    if not linked:
        return [input_path]

    ordered = [input_path]
    seen = {input_path.resolve()}
    for p in linked:
        resolved = p.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(p)
    return ordered


def _extract_markdown_links(toc_file: Path) -> list[Path]:
    content = toc_file.read_text(encoding="utf-8")
    links: list[Path] = []
    for match in _MD_LINK_RE.findall(content):
        rel = match.strip()
        if rel.startswith(("http://", "https://", "#")):
            continue
        path = (toc_file.parent / rel).resolve()
        if path.exists() and path.is_file() and path.suffix.lower() in {".md", ".markdown"}:
            links.append(path)
    return links


def _merge_parse_results(parsed_results: list[tuple[Path, ParseResult]]) -> ParseResult:
    from .core.parser import ParseResult

    metadata: dict = {}
    html_parts: list[str] = []
    diagrams = []

    for idx, (file_path, result) in enumerate(parsed_results):
        if not metadata and getattr(result, "metadata", None):
            metadata = dict(result.metadata)
        diagrams.extend(result.diagrams)
        section = (
            f'<section class="mdtopdf-merged-chapter" data-source="{escape(str(file_path))}">'
            f"{result.html_body}"
            "</section>"
        )
        html_parts.append(section)
        if idx < len(parsed_results) - 1:
            html_parts.append("<hr class=\"chapter-divider\">")

    return ParseResult(
        metadata=metadata,
        html_body="\n".join(html_parts),
        diagrams=diagrams,
    )


def _absolutize_local_image_sources(html_body: str, base_dir: Path) -> str:
    def _replace(match: re.Match) -> str:
        prefix = match.group(1)
        quote = match.group(2)
        src = match.group(3)
        if not src or src.startswith(("data:", "http://", "https://", "//", "ftp://", "#")):
            return match.group(0)

        candidate = Path(src)
        if not candidate.is_absolute():
            candidate = (base_dir / src).resolve()
        else:
            candidate = candidate.resolve()
        return f"{prefix}{quote}{candidate.as_posix()}{quote}"

    return _IMG_SRC_RE.sub(_replace, html_body)


