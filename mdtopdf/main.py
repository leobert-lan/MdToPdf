"""mdtopdf CLI entry point.

Usage examples:
    mdtopdf input.md
    mdtopdf input.md output/doc.pdf --preview
    mdtopdf input.md --plantuml-mode online --mermaid-mode online
    mdtopdf input.md --css theme.css --plantuml-jar /opt/plantuml.jar -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
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
    input_file: Path,
    output_file: Path | None,
    preview: bool,
    config_file: Path | None,
    plantuml_jar: Path | None,
    plantuml_mode: str | None,
    mermaid_mode: str | None,
    custom_css: Path | None,
    open_after: bool,
    verbose: bool,
) -> None:
    """将 Markdown 文件转换为 PDF（支持表格、代码高亮、PlantUML、Mermaid 图表）。

    INPUT_FILE  输入的 .md 或 .markdown 文件路径。

    OUTPUT_FILE 输出 PDF 路径（可选，默认与输入文件同目录同名）。
    """
    # ── 初始化日志 ──────────────────────────────────────────────────────────
    from .utils.logger import setup_logger

    logger = setup_logger(verbose)

    # ── 推导输出路径 ─────────────────────────────────────────────────────────
    from .utils.file_utils import derive_output_path, validate_input_file

    try:
        validate_input_file(input_file)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    resolved_output = derive_output_path(input_file, output_file)

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
    if open_after:
        cli_overrides["open_after_export"] = True

    # ── 执行转换 ─────────────────────────────────────────────────────────────
    try:
        _run_conversion(
            input_file=input_file,
            output_file=resolved_output,
            preview=preview,
            config_file=config_file,
            cli_overrides=cli_overrides,
            open_after=open_after,
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
    input_file: Path,
    output_file: Path,
    preview: bool,
    config_file: Path | None,
    cli_overrides: dict,
    open_after: bool,
) -> None:
    import logging

    logger = logging.getLogger("mdtopdf")

    # Step 1 — Load config
    from .config.config_loader import load_config

    # Step 2 — Parse Markdown (need front matter for config merge)
    from .core.parser import MarkdownParser

    logger.info("解析 Markdown: %s", input_file)
    parser = MarkdownParser()
    parse_result = parser.parse(input_file)

    # Merge config with front matter + CLI overrides
    config = load_config(
        cli_args=cli_overrides,
        front_matter=parse_result.metadata,
        extra_config_path=config_file,
    )

    # Step 3 — Assemble HTML
    from .core.assembler import HTMLAssembler

    logger.info(
        "渲染 %d 个图表并组装 HTML …", len(parse_result.diagrams)
    )
    assembler = HTMLAssembler(config)
    html = assembler.assemble(parse_result, base_dir=input_file.parent)

    # Step 4 — Generate PDF
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

