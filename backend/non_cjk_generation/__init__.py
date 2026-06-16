"""
non_cjk_generation -- Unicode Code Chart PDF Generator
=====================================================

Produces print-ready Unicode code chart PDFs from structured data.

Inputs:
  1. Unified ``.tsv`` data file  — contains NL (NamesList), FT (font table),
     and optionally CD (character data) sections
  2. Font files (``.ttf`` / ``.otf``) — glyphs for rendering, placed in
     ``data/fonts/`` or the project directory

Pipeline:
  Parse → Layout → Render

Usage::

    from backend.non_cjk_generation import generate_page_structure, render_pdf

    pages = generate_page_structure(
        cfl_path="data.tsv",
        nameslist_path="data.tsv",
        font_dir=".",
    )
    render_pdf(pages, "output.pdf", font_dir=".", extra_font_dirs=["data/fonts/"])
"""

from backend.non_cjk_generation.layout import (
    ChartPageBuilder,
    InfoPageBuilder,
    compute_code_chart_pages,
    compute_info_pages,
    compute_title_page,
    generate_page_structure,
)
from backend.non_cjk_generation.models import (
    BlockInfo,
    Drawing,
    DrawingItem,
    FontConfig,
    FontMetrics,
    GridConfig,
    InfoConfig,
    LayoutContext,
    NamesListEntry,
    Page,
    PageStructure,
    PageType,
    TextSpan,
    measure_text,
    measure_text_precise,
    wrap_text,
)
from backend.non_cjk_generation.parsers import (
    detect_block_from_nameslist,
    extract_block_entries,
    find_font_for_codepoint,
    find_font_for_range,
    parse_cfl,
    parse_nameslist,
)
from backend.non_cjk_generation.renderer import ReservedCellHatcher, register_fonts, render_pdf

__all__ = [
    # models
    "BlockInfo",
    "Drawing",
    "DrawingItem",
    "FontConfig",
    "FontMetrics",
    "GridConfig",
    "InfoConfig",
    "LayoutContext",
    "NamesListEntry",
    "Page",
    "PageStructure",
    "PageType",
    "TextSpan",
    "measure_text",
    "measure_text_precise",
    "wrap_text",
    # parsers
    "detect_block_from_nameslist",
    "extract_block_entries",
    "find_font_for_codepoint",
    "find_font_for_range",
    "parse_cfl",
    "parse_nameslist",
    # layout
    "ChartPageBuilder",
    "InfoPageBuilder",
    "compute_code_chart_pages",
    "compute_info_pages",
    "compute_title_page",
    "generate_page_structure",
    # renderer
    "ReservedCellHatcher",
    "register_fonts",
    "render_pdf",
]

__version__ = "1.0.0"
