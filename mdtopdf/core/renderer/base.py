"""Abstract base class and shared data types for diagram renderers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Diagram:
    """A diagram extracted from a Markdown fenced code block."""

    id: str          # UUID string — used as placeholder data-id
    type: str        # "plantuml" | "mermaid"
    code: str        # Raw diagram source code


@dataclass
class RenderResult:
    """Outcome of a single diagram render attempt."""

    diagram_id: str
    success: bool
    image_data: Optional[bytes]   # PNG (or SVG) bytes when success=True
    image_format: str             # "png" | "svg"
    error_message: Optional[str]  # Human-readable error when success=False


class DiagramRenderer(ABC):
    """Strategy interface for diagram renderers.

    Concrete implementations must be thread-safe because the assembler may
    invoke ``render()`` from a ThreadPoolExecutor.
    """

    @abstractmethod
    def render(self, diagram: Diagram) -> RenderResult:
        """Render *diagram* and return a RenderResult.

        Must never raise — failures are captured in ``RenderResult.success``.
        """

