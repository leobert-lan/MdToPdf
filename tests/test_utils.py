"""Tests for utility modules: file_utils, logger, temp_manager."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mdtopdf.utils.file_utils import (
    derive_output_path,
    ensure_parent_dir,
    read_text_file,
    validate_input_file,
)
from mdtopdf.utils.logger import get_logger, setup_logger
from mdtopdf.utils.temp_manager import get_temp_dir, get_temp_file


# ---------------------------------------------------------------------------
# file_utils
# ---------------------------------------------------------------------------


class TestValidateInputFile:
    def test_valid_md_file(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Hello")
        validate_input_file(f)  # should not raise

    def test_valid_markdown_file(self, tmp_path):
        f = tmp_path / "doc.markdown"
        f.write_text("# Hello")
        validate_input_file(f)  # should not raise

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_input_file(tmp_path / "nonexistent.md")

    def test_directory_raises(self, tmp_path):
        with pytest.raises(ValueError):
            validate_input_file(tmp_path)

    def test_non_md_extension_warns(self, tmp_path, caplog):
        f = tmp_path / "doc.txt"
        f.write_text("content")
        with caplog.at_level(logging.WARNING):
            validate_input_file(f)
        assert any("markdown" in r.message.lower() or "md" in r.message.lower()
                   for r in caplog.records)


class TestDeriveOutputPath:
    def test_none_uses_same_dir_and_stem(self, tmp_path):
        input_path = tmp_path / "my_doc.md"
        output = derive_output_path(input_path, None)
        assert output.suffix == ".pdf"
        assert output.stem == "my_doc"
        assert output.parent == tmp_path.resolve()

    def test_explicit_output_path_returned(self, tmp_path):
        input_path = tmp_path / "doc.md"
        output_path = tmp_path / "out" / "result.pdf"
        result = derive_output_path(input_path, output_path)
        assert result == output_path.resolve()

    def test_markdown_extension_replaced(self, tmp_path):
        input_path = tmp_path / "doc.markdown"
        output = derive_output_path(input_path, None)
        assert output.suffix == ".pdf"


class TestEnsureParentDir:
    def test_creates_nested_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "c" / "file.pdf"
        ensure_parent_dir(target)
        assert target.parent.exists()

    def test_existing_dir_does_not_raise(self, tmp_path):
        target = tmp_path / "file.pdf"
        ensure_parent_dir(target)  # tmp_path already exists


class TestReadTextFile:
    def test_reads_utf8(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("中文内容", encoding="utf-8")
        assert read_text_file(f) == "中文内容"

    def test_reads_ascii(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("hello world", encoding="utf-8")
        assert read_text_file(f) == "hello world"


# ---------------------------------------------------------------------------
# logger
# ---------------------------------------------------------------------------


class TestLogger:
    def test_setup_returns_logger(self):
        logger = setup_logger(verbose=False)
        assert isinstance(logger, logging.Logger)

    def test_verbose_sets_debug_level(self):
        logger = setup_logger(verbose=True)
        assert logger.level == logging.DEBUG

    def test_non_verbose_sets_info_level(self):
        logger = setup_logger(verbose=False)
        assert logger.level == logging.INFO

    def test_get_logger_namespaced(self):
        logger = get_logger("parser")
        assert "mdtopdf" in logger.name

    def test_get_logger_already_namespaced(self):
        logger = get_logger("mdtopdf.parser")
        assert logger.name == "mdtopdf.parser"


# ---------------------------------------------------------------------------
# temp_manager
# ---------------------------------------------------------------------------


class TestTempManager:
    def test_get_temp_file_returns_path(self):
        path = get_temp_file(suffix=".txt")
        assert isinstance(path, Path)
        assert path.suffix == ".txt"

    def test_temp_file_exists(self):
        path = get_temp_file(suffix=".tmp")
        assert path.exists()

    def test_different_calls_return_different_paths(self):
        p1 = get_temp_file(suffix=".png")
        p2 = get_temp_file(suffix=".png")
        assert p1 != p2

    def test_get_temp_dir_creates_directory(self):
        d = get_temp_dir(prefix="test_")
        assert d.exists()
        assert d.is_dir()

