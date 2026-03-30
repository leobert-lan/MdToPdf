"""AppConfig dataclasses — single source of truth for all configuration fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PageConfig:
    size: str = "A4"
    margin_top: str = "2.5cm"
    margin_bottom: str = "2.5cm"
    margin_left: str = "2.5cm"
    margin_right: str = "2.5cm"


@dataclass
class StyleConfig:
    font_family: str = "Arial, 'Noto Sans CJK SC', 'Microsoft YaHei', sans-serif"
    font_size: str = "12pt"
    line_height: str = "1.6"
    code_font_family: str = "'Courier New', Consolas, monospace"
    code_font_size: str = "10pt"
    custom_css: Optional[str] = None  # path to a CSS file


@dataclass
class PlantUMLConfig:
    mode: str = "local"  # "local" | "online"
    jar_path: str = "plantuml.jar"
    server_url: str = "http://www.plantuml.com/plantuml"
    timeout: int = 30


@dataclass
class MermaidConfig:
    mode: str = "local"  # "local" | "online"
    mmdc_path: str = "mmdc"
    ink_url: str = "https://mermaid.ink/img"
    timeout: int = 30
    background_color: str = "white"


@dataclass
class AppConfig:
    # Document metadata
    title: str = ""
    author: str = ""
    date: str = ""

    # Sub-configs
    page: PageConfig = field(default_factory=PageConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    plantuml: PlantUMLConfig = field(default_factory=PlantUMLConfig)
    mermaid: MermaidConfig = field(default_factory=MermaidConfig)

    # Runtime flags
    preview: bool = False
    open_after_export: bool = False
    output_path: Optional[str] = None

