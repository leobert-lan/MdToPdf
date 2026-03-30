"""Tests for config loader and AppConfig models."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mdtopdf.config.config_loader import load_config
from mdtopdf.config.models import AppConfig


# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------


class TestDefaultConfig:
    def test_returns_appconfig_instance(self):
        config = load_config()
        assert isinstance(config, AppConfig)

    def test_default_page_size_is_a4(self):
        config = load_config()
        assert config.page.size == "A4"

    def test_default_plantuml_mode_local(self):
        config = load_config()
        assert config.plantuml.mode == "local"

    def test_default_mermaid_mode_local(self):
        config = load_config()
        assert config.mermaid.mode == "local"

    def test_default_title_empty(self):
        config = load_config()
        assert config.title == ""

    def test_preview_disabled_by_default(self):
        config = load_config()
        assert config.preview is False


# ---------------------------------------------------------------------------
# Front Matter overrides
# ---------------------------------------------------------------------------


class TestFrontMatterOverrides:
    def test_title_from_front_matter(self):
        config = load_config(front_matter={"title": "我的文档"})
        assert config.title == "我的文档"

    def test_author_from_front_matter(self):
        config = load_config(front_matter={"author": "张三"})
        assert config.author == "张三"

    def test_plantuml_mode_from_front_matter(self):
        config = load_config(front_matter={"plantuml_mode": "online"})
        assert config.plantuml.mode == "online"

    def test_mermaid_mode_from_front_matter(self):
        config = load_config(front_matter={"mermaid_mode": "online"})
        assert config.mermaid.mode == "online"


# ---------------------------------------------------------------------------
# CLI args overrides
# ---------------------------------------------------------------------------


class TestCLIArgsOverrides:
    def test_plantuml_mode_cli_override(self):
        config = load_config(cli_args={"plantuml_mode": "online"})
        assert config.plantuml.mode == "online"

    def test_mermaid_mode_cli_override(self):
        config = load_config(cli_args={"mermaid_mode": "online"})
        assert config.mermaid.mode == "online"

    def test_plantuml_jar_cli_override(self):
        config = load_config(cli_args={"plantuml_jar_path": "/opt/plantuml.jar"})
        assert config.plantuml.jar_path == "/opt/plantuml.jar"

    def test_custom_css_cli_override(self):
        config = load_config(cli_args={"custom_css": "/my/style.css"})
        assert config.style.custom_css == "/my/style.css"


# ---------------------------------------------------------------------------
# Priority: CLI > Front Matter > file
# ---------------------------------------------------------------------------


class TestConfigPriority:
    def test_cli_overrides_front_matter(self):
        config = load_config(
            front_matter={"plantuml_mode": "online"},
            cli_args={"plantuml_mode": "local"},
        )
        assert config.plantuml.mode == "local"

    def test_cli_title_overrides_front_matter(self):
        config = load_config(
            front_matter={"title": "FM Title"},
            cli_args={"title": "CLI Title"},
        )
        assert config.title == "CLI Title"


# ---------------------------------------------------------------------------
# External config file
# ---------------------------------------------------------------------------


class TestExternalConfigFile:
    def test_extra_config_loaded(self, tmp_path):
        cfg = tmp_path / "my_config.yaml"
        cfg.write_text(
            yaml.dump({"plantuml": {"mode": "online"}}), encoding="utf-8"
        )
        config = load_config(extra_config_path=cfg)
        assert config.plantuml.mode == "online"

    def test_missing_extra_config_does_not_crash(self, tmp_path):
        missing = tmp_path / "nonexistent.yaml"
        config = load_config(extra_config_path=missing)
        assert isinstance(config, AppConfig)

    def test_malformed_extra_config_falls_back_to_default(self, tmp_path):
        bad_cfg = tmp_path / "bad.yaml"
        bad_cfg.write_text("{invalid yaml: [}", encoding="utf-8")
        # Should not raise; falls back to defaults
        config = load_config(extra_config_path=bad_cfg)
        assert isinstance(config, AppConfig)

