"""PlantUML diagram renderer.

Strategy selection (controlled by ``PlantUMLConfig.mode``):
  - "local"  → LocalJARStrategy  (java -jar plantuml.jar)
  - "online" → OnlineServiceStrategy  (plantuml.com HTTP API)

The renderer always tries the configured primary strategy first.  If that
strategy detects it cannot operate (e.g. JAR file missing, Java not found),
it raises ``StrategyUnavailableError`` and the renderer falls back to the
online service.  If both fail, it returns a RenderResult with success=False.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import zlib
from pathlib import Path
from typing import Optional

import requests

from ...config.models import PlantUMLConfig
from ...utils.temp_manager import get_temp_file
from .base import Diagram, DiagramRenderer, RenderResult

logger = logging.getLogger("mdtopdf.renderer.plantuml")


# ---------------------------------------------------------------------------
# Custom exception for "strategy not available"
# ---------------------------------------------------------------------------


class StrategyUnavailableError(Exception):
    """Raised when a strategy cannot be used in the current environment."""


# ---------------------------------------------------------------------------
# Encoding helper for the online API
# ---------------------------------------------------------------------------

_PLANTUML_CHARS = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)


def _encode_plantuml(text: str) -> str:
    """Encode PlantUML source for inclusion in a plantuml.com URL."""
    compressed = zlib.compress(text.encode("utf-8"), 9)
    # Strip the 2-byte zlib header and 4-byte Adler-32 checksum
    deflated = compressed[2:-4]
    return _b64_plantuml(deflated)


def _b64_plantuml(data: bytes) -> str:
    result: list[str] = []
    n = len(data)
    for i in range(0, n, 3):
        b1 = data[i]
        b2 = data[i + 1] if i + 1 < n else 0
        b3 = data[i + 2] if i + 2 < n else 0
        result.append(_PLANTUML_CHARS[(b1 >> 2) & 0x3F])
        result.append(_PLANTUML_CHARS[((b1 & 0x3) << 4 | b2 >> 4) & 0x3F])
        result.append(_PLANTUML_CHARS[((b2 & 0xF) << 2 | b3 >> 6) & 0x3F])
        result.append(_PLANTUML_CHARS[b3 & 0x3F])
    return "".join(result)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class LocalJARStrategy:
    """Render via a local ``plantuml.jar`` file."""

    def __init__(self, jar_path: str) -> None:
        self._jar = Path(jar_path)

    def is_available(self) -> bool:
        if not self._jar.is_absolute():
            # Search in PATH as well
            found = shutil.which(str(self._jar))
            if found:
                self._jar = Path(found)
                return True
        return self._jar.exists() and shutil.which("java") is not None

    def render(self, code: str) -> bytes:
        if not self.is_available():
            raise StrategyUnavailableError(
                f"plantuml.jar 不可用 ({self._jar}) 或 Java 未安装"
            )
        tmp_input = get_temp_file(suffix=".puml", prefix="plantuml_in_")
        tmp_input.write_text(code, encoding="utf-8")
        tmp_output = tmp_input.with_suffix(".png")
        cmd = [
            "java",
            "-jar",
            str(self._jar),
            "-tpng",
            "-charset",
            "UTF-8",
            str(tmp_input),
            "-o",
            str(tmp_input.parent),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            shell=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"plantuml 渲染失败 (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )
        if not tmp_output.exists():
            raise RuntimeError("plantuml 未生成输出文件")
        return tmp_output.read_bytes()


class OnlineServiceStrategy:
    """Render via the plantuml.com HTTP API."""

    def __init__(self, server_url: str, timeout: int = 30) -> None:
        self._server_url = server_url.rstrip("/")
        self._timeout = timeout

    def render(self, code: str) -> bytes:
        encoded = _encode_plantuml(code)
        url = f"{self._server_url}/png/{encoded}"
        logger.debug("PlantUML online 请求: %s", url[:120])
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        # The service returns an error image for invalid diagrams — detect it
        content_type = response.headers.get("Content-Type", "")
        if "image" not in content_type:
            raise RuntimeError(f"plantuml.com 返回了非图片响应: {content_type}")
        return response.content


# ---------------------------------------------------------------------------
# Renderer (strategy selector)
# ---------------------------------------------------------------------------


class PlantUMLRenderer(DiagramRenderer):
    """PlantUML renderer with automatic strategy fallback."""

    def __init__(self, config: PlantUMLConfig) -> None:
        self._config = config
        self._local = LocalJARStrategy(config.jar_path)
        self._online = OnlineServiceStrategy(config.server_url, config.timeout)

    def render(self, diagram: Diagram) -> RenderResult:
        code = diagram.code.strip()
        # Wrap in @startuml / @enduml if not present
        if not code.startswith("@start"):
            code = f"@startuml\n{code}\n@enduml"

        strategies: list[tuple[str, callable]] = []
        if self._config.mode == "local":
            strategies = [
                ("本地 JAR", self._render_local),
                ("在线服务", self._render_online),
            ]
        else:
            strategies = [
                ("在线服务", self._render_online),
                ("本地 JAR", self._render_local),
            ]

        last_error: Optional[str] = None
        for name, strategy_fn in strategies:
            try:
                image_data = strategy_fn(code)
                logger.debug("PlantUML 渲染成功 [%s] (diagram %s)", name, diagram.id[:8])
                return RenderResult(
                    diagram_id=diagram.id,
                    success=True,
                    image_data=image_data,
                    image_format="png",
                    error_message=None,
                )
            except StrategyUnavailableError as exc:
                logger.debug("PlantUML 策略 [%s] 不可用，尝试下一个: %s", name, exc)
                last_error = str(exc)
            except Exception as exc:
                logger.warning("PlantUML 策略 [%s] 渲染失败: %s", name, exc)
                last_error = str(exc)

        logger.warning("PlantUML 所有策略均失败 (diagram %s): %s", diagram.id[:8], last_error)
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
                f"plantuml.jar 不可用 ({self._config.jar_path}) 或 Java 未安装"
            )
        return self._local.render(code)

    def _render_online(self, code: str) -> bytes:
        return self._online.render(code)

