"""Tests for PlantUML and Mermaid renderers."""

from __future__ import annotations

import shutil
from unittest.mock import MagicMock, patch

import pytest

from mdtopdf.config.models import MermaidConfig, PlantUMLConfig
from mdtopdf.core.renderer.base import Diagram, RenderResult
from mdtopdf.core.renderer.mermaid_renderer import (
    MermaidInkStrategy,
    MermaidRenderer,
)
from mdtopdf.core.renderer.plantuml_renderer import (
    LocalJARStrategy,
    OnlineServiceStrategy,
    PlantUMLRenderer,
    StrategyUnavailableError,
    _encode_plantuml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _diagram(type_: str = "plantuml", code: str = "@startuml\nA->B\n@enduml") -> Diagram:
    return Diagram(id="test-id-0001", type=type_, code=code)


FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


# ---------------------------------------------------------------------------
# PlantUML encoding
# ---------------------------------------------------------------------------


class TestPlantUMLEncoding:
    def test_encode_returns_string(self):
        encoded = _encode_plantuml("@startuml\nA->B\n@enduml")
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_encode_different_inputs_give_different_outputs(self):
        a = _encode_plantuml("@startuml\nA->B\n@enduml")
        b = _encode_plantuml("@startuml\nC->D\n@enduml")
        assert a != b


# ---------------------------------------------------------------------------
# LocalJARStrategy
# ---------------------------------------------------------------------------


class TestLocalJARStrategy:
    def test_unavailable_when_jar_missing(self):
        strategy = LocalJARStrategy("/nonexistent/plantuml.jar")
        assert strategy.is_available() is False

    def test_unavailable_when_java_missing(self):
        strategy = LocalJARStrategy("plantuml.jar")
        with patch("shutil.which", return_value=None):
            assert strategy.is_available() is False

    def test_raises_when_unavailable(self):
        strategy = LocalJARStrategy("/nonexistent/plantuml.jar")
        with pytest.raises(StrategyUnavailableError):
            strategy.render("@startuml\nA->B\n@enduml")


# ---------------------------------------------------------------------------
# OnlineServiceStrategy
# ---------------------------------------------------------------------------


class TestOnlineServiceStrategy:
    def test_successful_render(self):
        strategy = OnlineServiceStrategy("http://www.plantuml.com/plantuml", timeout=5)
        mock_response = MagicMock()
        mock_response.content = FAKE_PNG
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = strategy.render("@startuml\nA->B\n@enduml")

        assert result == FAKE_PNG
        mock_get.assert_called_once()

    def test_raises_on_non_image_response(self):
        strategy = OnlineServiceStrategy("http://www.plantuml.com/plantuml")
        mock_response = MagicMock()
        mock_response.content = b"error"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(RuntimeError, match="非图片"):
                strategy.render("@startuml\nA->B\n@enduml")


# ---------------------------------------------------------------------------
# PlantUMLRenderer (strategy selection & fallback)
# ---------------------------------------------------------------------------


class TestPlantUMLRenderer:
    def _renderer(self, mode: str = "online") -> PlantUMLRenderer:
        config = PlantUMLConfig(mode=mode, timeout=5)
        return PlantUMLRenderer(config)

    def test_online_mode_success(self):
        renderer = self._renderer("online")
        with patch.object(renderer._online, "render", return_value=FAKE_PNG):
            result = renderer.render(_diagram())
        assert result.success is True
        assert result.image_data == FAKE_PNG

    def test_local_unavailable_falls_back_to_online(self):
        renderer = self._renderer("local")
        # Local is unavailable
        with patch.object(renderer._local, "is_available", return_value=False):
            with patch.object(renderer._online, "render", return_value=FAKE_PNG):
                result = renderer.render(_diagram())
        assert result.success is True

    def test_all_strategies_fail_returns_failure(self):
        renderer = self._renderer("online")
        with patch.object(renderer._online, "render", side_effect=RuntimeError("network error")):
            with patch.object(renderer._local, "is_available", return_value=False):
                result = renderer.render(_diagram())
        assert result.success is False
        assert result.error_message is not None

    def test_result_has_correct_diagram_id(self):
        renderer = self._renderer("online")
        d = _diagram()
        with patch.object(renderer._online, "render", return_value=FAKE_PNG):
            result = renderer.render(d)
        assert result.diagram_id == d.id

    def test_code_wrapped_in_startuml_if_missing(self):
        renderer = self._renderer("online")
        d = Diagram(id="x", type="plantuml", code="A -> B")  # no @startuml
        captured_code: list[str] = []

        def capture(code: str) -> bytes:
            captured_code.append(code)
            return FAKE_PNG

        with patch.object(renderer._online, "render", side_effect=capture):
            renderer.render(d)

        assert captured_code[0].startswith("@startuml")
        assert captured_code[0].strip().endswith("@enduml")


# ---------------------------------------------------------------------------
# MermaidInkStrategy
# ---------------------------------------------------------------------------


class TestMermaidInkStrategy:
    def test_successful_render(self):
        strategy = MermaidInkStrategy("https://mermaid.ink/img", timeout=5)
        mock_response = MagicMock()
        mock_response.content = FAKE_PNG
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            result = strategy.render("graph TD\nA-->B")

        assert result == FAKE_PNG

    def test_raises_on_non_image_response(self):
        strategy = MermaidInkStrategy("https://mermaid.ink/img")
        mock_response = MagicMock()
        mock_response.content = b"error page"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            with pytest.raises(RuntimeError):
                strategy.render("graph TD\nA-->B")


# ---------------------------------------------------------------------------
# MermaidRenderer
# ---------------------------------------------------------------------------


class TestMermaidRenderer:
    def _renderer(self, mode: str = "online") -> MermaidRenderer:
        config = MermaidConfig(mode=mode, timeout=5)
        return MermaidRenderer(config)

    def test_online_success(self):
        renderer = self._renderer("online")
        with patch.object(renderer._online, "render", return_value=FAKE_PNG):
            result = renderer.render(_diagram("mermaid", "graph TD\nA-->B"))
        assert result.success is True
        assert result.image_data == FAKE_PNG

    def test_local_unavailable_falls_back_to_online(self):
        renderer = self._renderer("local")
        with patch.object(renderer._local, "is_available", return_value=False):
            with patch.object(renderer._online, "render", return_value=FAKE_PNG):
                result = renderer.render(_diagram("mermaid", "graph TD\nA-->B"))
        assert result.success is True

    def test_all_fail_returns_failure_result(self):
        renderer = self._renderer("online")
        with patch.object(renderer._online, "render", side_effect=RuntimeError("fail")):
            with patch.object(renderer._local, "is_available", return_value=False):
                result = renderer.render(_diagram("mermaid", "graph TD\nA-->B"))
        assert result.success is False

