"""Mermaid diagram renderer.

Strategy selection (controlled by ``MermaidConfig.mode``):
  - "local"  → LocalMMDCStrategy   (Node.js mmdc CLI)
  - "online" → MermaidInkStrategy  (mermaid.ink HTTP API)

Fallback behaviour is identical to the PlantUML renderer.
"""

from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import requests

from ...config.models import MermaidConfig
from ...utils.temp_manager import get_temp_file
from .base import Diagram, DiagramRenderer, RenderResult
from .plantuml_renderer import StrategyUnavailableError

logger = logging.getLogger("mdtopdf.renderer.mermaid")


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class LocalMMDCStrategy:
    """Render via the ``mmdc`` CLI from @mermaid-js/mermaid-cli."""

    def __init__(self, mmdc_path: str, background_color: str = "white") -> None:
        self._mmdc = mmdc_path
        self._bg = background_color

    def is_available(self) -> bool:
        return shutil.which(self._mmdc) is not None

    def render(self, code: str) -> bytes:
        if not self.is_available():
            raise StrategyUnavailableError(
                f"mmdc 命令未找到 ({self._mmdc})，请安装 @mermaid-js/mermaid-cli"
            )
        tmp_input = get_temp_file(suffix=".mmd", prefix="mermaid_in_")
        tmp_input.write_text(code, encoding="utf-8")
        tmp_output = get_temp_file(suffix=".png", prefix="mermaid_out_")
        cmd = [
            self._mmdc,
            "-i",
            str(tmp_input),
            "-o",
            str(tmp_output),
            "-b",
            self._bg,
            "--quiet",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            shell=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"mmdc 渲染失败 (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )
        if not tmp_output.exists() or tmp_output.stat().st_size == 0:
            raise RuntimeError("mmdc 未生成输出文件")
        return tmp_output.read_bytes()


class MermaidInkStrategy:
    """Render via the mermaid.ink public API."""

    def __init__(self, ink_url: str, timeout: int = 30) -> None:
        self._ink_url = ink_url.rstrip("/")
        self._timeout = timeout

    def render(self, code: str) -> bytes:
        payload = {"code": code, "mermaid": {"theme": "default"}}
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("utf-8")
        # Remove padding — mermaid.ink does not expect it
        encoded = encoded.rstrip("=")
        url = f"{self._ink_url}/{encoded}"
        logger.debug("Mermaid.ink 请求: %s", url[:120])
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
            raise RuntimeError(f"mermaid.ink 返回了非图片响应: {content_type}")
        return response.content


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class MermaidRenderer(DiagramRenderer):
    """Mermaid renderer with automatic strategy fallback."""

    def __init__(self, config: MermaidConfig) -> None:
        self._config = config
        self._local = LocalMMDCStrategy(config.mmdc_path, config.background_color)
        self._online = MermaidInkStrategy(config.ink_url, config.timeout)

    def render(self, diagram: Diagram) -> RenderResult:
        code = diagram.code.strip()

        if self._config.mode == "local":
            strategies: list[tuple[str, callable]] = [
                ("本地 mmdc", self._render_local),
                ("Mermaid.ink", self._render_online),
            ]
        else:
            strategies = [
                ("Mermaid.ink", self._render_online),
                ("本地 mmdc", self._render_local),
            ]

        last_error: Optional[str] = None
        for name, strategy_fn in strategies:
            try:
                image_data = strategy_fn(code)
                logger.debug("Mermaid 渲染成功 [%s] (diagram %s)", name, diagram.id[:8])
                return RenderResult(
                    diagram_id=diagram.id,
                    success=True,
                    image_data=image_data,
                    image_format="png",
                    error_message=None,
                )
            except StrategyUnavailableError as exc:
                logger.debug("Mermaid 策略 [%s] 不可用，尝试下一个: %s", name, exc)
                last_error = str(exc)
            except Exception as exc:
                logger.warning("Mermaid 策略 [%s] 渲染失败: %s", name, exc)
                last_error = str(exc)

        logger.warning("Mermaid 所有策略均失败 (diagram %s): %s", diagram.id[:8], last_error)
        return RenderResult(
            diagram_id=diagram.id,
            success=False,
            image_data=None,
            image_format="png",
            error_message=last_error or "未知错误",
        )

    def _render_local(self, code: str) -> bytes:
        if not self._local.is_available():
            raise StrategyUnavailableError(
                f"mmdc 未找到 ({self._config.mmdc_path})，请安装 @mermaid-js/mermaid-cli"
            )
        return self._local.render(code)

    def _render_online(self, code: str) -> bytes:
        return self._online.render(code)

