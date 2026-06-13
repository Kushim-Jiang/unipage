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
        self.pdf_progress: float = 0.0
        self.pdf_results: Optional[list] = None

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


# Singleton — import this from anywhere in the backend.
STATE = _AppState()
