"""Application state — a singleton holding the active project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from backend.models.project import Project


class _AppState:
    """Thread-safe-ish global state for the Unipage backend.

    Holds one active project at a time.  All mutations go through
    the API routes, so no locking is needed for the common case.
    """

    def __init__(self) -> None:
        self._project: Optional[Project] = None
        self._proofs: list = []  # list[ProofLayout]
        # PDF generation progress
        self.pdf_progress: float = 0.0
        self.pdf_results: Optional[list] = None
        # Background parse progress
        self.parse_progress: float = 0.0
        self.parse_done: bool = False
        self.parse_bugs: Optional[dict] = None
        # Background check-all progress
        self.check_progress: float = 0.0
        self.check_done: bool = False
        self.check_bugs: Optional[dict] = None

    # ── project ──────────────────────────────────────────────────

    @property
    def project(self) -> Optional[Project]:
        return self._project

    @project.setter
    def project(self, value: Optional[Project]) -> None:
        self._project = value

    @property
    def has_project(self) -> bool:
        return self._project is not None

    # ── proofs (cached output of make_proof, consumed by make_pdf) ─

    @property
    def proofs(self) -> list[dict]:
        return self._proofs

    @proofs.setter
    def proofs(self, value: list[dict]) -> None:
        self._proofs = value

    def clear_proofs(self) -> None:
        self._proofs = []

    # ── helpers ──────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear everything (close project)."""
        self._project = None
        self._proofs = []
        self.pdf_progress = 0.0
        self.pdf_results = None
        self.parse_progress = 0.0
        self.parse_done = False
        self.parse_bugs = None
        self.check_progress = 0.0
        self.check_done = False
        self.check_bugs = None


# Singleton — import this from anywhere in the backend.
STATE = _AppState()
