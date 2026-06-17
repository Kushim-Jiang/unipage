"""Font management for chart generation — fpdf2 backend.

Centralizes font-name constants and the fpdf2 font‑family mapping.
"""

from __future__ import annotations

from fpdf import FPDF

# -- Font name constants --------------------------------------------

OpenSans_Bold = "OpenSans-Bold"
OpenSans_Italic = "OpenSans-Italic"
LiberationSans_Regular = "LiberationSans-Regular"
LiberationSans_Bold = "LiberationSans-Bold"
LiberationSansNarrow_Regular = "LiberationSansNarrow-Regular"
LiberationSerif_Regular = "LiberationSerif-Regular"
CJKRadicals = "CJKRadicals"

# -- fpdf2 (family, style) mapping ----------------------------------

FONT_MAP = {
    OpenSans_Bold: ("OpenSans", "B"),
    OpenSans_Italic: ("OpenSans", "I"),
    LiberationSans_Regular: ("LiberationSans", ""),
    LiberationSans_Bold: ("LiberationSans", "B"),
    LiberationSansNarrow_Regular: ("LiberationSansNarrow", ""),
    LiberationSerif_Regular: ("LiberationSerif", ""),
    CJKRadicals: ("CJKRadicals", ""),
}

_FALLBACK = ("LiberationSans", "")


def use_font(pdf: FPDF, font_name: str, size: float) -> None:
    """Set the current font on *pdf*, falling back to LiberationSans."""
    family, style = FONT_MAP.get(font_name, _FALLBACK)
    try:
        pdf.set_font(family, style, size)
    except Exception:
        pdf.set_font(*_FALLBACK, size)
