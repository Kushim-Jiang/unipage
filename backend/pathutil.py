"""Filesystem path helpers.

Paths are handled with :mod:`pathlib` throughout the backend; ``os.path`` is
avoided.  Values that cross the JSON/HTTP boundary (project directory, project
file, resource URLs) are stored as POSIX-style strings so that project files
stay portable and diff-stable across platforms.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
"""Repository root -- the directory that contains ``backend/``."""


def as_path(value: Optional[PathLike]) -> Optional[Path]:
    """Return *value* as a :class:`Path`; ``None`` when unset or empty."""
    if value is None or value == "":
        return None
    return value if isinstance(value, Path) else Path(value)


def require_path(value: Optional[PathLike], what: str = "path") -> Path:
    """Like :func:`as_path`, but raise when the value is unset."""
    path = as_path(value)
    if path is None:
        raise ValueError(f"{what} is not set")
    return path


def to_stored(value: PathLike) -> str:
    """Serialise a path for JSON storage (POSIX separators)."""
    return Path(value).as_posix()


def to_str(value: Optional[PathLike]) -> str:
    """Render a path for display/transport ("" when unset)."""
    path = as_path(value)
    return "" if path is None else str(path)


def same_path(first: Optional[PathLike], second: Optional[PathLike]) -> bool:
    """Return True when both arguments denote the same location.

    Tolerates separator style, relative vs absolute spellings, ``..``
    segments and -- on Windows -- letter case.
    """
    left, right = as_path(first), as_path(second)
    if left is None or right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:  # pragma: no cover - exotic/unreadable paths
        return left.absolute() == right.absolute()
