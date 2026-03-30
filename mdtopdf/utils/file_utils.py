"""File-system utility helpers."""

from __future__ import annotations

from pathlib import Path


_VALID_MD_SUFFIXES = {".md", ".markdown"}


def validate_input_file(path: Path) -> None:
    """Raise ValueError / FileNotFoundError for invalid inputs."""
    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {path}")
    if not path.is_file():
        raise ValueError(f"输入路径不是文件: {path}")
    if path.suffix.lower() not in _VALID_MD_SUFFIXES:
        # Warn but continue — allow .txt etc. treated as Markdown
        import logging

        logging.getLogger("mdtopdf.file_utils").warning(
            "输入文件扩展名非 .md/.markdown，将尝试按 Markdown 格式解析: %s", path
        )


def derive_output_path(input_path: Path, output_path: Path | None = None) -> Path:
    """Return the resolved output PDF path.

    If *output_path* is not given, the PDF sits in the same directory as the
    input file with the same stem and ``.pdf`` suffix.
    """
    if output_path is not None:
        return output_path.resolve()
    return input_path.with_suffix(".pdf").resolve()


def ensure_parent_dir(path: Path) -> None:
    """Create parent directories of *path* if they do not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text_file(path: Path, encoding: str = "utf-8") -> str:
    """Read a text file, falling back to cp1252 on Windows if UTF-8 fails."""
    try:
        return path.read_text(encoding=encoding)
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1252", errors="replace")

