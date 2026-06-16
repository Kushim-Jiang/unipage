"""
Data types, geometry constants, and font measurement utilities
for Unicode code chart PDF generation.

All coordinates are in PDF points (1/72 inch), origin at bottom-left.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from os.path import exists
from typing import Optional

# ==================================================================->
#  Page geometry
# ==================================================================->

PAGE_W = 612.0
PAGE_H = 792.0

BLOCK_LEFT = 82.80
BLOCK_RIGHT = 529.20
BLOCK_UP = 76.74
BLOCK_DOWN = 733.08
BLOCK_WIDTH = BLOCK_RIGHT - BLOCK_LEFT
BLOCK_HEIGHT = BLOCK_DOWN - BLOCK_UP

FORMAT_SHIFT = 15.96


class PageType(Enum):
    LEFT = "Left"
    RIGHT = "Right"
    CENTER = "Center"


def shift_x(x: float, page_type: PageType) -> float:
    if page_type == PageType.LEFT:
        return x - FORMAT_SHIFT
    if page_type == PageType.RIGHT:
        return x + FORMAT_SHIFT
    return x


# ==================================================================->
#  Data types
# ==================================================================->


@dataclass
class TextSpan:
    """A single contiguous run of text with uniform formatting."""

    text: str
    font: str
    size: float
    color: int = 0
    bbox: list[float] = field(default_factory=lambda: [0, 0, 0, 0])
    origin: list[float] = field(default_factory=lambda: [0, 0])

    @classmethod
    def make(
        cls,
        text: str,
        font: str,
        size: float,
        x: float,
        y: float,
        color: int = 0,
        font_metrics: "FontMetrics | None" = None,
    ) -> "TextSpan":
        """Factory: construct a TextSpan with auto-computed bbox.

        If *font_metrics* is provided, uses it for precise width measurement.
        Otherwise falls back to heuristic measure_text.
        """
        if not text or text == " ":
            width = 0.0
        elif font_metrics is not None:
            width = font_metrics.measure(font, size, text)
        else:
            from backend.non_cjk_generation.models import measure_text

            width = measure_text(font, size, text)
        return cls(
            text=text,
            font=font,
            size=size,
            color=color,
            bbox=[x, y - size * 0.8, x + width, y + size * 0.2],
            origin=[x, y],
        )

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "font": self.font,
            "size": self.size,
            "color": self.color,
            "bbox": self.bbox,
            "origin": self.origin,
        }


@dataclass
class DrawingItem:
    """A single drawing operation."""

    op: str  # "re" = rectangle, "l" = line
    x: float
    y: float
    w: float = 0
    h: float = 0

    def to_dict(self) -> dict:
        if self.op == "l":
            return {"op": "l", "x1": self.x, "y1": self.y, "x2": self.w, "y2": self.h}
        if self.op == "re":
            return {"op": "re", "x": self.x, "y": self.y, "w": self.w, "h": self.h}
        return {"op": self.op, "x": self.x, "y": self.y}


@dataclass
class Drawing:
    """A group of drawing operations sharing fill/stroke attributes."""

    fill: Optional[list[float]] = None
    color: Optional[list[float]] = None
    width: float = 0
    items: list[DrawingItem] = field(default_factory=list)

    @classmethod
    def rect(cls, x: float, y: float, w: float, h: float) -> "Drawing":
        """Factory: a filled white rectangle (background)."""
        return cls(
            fill=[1.0, 1.0, 1.0],
            color=None,
            width=0,
            items=[DrawingItem(op="re", x=x, y=y, w=w, h=h)],
        )

    @classmethod
    def line(cls, x1: float, y1: float, x2: float, y2: float, width: float) -> "Drawing":
        """Factory: a black stroke line."""
        return cls(
            fill=None,
            color=[0, 0, 0],
            width=width,
            items=[DrawingItem(op="l", x=x1, y=y1, w=x2, h=y2)],
        )

    def to_dict(self) -> dict:
        return {
            "fill": self.fill,
            "color": self.color,
            "width": self.width,
            "items": [it.to_dict() for it in self.items],
        }


@dataclass
class Page:
    """A single page in the output structure."""

    page_num: int
    text_spans: list[TextSpan] = field(default_factory=list)
    drawings: list[Drawing] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "page_num": self.page_num,
            "text_spans": [ts.to_dict() for ts in self.text_spans],
            "drawings": [d.to_dict() for d in self.drawings],
        }


@dataclass
class PageStructure:
    """Complete page structure output."""

    pages: list[Page] = field(default_factory=list)

    def to_list(self) -> list[dict]:
        return [p.to_dict() for p in self.pages]


@dataclass
class BlockInfo:
    """Information about a Unicode block being laid out."""

    name: str
    start_cp: int
    end_cp: int
    column_count: int = 24
    char_count: int = 16
    grid_left: float | None = None  # override auto-centering; None = auto


@dataclass
class FontConfig:
    """Font configuration for a codepoint or range from CFL.

    Attributes
    ----------
    font_name: Font file/display name.
    size: Font size in points.
    offset: Codepoint offset for glyph lookup (Q value).
    range_start / range_end: Covered codepoint range (inclusive).
    excludes: List of (start, end) ranges excluded from this font (/X=).
    min_size: Minimum font size for nameslist rendering (/M=).
    """

    font_name: str
    size: float = 22
    offset: int = 0
    range_start: int = 0
    range_end: int = 0x10FFFF
    excludes: list = field(default_factory=list)
    min_size: int = 0


@dataclass
class NamesListEntry:
    """A single entry in a Unicode NamesList file.

    The ``type`` field discriminates the entry kind (see NamesList spec):
      - "block_header":   @@ block header line
      - "name":           character name line (CHAR TAB NAME)
      - "reserved":       reserved character line (CHAR TAB <reserved>)
      - "alias":          alias line (TAB = SP LINE)
      - "formal_alias":   formal alias line (TAB % SP NAME)
      - "cross_ref":      cross-reference line (TAB x SP ...)
      - "variation":      variation sequence line (TAB ~ SP ...)
      - "decomposition":  decomposition mapping (TAB : SP ...)
      - "compat_mapping": compatibility mapping (TAB # SP ...)
      - "comment":        bullet comment (TAB * SP ...) or unmarked comment
      - "notice":         @+ notice line
      - "sidebar":        ;; marginal sidebar line
      - "subheader":      @ section subheader
      - "title":          @@@ title line (page header)
      - "subtitle":       @@@+ subtitle line
      - "variation_subheader":  @~ variation summary subheader
      - "altglyph_subheader":   @@~ alternate glyph summary subheader
      - "mixed_subheader":      @@@~ combined summary subheader
      - "page_break":     @@ standalone page/column break
      - "index_tab":      @@+ index tab marker
      - "file_comment":   ; comment line
      - "ignored":        TAB ; ignored line
      - "empty":          blank line
    """

    type: str = ""
    codepoint: str = ""  # hex codepoint (for name/reserved/cross_ref lines)
    name: str = ""  # character name or LCNAME
    text: str = ""  # general text content (subheaders, notices, comments, etc.)
    block_name: str = ""  # block name (for block_header)
    block_start: str = ""  # block start CP (for block_header)
    block_end: str = ""  # block end CP (for block_header)
    alt_label: str = ""  # alternate ISO label (for block_header)
    target_cp: str = ""  # cross-ref target codepoint
    target_name: str = ""  # cross-ref target name
    var_selector: str = ""  # variation selector (for variation lines)
    var_label: str = ""  # variation label
    var_tag: str = ""  # variation context tag
    mapping_tag: str = ""  # decomposition/compat mapping tag (e.g. "<font>")
    mapping_text: str = ""  # decomposition/compat mapping text
    annotations: list["NamesListEntry"] = field(default_factory=list)
    """Child annotations attached to a name/reserved line."""


@dataclass
class LayoutContext:
    """Context passed through all layout computation stages."""

    version: str = "17.0.0"
    short_version: str = "17.0"
    short_version_label: str = "17.0"
    year: str = "2025"
    block: Optional[BlockInfo] = None
    cfl_config: list[FontConfig] = field(default_factory=list)
    nameslist: list[NamesListEntry] = field(default_factory=list)
    font_dir: str = ""
    extra_font_dirs: list[str] = field(default_factory=list)
    title_md_path: str = ""
    chart_page_base: int = 1
    assigned_cps: set[int] | None = None
    combining_cps: set[int] | None = None


@dataclass
class TitlePageConfig:
    """Layout parameters for the title/front-matter page.

    All positions are in points from the page top-left origin.
    Fonts are (family, size) tuples matched against the renderer's font map.
    """

    # -- Block name & range ----------------------------------
    margin_left: float = 82.80  # left margin for all title text
    block_name_y: float = 87.30  # y-origin of block name line
    block_name_font: tuple = ("OpenSans-Bold", 11.0)
    range_y: float = 100.08  # y-origin of "Range: XXXX-YYYY" line
    range_font: tuple = ("LiberationSans-Bold", 9.0)

    # -- Body text -------------------------------------------
    body_start_y: float = 111.18  # y-origin of first body text line
    body_font: tuple = ("LiberationSans-Regular", 9.0)
    bold_font: tuple = ("LiberationSans-Bold", 9.0)
    italic_font: tuple = ("LiberationSans-Italic", 9.0)
    space_font: tuple = ("LiberationSans-Regular", 9.0)
    max_width: float = 540.0  # word-wrap width for body text

    # -- Vertical spacing between elements -------------------
    body_leading: float = 9.00  # same-font continuation
    body_to_italic: float = 9.60  # body ->italic (no blank line)
    body_to_space: float = 9.48  # body ->blank line
    space_to_body: float = 9.72  # blank line ->body text
    space_to_italic: float = 9.60  # blank line ->italic
    italic_to_space: float = 11.16  # italic ->blank line
    space_to_heading: float = 13.02  # blank line ->heading
    heading_to_body: float = 12.90  # heading ->body text


# ==================================================================->
#  Chart grid & info section layout constants
# ==================================================================->


@dataclass
class GridConfig:
    """Constants for code chart grid layout.

    All values in PDF points.  These match the Unicode Standard reference.
    """

    cell_w: float = 31.65
    cell_row_h: float = 39.6
    col_header_y: float = 86.4
    first_glyph_y: float = 118.1
    label_offset_y: float = 12.3
    row_idx_x: float = 105.4
    col1_x: float = 123.50
    grid_left: float = 116.10
    grid_top: float = 92.88
    header_y: float = 44.48
    footer_y: float = 748.77
    thick_border: float = 1.5
    thin_border: float = 0.25
    thick_extend: float = 14.9

    # Right-edge positions for right-aligned elements
    chart_header_right: float = 528.7
    chart_footer_right: float = 529.4
    info_header_right: float = 528.9
    info_footer_right: float = 529.4

    @property
    def num_rows(self) -> int:
        return 16

    def center_grid_left(self, num_cols: int, page_w: float = PAGE_W) -> float:
        return (page_w - num_cols * self.cell_w) / 2


@dataclass
class InfoConfig:
    """Constants for information section (two-column nameslist) layout."""

    col1_cp_x: float = 82.80
    col1_glyph_x: float = 110.10
    col1_name_x: float = 126.00
    col2_cp_x: float = 310.00
    col2_glyph_x: float = 336.52
    col2_name_x: float = 353.20
    line_h: float = 10.6
    first_y: float = 84.60
    glyph_y_adjust: float = +0.36
    gap_after_blockanno: float = 15.2
    gap_after_section: float = 12.5
    gap_after_regular: float = 10.59
    col_switch_y: float = 728.17

    @property
    def col1_max_w(self) -> float:
        return self.col1_right - self.col1_name_x

    @property
    def col2_max_w(self) -> float:
        return self.col2_right - self.col2_name_x

    @property
    def col1_text_left(self) -> float:
        return self.col1_name_x

    @property
    def col2_text_left(self) -> float:
        return self.col2_name_x

    @property
    def col1_text_right(self) -> float:
        return self.col1_text_left + 180.0

    @property
    def col2_text_right(self) -> float:
        return self.col2_text_left + 180.0

    @property
    def col1_right(self) -> float:
        return self.col1_text_right

    @property
    def col2_right(self) -> float:
        return self.col2_text_right

    @property
    def col1_glyph_col_w(self) -> float:
        return self.col1_name_x - self.col1_glyph_x

    @property
    def col2_glyph_col_w(self) -> float:
        return self.col2_name_x - self.col2_glyph_x

    def column_params(self, is_col2: bool) -> dict:
        """Return (cp_x, glyph_x, name_x, max_w, glyph_col_w, right) for a column."""
        if is_col2:
            return {
                "cp_x": self.col2_cp_x,
                "glyph_x": self.col2_glyph_x,
                "name_x": self.col2_name_x,
                "max_w": self.col2_max_w,
                "glyph_col_w": self.col2_glyph_col_w,
                "right": self.col2_right,
            }
        return {
            "cp_x": self.col1_cp_x,
            "glyph_x": self.col1_glyph_x,
            "name_x": self.col1_name_x,
            "max_w": self.col1_max_w,
            "glyph_col_w": self.col1_glyph_col_w,
            "right": self.col1_right,
        }


# ==================================================================->
#  Font measurement (heuristic + precise via fontTools)
# ==================================================================->

_FONT_WIDTH_FACTORS: dict[str, float] = {
    "OpenSans-Light": 0.50,
    "OpenSans-Regular": 0.52,
    "OpenSans-Bold": 0.55,
    "OpenSans-Italic": 0.50,
    "LiberationSans-Regular": 0.56,
    "LiberationSans-Bold": 0.58,
    "LiberationSans-Italic": 0.52,
    "LiberationSansNarrow-Regular": 0.45,
    "LiberationSerif-Regular": 0.50,
}


_font_cache: dict[str, dict] = {}


def measure_text(font_name: str, font_size: float, text: str) -> float:
    """Estimate width of a text string in points (heuristic)."""
    if not text:
        return 0.0
    factor = _FONT_WIDTH_FACTORS.get(font_name, 0.52)
    return len(text) * font_size * factor


def measure_text_precise(
    font_name: str,
    font_size: float,
    text: str,
    font_path: Optional[str] = None,
) -> float:
    """Measure text width precisely using fontTools if available."""
    if not text:
        return 0.0
    if font_path and exists(font_path):
        try:
            from fontTools.ttLib import TTFont

            if font_path not in _font_cache:
                font = TTFont(font_path)
                cmap = font.getBestCmap()
                hmtx = font["hmtx"]
                upem = font["head"].unitsPerEm
                _font_cache[font_path] = {"cmap": cmap, "hmtx": hmtx, "upem": upem}
            cached = _font_cache[font_path]
            total = 0.0
            scale = font_size / cached["upem"]
            for ch in text:
                gn = cached["cmap"].get(ord(ch), ".notdef")
                w, _ = cached["hmtx"].get(gn, (0, 0))
                total += w * scale
            return total
        except Exception:
            pass
    return measure_text(font_name, font_size, text)


def measure_glyph_visual_center(
    font_name: str,
    font_size: float,
    char: str,
    font_path: Optional[str] = None,
) -> float:
    """Return the horizontal offset from glyph origin to the visual center.

    The visual center is (xMin + xMax) / 2 in font units, scaled to points.
    A positive return means the visual center is to the RIGHT of the origin.
    """
    if not char or not font_path or not exists(font_path):
        return measure_text_precise(font_name, font_size, char, font_path) / 2
    try:
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.ttLib import TTFont

        font = TTFont(font_path)
        cmap = font.getBestCmap()
        gn = cmap.get(ord(char), ".notdef")
        gs = font.getGlyphSet()
        if gn not in gs:
            return measure_text_precise(font_name, font_size, char, font_path) / 2
        bp = BoundsPen(gs)
        gs[gn].draw(bp)
        if bp.bounds:
            xMin, _yMin, xMax, _yMax = bp.bounds
            upem = font["head"].unitsPerEm
            scale = font_size / upem
            return (xMin + xMax) / 2 * scale
    except Exception:
        pass
    return measure_text_precise(font_name, font_size, char, font_path) / 2


def wrap_text(
    font_name: str,
    font_size: float,
    text: str,
    max_width: float,
    font_path: Optional[str] = None,
) -> list[str]:
    """Greedy word-wrap to fit within max_width."""
    words = text.split(" ")
    lines: list[str] = []
    current_line: list[str] = []
    current_width = 0.0
    space_width = measure_text_precise(font_name, font_size, " ", font_path)

    for word in words:
        word_width = measure_text_precise(font_name, font_size, word, font_path)
        sep_width = space_width if current_line else 0.0
        if current_width + sep_width + word_width <= max_width:
            current_line.append(word)
            current_width += sep_width + word_width
        else:
            if current_line:
                lines.append(" ".join(current_line))
            if word_width > max_width:
                char_lines = _break_long_word(font_name, font_size, word, max_width, font_path)
                if char_lines:
                    lines.extend(char_lines[:-1])
                    current_line = [char_lines[-1]]
                    current_width = measure_text_precise(font_name, font_size, char_lines[-1], font_path)
                else:
                    current_line = [word]
                    current_width = word_width
            else:
                current_line = [word]
                current_width = word_width

    if current_line:
        lines.append(" ".join(current_line))
    return lines if lines else [text]


def _break_long_word(
    font_name: str, font_size: float, word: str, max_width: float, font_path: Optional[str] = None
) -> list[str]:
    lines: list[str] = []
    current = ""
    current_width = 0.0
    for ch in word:
        ch_width = measure_text_precise(font_name, font_size, ch, font_path)
        if current_width + ch_width > max_width and current:
            lines.append(current)
            current = ch
            current_width = ch_width
        else:
            current += ch
            current_width += ch_width
    if current:
        lines.append(current)
    return lines


def get_line_height(font_size: float, leading_factor: float = 1.2) -> float:
    return font_size * leading_factor


# ==================================================================->
#  FontMetrics ->unified font measurement service
# ==================================================================->


class FontMetrics:
    """Unified font measurement service.

    Combines heuristic and precise (fontTools) text measurement,
    glyph visual-center calculation, and word-wrapping into a single
    stateful object with a configurable font directory for path resolution.

    Usage::

        fm = FontMetrics(font_dir="data/fonts/")
        w = fm.measure("LiberationSans-Regular", 10, "Hello")
        center = fm.glyph_visual_center("OpenSans-Bold", 22, "A")
    """

    def __init__(self, font_dir: str = "", extra_dirs: list[str] | None = None):
        self._font_dir: str = font_dir
        self._extra_dirs: list[str] = extra_dirs or []
        self._font_path_cache: dict[str, str | None] = {}
        self._font_data_cache: dict[str, dict] = {}

    # -- Font file path resolution --------------------------

    def resolve_font_path(self, font_name: str) -> str | None:
        """Return the absolute path to a .ttf/.otf file for *font_name*.

        Searches *font_dir* first, then each directory in *extra_dirs*.
        """
        if font_name in self._font_path_cache:
            return self._font_path_cache[font_name]
        from pathlib import Path

        search_dirs = [Path(self._font_dir)] if self._font_dir else []
        search_dirs += [Path(d) for d in self._extra_dirs]
        for base in search_dirs:
            for ext in (".ttf", ".otf"):
                p = base / (font_name + ext)
                if p.exists():
                    result = str(p)
                    break
            else:
                continue
            self._font_path_cache[font_name] = result
            return result
        self._font_path_cache[font_name] = None
        return None

    # -- Measurement ----------------------------------------

    def measure(self, font_name: str, font_size: float, text: str, font_path: str | None = None) -> float:
        """Measure text width: precise via fontTools if available, else heuristic."""
        if not text:
            return 0.0
        path = font_path or self.resolve_font_path(font_name)
        if path:
            try:
                cached = self._load_font_data(path)
                if cached:
                    total = 0.0
                    scale = font_size / cached["upem"]
                    for ch in text:
                        gn = cached["cmap"].get(ord(ch), ".notdef")
                        w, _ = cached["hmtx"].get(gn, (0, 0))
                        total += w * scale
                    return total
            except Exception:
                pass
        return measure_text(font_name, font_size, text)

    def glyph_visual_center(
        self,
        font_name: str,
        font_size: float,
        char: str,
        font_path: str | None = None,
    ) -> float:
        """Horizontal offset from glyph origin to visual center (in points)."""
        if not char:
            return 0.0
        path = font_path or self.resolve_font_path(font_name)
        if not path or not exists(path):
            return self.measure(font_name, font_size, char, path) / 2
        try:
            from fontTools.pens.boundsPen import BoundsPen
            from fontTools.ttLib import TTFont

            font = TTFont(path)
            cmap = font.getBestCmap()
            gn = cmap.get(ord(char), ".notdef")
            gs = font.getGlyphSet()
            if gn not in gs:
                return self.measure(font_name, font_size, char, path) / 2
            bp = BoundsPen(gs)
            gs[gn].draw(bp)
            if bp.bounds:
                xMin, _yMin, xMax, _yMax = bp.bounds
                upem = font["head"].unitsPerEm
                scale = font_size / upem
                return (xMin + xMax) / 2 * scale
        except Exception:
            pass
        return self.measure(font_name, font_size, char, path) / 2

    def glyph_bbox_width(self, cp: int, fc: "FontConfig") -> float:
        """Return the bounding-box width of a glyph codepoint in points."""
        try:
            from fontTools.pens.boundsPen import BoundsPen
            from fontTools.ttLib import TTFont

            path = self.resolve_font_path(fc.font_name)
            if not path:
                return 13.0
            font = TTFont(path)
            cmap = font.getBestCmap()
            gn = cmap.get(cp, ".notdef")
            gs = font.getGlyphSet()
            if gn in gs:
                bp = BoundsPen(gs)
                gs[gn].draw(bp)
                if bp.bounds:
                    xmin, _, xmax, _ = bp.bounds
                    return (xmax - xmin) * fc.size / font["head"].unitsPerEm
        except Exception:
            pass
        return 13.0

    def resolve_glyph_char(self, cp: int, fc: "FontConfig") -> str:
        """Return the character to use for a codepoint with the given font.

        Checks the font's cmap: first the Unicode codepoint directly,
        then the Q-offset PUA codepoint. Returns '' if no glyph found.
        """
        try:
            from fontTools.ttLib import TTFont

            path = self.resolve_font_path(fc.font_name)
            if not path:
                return chr(cp) if cp <= 0x10FFFF else ""
            font = TTFont(path)
            cmap = font.getBestCmap()
            if cp in cmap:
                return chr(cp)
            if fc.offset and fc.offset < 0xF0000:
                gcp = fc.range_start + (cp - fc.offset)
                if 0 <= gcp <= 0x10FFFF and gcp in cmap:
                    return chr(gcp)
        except Exception:
            pass
        return chr(cp) if cp <= 0x10FFFF else ""

    def wrap(self, font_name: str, font_size: float, text: str, max_width: float) -> list[str]:
        """Greedy word-wrap to fit within *max_width*."""
        return wrap_text(font_name, font_size, text, max_width)

    # -- Internal -------------------------------------------

    def _load_font_data(self, font_path: str) -> dict | None:
        if font_path in self._font_data_cache:
            return self._font_data_cache[font_path]
        try:
            from fontTools.ttLib import TTFont

            font = TTFont(font_path)
            data = {
                "cmap": font.getBestCmap(),
                "hmtx": font["hmtx"],
                "upem": font["head"].unitsPerEm,
            }
            self._font_data_cache[font_path] = data
            return data
        except Exception:
            return None
