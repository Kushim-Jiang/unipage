"""Validation helpers — bug labels, status tracking, and summary."""

from __future__ import annotations

from backend.models.dataclasses import BugEntry

_BUG_LABELS: dict[str, str] = {
    "C000": "Unknown error.",
    "C001": "Block file format error.",
    "C002": "Invalid RS expression.",
    "C003": "Block name is empty.",
    "C004": "Block type is empty.",
    "C005": "Block range is invalid.",
    "C006": "Project file format error.",
    "C007": "No font selected.",
    "C008": "Missing glyph.",
    "C009": "Font does not exist.",
    "J001": "Block range start mod 16 is not 0, violating Unicode Standard Conformance D10b.",
    "J002": "Block range end mod 16 is not 15, violating Unicode Standard Conformance D10b.",
    "J003": "Character outside block range.",
    "J004": "Radical does not exist.",
}


def bug_label(code: str) -> str:
    """Return the human-readable label for a bug code."""
    return _BUG_LABELS.get(code, "Unknown code.")


def split_bugs(bugs: list[BugEntry]) -> tuple[list[BugEntry], list[BugEntry], list[BugEntry]]:
    """Split a flat bug list into (errors, warnings, infos)."""
    errors = [b for b in bugs if b.severity == 0]
    warnings = [b for b in bugs if b.severity == 1]
    infos = [b for b in bugs if b.severity == 2]
    return errors, warnings, infos


def bug_summary(bugs: list[BugEntry]) -> dict:
    """Return a structured summary of all bugs."""
    errors, warnings, infos = split_bugs(bugs)
    return {
        "errors": [
            {"code": b.code, "label": bug_label(b.code), "file": b.filename, "detail": b.detail} for b in errors
        ],
        "warnings": [
            {"code": b.code, "label": bug_label(b.code), "file": b.filename, "detail": b.detail} for b in warnings
        ],
        "infos": [{"code": b.code, "label": bug_label(b.code), "file": b.filename, "detail": b.detail} for b in infos],
        "counts": {"errors": len(errors), "warnings": len(warnings), "infos": len(infos)},
    }


def has_errors(bugs: list[BugEntry]) -> bool:
    return any(b.severity == 0 for b in bugs)
