"""Shared dataclass definitions for the Unipage backend.

Replaces raw dicts/lists with typed data classes so that
type checkers (mypy, pyright, ruff) and editors can provide
better validation and autocompletion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# -- Bug / diagnostic entry ------------------------------------------


@dataclass
class BugEntry:
    """A single diagnostic message produced during parsing or validation.

    Attributes:
        severity: 0 = error, 1 = warning, 2 = info.
        code: Short code like ``"C001"``, ``"J003"``.
        filename: Basename of the source file.
        detail: Human-readable detail string.
    """

    severity: int
    code: str
    filename: str
    detail: str = ""

    def to_list(self) -> list:
        """Return the legacy ``[severity, code, filename, detail]`` form."""
        return [self.severity, self.code, self.filename, self.detail]

    @classmethod
    def from_list(cls, raw: list) -> BugEntry:
        """Create from legacy ``[severity, code, filename, detail]`` list."""
        return cls(severity=raw[0], code=raw[1], filename=raw[2], detail=raw[3] if len(raw) > 3 else "")


# -- Resource entry --------------------------------------------------


@dataclass
class ResourceEntry:
    """A single resource file registered in the project.

    Attributes:
        basename: File name (no directory).
        check_status: 0 = uncompiled, 1 = compile_failed, 2 = compiled_ok.
        url: Absolute path to the file.
        parse_data: Parsed content (set when check_status == 2).
    """

    basename: str
    check_status: int  # 0=uncompiled, 1=compile_failed, 2=compiled_ok
    url: str
    parse_data: Any = None  # list[dict] for blocks/attributes, varies by type

    def to_list(self) -> list:
        """Return the legacy ``[basename, check_status, url, parse_data]`` form."""
        return [self.basename, self.check_status, self.url, self.parse_data]

    @classmethod
    def from_list(cls, raw: list) -> ResourceEntry:
        """Create from legacy ``[basename, check_status, url, parse_data]`` list."""
        return cls(
            basename=raw[0],
            check_status=raw[1],
            url=raw[2],
            parse_data=raw[3] if len(raw) > 3 else None,
        )


# -- Block info ------------------------------------------------------


@dataclass
class BlockInfo:
    """Parsed definition of a single Unicode block.

    Attributes:
        name: Block name (e.g. ``"CJK Unified Ideographs"``).
        type: Block type -- ``"RF-W"``, ``"RF-H"``, ``"RF-V"``, ``"RS-W"``,
            ``"RS-H"``, or ``"NL"`` (NamesList).
        start_cp: First codepoint (inclusive).
        end_cp: Last codepoint (inclusive).
        content: Inner data dict.  Structure varies by block type.
    """

    name: str
    type: str
    start_cp: int
    end_cp: int
    content: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return dict suitable for JSON serialisation."""
        return {
            "name": self.name,
            "type": self.type,
            "start_cp": self.start_cp,
            "end_cp": self.end_cp,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> BlockInfo:
        """Create from a dict, supporting both old and new key names."""
        return cls(
            name=raw.get("name") or raw.get("blk_name", ""),
            type=raw.get("type") or raw.get("blk_type", ""),
            start_cp=raw.get("start_cp") or raw.get("blk_initcp", 0),
            end_cp=raw.get("end_cp") or raw.get("blk_finacp", 0),
            content=raw.get("content") or raw.get("blk_cont", {}),
        )


# -- Block setting ---------------------------------------------------


@dataclass
class BlockSetting:
    """Print settings for a single block.

    Attributes:
        name: Block name (matches ``BlockInfo.name``).
        type: Block type.
        start_cp: First codepoint.
        end_cp: Last codepoint.
        content: Settings dict with keys like ``print``, ``column``,
            ``format``, ``title``, ``font``, ``yellow``, ``blue``.
    """

    name: str
    type: str
    start_cp: int
    end_cp: int
    content: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "start_cp": self.start_cp,
            "end_cp": self.end_cp,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> BlockSetting:
        """Create from a dict, supporting both old and new key names."""
        return cls(
            name=raw.get("name") or raw.get("blk_name", ""),
            type=raw.get("type") or raw.get("blk_type", ""),
            start_cp=raw.get("start_cp") or raw.get("blk_initcp", 0),
            end_cp=raw.get("end_cp") or raw.get("blk_finacp", 0),
            content=raw.get("content") or raw.get("blk_cont", {}),
        )


# -- Proof layout ----------------------------------------------------


@dataclass
class ProofLayout:
    """Layout data for one block, ready for PDF generation.

    This is the output of ``layout.make_proof`` and input to
    ``pdf_builder.generate_pdf``.
    """

    name: str
    start_cp: int
    end_cp: int
    page_title: bool
    print_pages: list
    page_class: tuple
    char_count: int
    glyph_dict: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "start_cp": self.start_cp,
            "end_cp": self.end_cp,
            "page_title": self.page_title,
            "print_pages": self.print_pages,
            "page_class": self.page_class,
            "char_count": self.char_count,
        }
        if self.glyph_dict is not None:
            d["glyph_dict"] = self.glyph_dict
        return d


# -- Project info ----------------------------------------------------


@dataclass
class ProjectInfo:
    """Basic identifying info for a Unipage project."""

    project_name: str = ""
    project_dir: str = ""
    project_file: str = ""

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "project_dir": self.project_dir,
            "project_file": self.project_file,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> ProjectInfo:
        return cls(
            project_name=raw.get("project_name", ""),
            project_dir=raw.get("project_dir", ""),
            project_file=raw.get("project_file", ""),
        )


# -- Resource collection ---------------------------------------------


@dataclass
class ResourceCollection:
    """Typed container for all resource file lists in a project."""

    project: list[ResourceEntry] = field(default_factory=list)
    font: list[ResourceEntry] = field(default_factory=list)
    data: list[ResourceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, list]:
        return {
            "project": resource_list_to_raw(self.project),
            "font": resource_list_to_raw(self.font),
            "data": resource_list_to_raw(self.data),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> ResourceCollection:
        """Create from a dict."""
        return cls(
            project=resource_list_from_raw(raw.get("project", [])),
            font=resource_list_from_raw(raw.get("font", [])),
            data=resource_list_from_raw(raw.get("data", [])),
        )

    def all(self) -> list[ResourceEntry]:
        """Return every resource entry across all categories."""
        return self.project + self.font + self.data


# -- Helper: resource list conversion --------------------------------


def resource_list_from_raw(raw_list: list) -> list[ResourceEntry]:
    """Convert a list of legacy ``[basename, status, url, parse]`` lists
    to ``list[ResourceEntry]``."""
    return [ResourceEntry.from_list(r) for r in raw_list]


def resource_list_to_raw(entries: list[ResourceEntry]) -> list:
    """Convert ``list[ResourceEntry]`` back to legacy list-of-lists."""
    return [e.to_list() for e in entries]
