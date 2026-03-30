"""Config loader — merges all configuration layers into a single AppConfig.

Priority (low → high):
  default_config.yaml → ~/.mdtopdf/config.yaml → extra config file
  → YAML Front Matter → CLI arguments
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from .models import AppConfig, MermaidConfig, PageConfig, PlantUMLConfig, StyleConfig

logger = logging.getLogger("mdtopdf.config")

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"
_USER_CONFIG_PATH = Path.home() / ".mdtopdf" / "config.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(
    cli_args: Optional[dict[str, Any]] = None,
    front_matter: Optional[dict[str, Any]] = None,
    extra_config_path: Optional[Path] = None,
) -> AppConfig:
    """Return a fully merged AppConfig from all layers."""

    # Layer 1 — built-in defaults
    data: dict[str, Any] = _load_yaml(_DEFAULT_CONFIG_PATH)

    # Layer 2 — user-level config
    if _USER_CONFIG_PATH.exists():
        try:
            user_data = _load_yaml(_USER_CONFIG_PATH)
            data = _deep_merge(data, user_data)
        except Exception as exc:
            logger.warning("无法加载用户配置 %s: %s", _USER_CONFIG_PATH, exc)

    # Layer 3 — explicit extra config file (--config CLI option)
    if extra_config_path is not None:
        if extra_config_path.exists():
            try:
                extra_data = _load_yaml(extra_config_path)
                data = _deep_merge(data, extra_data)
            except Exception as exc:
                logger.warning("无法加载配置文件 %s: %s", extra_config_path, exc)
        else:
            logger.warning("配置文件不存在: %s", extra_config_path)

    # Layer 4 — YAML Front Matter
    if front_matter:
        data = _apply_front_matter(data, front_matter)

    # Layer 5 — CLI arguments (highest priority)
    if cli_args:
        data = _apply_cli_args(data, cli_args)

    return _build_config(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        result = yaml.safe_load(fh)
    return result if isinstance(result, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base* (non-destructive)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif value is not None:
            result[key] = value
    return result


def _apply_front_matter(data: dict[str, Any], fm: dict[str, Any]) -> dict[str, Any]:
    """Map front-matter keys to the internal config structure."""
    data = data.copy()

    # Top-level metadata
    for key in ("title", "author", "date"):
        if key in fm:
            data[key] = fm[key]

    # Allow front-matter to override page size
    if "page_size" in fm:
        data.setdefault("page", {})["size"] = fm["page_size"]

    # Allow overriding CSS path
    if "custom_css" in fm:
        data.setdefault("style", {})["custom_css"] = fm["custom_css"]

    # Allow per-document diagram mode
    if "plantuml_mode" in fm:
        data.setdefault("plantuml", {})["mode"] = fm["plantuml_mode"]
    if "mermaid_mode" in fm:
        data.setdefault("mermaid", {})["mode"] = fm["mermaid_mode"]

    return data


def _apply_cli_args(data: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """Map flat CLI argument dict onto the nested config structure."""
    data = data.copy()

    mapping = {
        "plantuml_mode": ("plantuml", "mode"),
        "plantuml_jar_path": ("plantuml", "jar_path"),
        "mermaid_mode": ("mermaid", "mode"),
        "custom_css": ("style", "custom_css"),
        "open_after_export": ("output", "open_after_export"),
    }

    for cli_key, (section, field) in mapping.items():
        if cli_key in args and args[cli_key] is not None:
            data.setdefault(section, {})[field] = args[cli_key]

    # Direct top-level overrides
    for key in ("title", "author"):
        if key in args and args[key] is not None:
            data[key] = args[key]

    return data


def _build_config(data: dict[str, Any]) -> AppConfig:
    """Construct an AppConfig dataclass from the merged dict."""

    page_raw = data.get("page", {})
    margin_raw = page_raw.get("margin", {})
    page = PageConfig(
        size=page_raw.get("size", "A4"),
        margin_top=margin_raw.get("top", "2.5cm"),
        margin_bottom=margin_raw.get("bottom", "2.5cm"),
        margin_left=margin_raw.get("left", "2.5cm"),
        margin_right=margin_raw.get("right", "2.5cm"),
    )

    style_raw = data.get("style", {})
    style = StyleConfig(
        font_family=style_raw.get(
            "font_family", "Arial, 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
        ),
        font_size=style_raw.get("font_size", "12pt"),
        line_height=str(style_raw.get("line_height", "1.6")),
        code_font_family=style_raw.get(
            "code_font_family", "'Courier New', Consolas, monospace"
        ),
        code_font_size=style_raw.get("code_font_size", "10pt"),
        custom_css=style_raw.get("custom_css"),
    )

    pu_raw = data.get("plantuml", {})
    plantuml = PlantUMLConfig(
        mode=pu_raw.get("mode", "local"),
        jar_path=pu_raw.get("jar_path", "plantuml.jar"),
        server_url=pu_raw.get("server_url", "http://www.plantuml.com/plantuml"),
        timeout=int(pu_raw.get("timeout", 30)),
    )

    mm_raw = data.get("mermaid", {})
    mermaid = MermaidConfig(
        mode=mm_raw.get("mode", "local"),
        mmdc_path=mm_raw.get("mmdc_path", "mmdc"),
        ink_url=mm_raw.get("ink_url", "https://mermaid.ink/img"),
        timeout=int(mm_raw.get("timeout", 30)),
        background_color=mm_raw.get("background_color", "white"),
    )

    output_raw = data.get("output", {})

    return AppConfig(
        title=str(data.get("title", "")),
        author=str(data.get("author", "")),
        date=str(data.get("date", "")),
        page=page,
        style=style,
        plantuml=plantuml,
        mermaid=mermaid,
        preview=bool(data.get("preview", {}).get("enabled", False)),
        open_after_export=bool(output_raw.get("open_after_export", False)),
    )

