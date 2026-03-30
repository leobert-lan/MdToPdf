# AGENTS.md — MdToPdf

## Project Overview
Python CLI tool that converts Markdown (with tables, code blocks, PlantUML, Mermaid diagrams) to a single self-contained PDF via the pipeline: **`.md` → Parser → DiagramRenderers → Assembler → WeasyPrint → `.pdf`**. HTML is the mandatory intermediate format. See `docs/system_design.md` for full design rationale and `CRD/crd.md` for requirements.

## Planned Directory Layout
```
mdtopdf/            # main package
  main.py           # click CLI entry point
  core/
    parser.py       # MarkdownParser (python-frontmatter + Python-Markdown + DiagramExtension)
    assembler.py    # HTMLAssembler — merges rendered diagrams into HTML, inlines all CSS
    pdf_generator.py# WeasyPrint wrapper
    previewer.py    # os.startfile() MVP; tkinter+PyMuPDF enhanced version later
    renderer/
      base.py       # DiagramRenderer ABC (render() -> RenderResult)
      plantuml_renderer.py  # LocalJARStrategy | OnlineServiceStrategy
      mermaid_renderer.py   # LocalMMDCStrategy | MermaidInkStrategy
  config/
    config_loader.py# Merges layers in priority order (see below)
    models.py       # AppConfig dataclass
    default_config.yaml
  assets/styles/default.css
  assets/templates/document.html
  utils/            # logger.py, temp_manager.py, file_utils.py
tests/fixtures/     # Sample .md files for tests
```

## Core Architectural Patterns

**Diagram interception:** A custom `DiagramExtension` for Python-Markdown intercepts `plantuml` and `mermaid` fenced code blocks during parsing, replaces them with `<div class="diagram-placeholder" data-id="<uuid>">`, and stores the raw code in `ParseResult.diagrams`. All other fenced blocks go through Pygments (`codehilite`).

**Assembler rule:** Successful renders produce `<img src="data:image/png;base64,...">` (always Base64 Data URI, never file paths). Failed renders produce `<pre class="diagram-error">` with original code + WARNING log. Output HTML must be fully self-contained (no external resource references).

**Config priority (low to high):** `config/default_config.yaml` → `~/.mdtopdf/config.yaml` → YAML Front Matter in the `.md` file → CLI arguments.

**Strategy pattern for renderers:** Local mode is always tried first; if unavailable, falls back to the online API; if that also fails, graceful degradation preserves the original code block. Never abort the whole conversion due to a single diagram failure.

**Concurrency:** Diagram rendering uses `concurrent.futures.ThreadPoolExecutor` — keep renderer logic thread-safe.

## CLI Usage
```bash
mdtopdf input.md                         # output defaults to input.pdf in same dir
mdtopdf input.md out/doc.pdf --preview   # preview via system PDF viewer before saving
mdtopdf input.md --plantuml-mode online --mermaid-mode online  # no local Java/Node needed
mdtopdf input.md --css theme.css --plantuml-jar /opt/plantuml.jar -v
```

## External Environment Dependencies (non-Python)
| Dependency | Required for |
|---|---|
| JRE >= 8 + `plantuml.jar` | Local PlantUML rendering |
| Node.js >= 16 + `@mermaid-js/mermaid-cli` (`mmdc`) | Local Mermaid rendering |
| GTK3 runtime (Windows) | WeasyPrint — **always required** |

Without GTK3, WeasyPrint will not function at all. Install via the official GTK3 Windows installer. For diagram-free or CI use cases, `--plantuml-mode online --mermaid-mode online` avoids the Java and Node.js requirements entirely.

## Windows-Specific Conventions
- All path handling uses `pathlib.Path` (never raw string concatenation).
- Subprocess calls (Java, mmdc) always use `shell=False`.
- Preview uses `os.startfile(tmp_path)` — Windows-only API, no extra dependency.
- CJK fonts: WeasyPrint resolves system fonts automatically; ensure **Microsoft YaHei** or **Noto Sans CJK SC** is installed for Chinese content to render correctly.

## Dev Workflow
```bash
pip install -r requirements-dev.txt
pytest tests/                  # run all tests
pytest --cov=mdtopdf tests/    # with coverage (target >= 70%)
black mdtopdf/                 # format
flake8 mdtopdf/                # lint
mypy mdtopdf/                  # type-check
```
Test fixtures (sample `.md` files) live in `tests/fixtures/`.

