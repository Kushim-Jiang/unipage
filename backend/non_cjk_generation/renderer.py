"""
PDF renderer for Unicode code charts using fpdf2.

Renders page structure (list of page dicts with text_spans and drawings)
into a print-ready PDF. Handles font registration, text placement,
line/rectangle drawing, and reserved-cell diagonal hatching.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def to_rgb(val):
    """Convert a color value to (r, g, b) tuple."""
    if val is None:
        return None
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return (int(val[0] * 255), int(val[1] * 255), int(val[2] * 255))
    if isinstance(val, (int, float)):
        v = int(val)
        return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    return None


# ==================================================================->
#  Font registry
# ==================================================================->

# Map layout font names ->(fpdf2 family, style)
DEFAULT_FONT_MAP = {
    "OpenSans-Bold": ("OpenSans", "B"),
    "OpenSans-Italic": ("OpenSans", "I"),
    "OpenSans-Light": ("OpenSansLight", ""),
    "LiberationSans-Regular": ("LiberationSans", ""),
    "LiberationSans-Bold": ("LiberationSans", "B"),
    "LiberationSans-Italic": ("LiberationSans", "I"),
    "LiberationSansNarrow-Regular": ("LiberationSansNarrow", ""),
    "LiberationSerif-Regular": ("LiberationSerif", ""),
}

FALLBACK_FONT = ("LiberationSans", "")


def register_fonts(
    pdf,
    font_dir: str,
    system_font_dir: str = "",
    extra_fonts: list[tuple[str, str, str]] | None = None,
    extra_font_dirs: list[str] | None = None,
):
    """Register all required fonts with fpdf2.

    Parameters
    ----------
    pdf: fpdf2.FPDF instance
    font_dir: Path to directory containing project font files (.ttf/.otf)
    system_font_dir: Optional path to system fonts. If a font is not
        found in *font_dir*, it is also searched in *system_font_dir*.
    extra_fonts: Optional list of (family, style, filename) tuples to
        register in addition to the built-in defaults.  Callers use this
        to supply block-specific fonts not shipped with the library.
    extra_font_dirs: Optional list of additional directories to search
        for font files (checked after *font_dir*, before *system_font_dir*).
        Use this when block-specific fonts live alongside block data.
    """
    import sys

    font_registry = [
        ("OpenSans", "", "OpenSans-Regular.ttf"),
        ("OpenSans", "B", "OpenSans-Bold.ttf"),
        ("OpenSans", "I", "OpenSans-Italic.ttf"),
        ("OpenSansLight", "", "OpenSans-Light.ttf"),
        # Liberation Sans family
        ("LiberationSans", "", "LiberationSans-Regular.ttf"),
        ("LiberationSans", "B", "LiberationSans-Bold.ttf"),
        ("LiberationSans", "I", "LiberationSans-Italic.ttf"),
        ("LiberationSansNarrow", "", "LiberationSansNarrow-Regular.ttf"),
        # Liberation Serif for bullets/arrows/specials
        ("LiberationSerif", "", "LiberationSerif-Regular.ttf"),
        # SpecialsUC6 for Unicode chart reserved-cell markers
        ("SpecialsUC6", "", "SpecialsUC6-20240723.ttf"),
        # CJK Radicals for RS radical characters
        ("CJKRadicals-Light", "", "CJKRadicals-Light.ttf"),
    ]

    if extra_fonts:
        font_registry.extend(extra_fonts)

    font_base = Path(font_dir)
    extra_bases = [Path(d) for d in extra_font_dirs] if extra_font_dirs else []
    sys_base = Path(system_font_dir) if system_font_dir else None

    for family, style, filename in font_registry:
        path = font_base / filename
        if not path.exists():
            for eb in extra_bases:
                candidate = eb / filename
                if candidate.exists():
                    path = candidate
                    break
        if not path.exists() and sys_base:
            path = sys_base / filename
        if path.exists():
            try:
                pdf.add_font(family, style, str(path))
            except Exception as e:
                print(f"  Warning: {filename} ({style}) - {e}", file=sys.stderr)
        else:
            print(f"  Warning: font file not found: {filename}", file=sys.stderr)

    print(f"  Registered {len(font_registry)} fonts")


# ==================================================================->
#  Reserved cell hatching
# ==================================================================->


class ReservedCellHatcher:
    """Draws 45\u00b0 diagonal hatch lines in reserved (unassigned) code-chart cells.

    Consolidates the trapezoid-drawing and cell-walking algorithm into
    a single class, replacing the former standalone functions
    ``_draw_diag_trapezoid`` and ``_draw_reserved_cell_lines``.

    Usage::

        hatcher = ReservedCellHatcher(ucd_path, block_start_cp, block_end_cp)
        hatcher.draw(pdf, page_num=1)

    Or pass *assigned_cps* directly to skip file I/O::

        hatcher = ReservedCellHatcher(assigned_cps={0x41, 0x42, ...},
                                      block_start_cp=0x40, block_end_cp=0x7F)
    """

    def __init__(
        self,
        ucd_path: str = "",
        block_start_cp: int = 0,
        block_end_cp: int = 0,
        num_cols: int = 12,
        num_rows: int = 16,
        grid_left: float = 116.1,
        grid_top: float = 92.88,
        cell_width: float = 31.65,
        cell_height: float = 39.6,
        diag_color: tuple = (35, 31, 32),
        diag_width: float = 0.58,
        line_spacing: float = 4.62,
        assigned_cps: set[int] | None = None,
    ):
        self.ucd_path = ucd_path
        self.assigned_cps = assigned_cps
        self.block_start_cp = block_start_cp
        self.block_end_cp = block_end_cp
        self.num_cols = num_cols
        self.num_rows = num_rows
        self.grid_left = grid_left
        self.grid_top = grid_top
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.diag_color = diag_color
        self.diag_width = diag_width
        self.line_spacing = line_spacing
        self._offset2 = diag_width / 1.4142135623730951

    def draw(self, pdf, page_num: int):
        """Draw reserved-cell hatching for one chart page."""
        start_cp = self.block_start_cp + (page_num - 1) * self.num_rows * self.num_cols

        assigned = self._load_assigned(start_cp)
        pdf.set_fill_color(*self.diag_color)

        reserved = self._build_reserved_mask(start_cp, assigned)
        grid_right = self.grid_left + self.num_cols * self.cell_width
        grid_bottom = self.grid_top + self.num_rows * self.cell_height

        intercept_start = self.grid_top - grid_right
        intercept_end = grid_bottom - self.grid_left

        intercept = intercept_start
        while intercept <= intercept_end:
            cur_x, cur_y, entry_boundary = self._entry_point(intercept, grid_right, grid_bottom)
            exit_x, exit_y, grid_exit_boundary = self._exit_point(intercept, grid_right, grid_bottom)

            seg_start = None
            seg_end = None
            seg_entry_boundary = None

            while cur_x < exit_x - 0.01 and cur_y < exit_y - 0.01:
                col = int((cur_x - self.grid_left + 0.001) // self.cell_width)
                row = int((cur_y - self.grid_top + 0.001) // self.cell_height)
                col = max(0, min(col, self.num_cols - 1))
                row = max(0, min(row, self.num_rows - 1))

                cell_right = self.grid_left + (col + 1) * self.cell_width
                cell_bottom = self.grid_top + (row + 1) * self.cell_height

                if cell_right + intercept <= cell_bottom:
                    next_x = min(cell_right, exit_x)
                    next_y = next_x + intercept
                    step_exit = "V"
                else:
                    next_y = min(cell_bottom, exit_y)
                    next_x = next_y - intercept
                    step_exit = "H"

                if abs((cell_right + intercept) - cell_bottom) < 0.01:
                    step_exit = "B"

                if next_x > exit_x:
                    next_x = exit_x
                    next_y = next_x + intercept
                    step_exit = grid_exit_boundary
                if next_y > exit_y:
                    next_y = exit_y
                    next_x = next_y - intercept
                    step_exit = grid_exit_boundary

                if next_x <= cur_x + 0.001 and next_y <= cur_y + 0.001:
                    if cell_right + intercept <= cell_bottom:
                        next_x = min(cell_right, exit_x)
                        next_y = next_x + intercept
                    else:
                        next_y = min(cell_bottom, exit_y)
                        next_x = next_y - intercept
                    if next_x <= cur_x:
                        next_x = cur_x + 0.01
                        next_y = next_x + intercept
                    if next_y <= cur_y:
                        next_y = cur_y + 0.01
                        next_x = next_y - intercept

                if reserved[row][col]:
                    if seg_start is None:
                        seg_start = (cur_x, cur_y)
                        seg_entry_boundary = entry_boundary
                    seg_end = (next_x, next_y)
                    entry_boundary = step_exit
                else:
                    if seg_start is not None:
                        sx, sy = seg_start
                        ex, ey = seg_end
                        if abs(ex - sx) > 0.5 or abs(ey - sy) > 0.5:
                            self._draw_trapezoid(pdf, sx, sy, ex, ey, seg_entry_boundary, entry_boundary)
                        seg_start = None
                    entry_boundary = step_exit

                cur_x, cur_y = next_x, next_y

            if seg_start is not None:
                sx, sy = seg_start
                ex, ey = seg_end
                if abs(ex - sx) > 0.5 or abs(ey - sy) > 0.5:
                    self._draw_trapezoid(pdf, sx, sy, ex, ey, seg_entry_boundary, grid_exit_boundary)

            intercept += self.line_spacing

    # -- Internal helpers ----------------------------------

    def _load_assigned(self, start_cp: int) -> set:
        if self.assigned_cps is not None:
            return {cp for cp in self.assigned_cps if start_cp <= cp < start_cp + self.num_rows * self.num_cols}
        assigned = set()
        ucd = Path(self.ucd_path)
        if ucd.exists():
            with open(ucd, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or not line[0].isalnum():
                        continue
                    parts = line.split(";")
                    if len(parts) >= 2:
                        try:
                            cp = int(parts[0], 16)
                        except ValueError:
                            continue
                        if start_cp <= cp < start_cp + self.num_rows * self.num_cols:
                            assigned.add(cp)
        return assigned

    def _build_reserved_mask(self, start_cp: int, assigned: set) -> list[list[bool]]:
        reserved = [[False] * self.num_cols for _ in range(self.num_rows)]
        for row in range(self.num_rows):
            for col in range(self.num_cols):
                cp = start_cp + row + col * self.num_rows
                if cp <= self.block_end_cp and cp not in assigned:
                    reserved[row][col] = True
        return reserved

    def _entry_point(self, intercept: float, grid_right: float, grid_bottom: float):
        y_at_left = self.grid_left + intercept
        if self.grid_top <= y_at_left <= grid_bottom:
            return self.grid_left, y_at_left, "V"
        elif y_at_left < self.grid_top:
            return self.grid_top - intercept, self.grid_top, "H"
        else:
            return grid_bottom - intercept, grid_bottom, "H"

    def _exit_point(self, intercept: float, grid_right: float, grid_bottom: float):
        y_at_right = grid_right + intercept
        if self.grid_top <= y_at_right <= grid_bottom:
            return grid_right, y_at_right, "V"
        elif y_at_right > grid_bottom:
            return grid_bottom - intercept, grid_bottom, "H"
        else:
            return self.grid_top - intercept, self.grid_top, "H"

    def _draw_trapezoid(self, pdf, sx, sy, ex, ey, start_cut, end_cut):
        """Draw a filled trapezoid for one diagonal hatch segment."""
        o = self._offset2
        if start_cut == "H" and end_cut == "V":
            points = [(sx - o, sy), (sx + o, sy), (ex, ey - o), (ex, ey + o)]
        elif start_cut == "V" and end_cut == "H":
            points = [(sx, sy - o), (sx, sy + o), (ex - o, ey), (ex + o, ey)]
        elif start_cut == "H" and end_cut == "H":
            points = [(sx - o, sy), (sx + o, sy), (ex + o, ey), (ex - o, ey)]
        elif start_cut == "V" and end_cut == "V":
            points = [(sx, sy + o), (ex, ey + o), (ex, ey - o), (sx, sy - o)]
        else:
            points = [(sx - o, sy), (sx + o, sy), (ex, ey - o), (ex, ey + o)]
        pdf.polygon(points, style="F")


# Backward-compatible wrapper
def _draw_reserved_cell_lines(
    pdf,
    page_num,
    ucd_path,
    block_start_cp,
    block_end_cp,
    num_cols=12,
    num_rows=16,
    grid_left=116.1,
    grid_top=92.88,
    cell_width=31.65,
    cell_height=39.6,
    assigned_cps=None,
):
    hatcher = ReservedCellHatcher(
        ucd_path,
        block_start_cp,
        block_end_cp,
        num_cols=num_cols,
        num_rows=num_rows,
        grid_left=grid_left,
        grid_top=grid_top,
        cell_width=cell_width,
        cell_height=cell_height,
        assigned_cps=assigned_cps,
    )
    hatcher.draw(pdf, page_num)


# ==================================================================->
#  Main render function
# ==================================================================->


def render_pdf(
    pages_data: list[dict],
    output_path: str,
    font_dir: str,
    ucd_path: Optional[str] = None,
    font_map: Optional[dict] = None,
    block_start_cp: int = 0,
    block_end_cp: int = 0,
    num_chart_pages: int = 0,
    system_font_dir: str = "",
    num_chart_cols: int = 0,
    extra_fonts: list[tuple[str, str, str]] | None = None,
    extra_font_map: dict[str, tuple[str, str]] | None = None,
    extra_font_dirs: list[str] | None = None,
    assigned_cps: set[int] | None = None,
):
    """Render page structure to a PDF file using fpdf2.

    Parameters
    ----------
    pages_data: List of page dicts from generate_page_structure()
    output_path: Output PDF file path
    font_dir: Directory containing .ttf/.otf project font files
    ucd_path: Path to UnicodeData.txt (for reserved cell hatching)
    font_map: Optional custom font name mapping (fully replaces defaults)
    block_start_cp: First codepoint of the block (for reserved-cell hatching)
    block_end_cp: Last codepoint of the block
    num_chart_pages: Number of chart grid pages (0 = auto-detect).
        Pages 1..num_chart_pages get reserved-cell hatching.
    num_chart_cols: Columns per chart page (0 = auto-detect from grid width).
    system_font_dir: Optional path to system fonts
    extra_fonts: Optional block-specific fonts to register, as
        (family, style, filename) tuples.
    extra_font_map: Optional block-specific font name ->(family, style)
        mapping, merged on top of DEFAULT_FONT_MAP.
    extra_font_dirs: Optional additional directories to search for font
        files.  Use when block-specific .ttf files live alongside block data
        rather than in the shared *font_dir*.
    """
    from fpdf import FPDF

    # Auto-detect chart page count and column count from page data
    if num_chart_pages <= 0 or num_chart_cols <= 0:
        max_chart_pn = 0
        for p in pages_data:
            pn = p.get("page_num", -1)
            if pn < 1:
                continue
            grid_rects = [
                item
                for d in p.get("drawings", [])
                for item in d.get("items", [])
                if item.get("op") == "re" and item.get("h", 0) > 600
            ]
            if grid_rects:
                max_chart_pn = max(max_chart_pn, pn)
                if num_chart_cols <= 0:
                    xs = sorted(item["x"] for item in grid_rects)
                    if len(xs) >= 2:
                        num_chart_cols = round((xs[-1] + grid_rects[-1]["w"] - xs[0]) / 31.65)
                    else:
                        num_chart_cols = 1
        if num_chart_pages <= 0:
            num_chart_pages = max_chart_pn
        if num_chart_pages <= 0:
            num_chart_pages = 1
        if num_chart_cols <= 0:
            num_chart_cols = 12

    # Build font map: defaults + caller extras
    fm = dict(DEFAULT_FONT_MAP)
    if extra_font_map:
        fm.update(extra_font_map)
    if font_map:
        fm = font_map  # explicit override takes full precedence

    print(f"Rendering {len(pages_data)} pages...")
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    register_fonts(pdf, font_dir, system_font_dir, extra_fonts=extra_fonts, extra_font_dirs=extra_font_dirs)

    for page_info in pages_data:
        pn = page_info["page_num"]
        pdf.add_page()

        # -- Phase 1: background fills (white rectangles) -----
        for drawing in page_info.get("drawings", []):
            items = drawing.get("items", [])
            if not items:
                continue
            fill_rgb = to_rgb(drawing.get("fill"))
            stroke_rgb = to_rgb(drawing.get("color"))
            # Only pure-fill drawings (no stroke) at this stage
            if stroke_rgb is not None or fill_rgb is None:
                continue
            for item in items:
                if item["op"] == "re":
                    pdf.set_fill_color(*fill_rgb)
                    pdf.set_line_width(0)
                    pdf.rect(item["x"], item["y"], item["w"], item["h"], "F")

        # -- Phase 2: reserved-cell diagonal hatching ---------
        if (ucd_path or assigned_cps) and block_start_cp and 1 <= pn <= num_chart_pages:
            # Extract actual grid_left and num_cols from page data
            # (handles combined layouts where grid is not centered)
            chart_page = pages_data[pn] if pn < len(pages_data) else None
            actual_cols = num_chart_cols
            actual_grid_left = (612.0 - num_chart_cols * 31.65) / 2
            if chart_page:
                grid_rects = [
                    item["x"]
                    for d in chart_page.get("drawings", [])
                    for item in d.get("items", [])
                    if item.get("op") == "re" and item.get("h", 0) > 600
                ]
                if grid_rects:
                    actual_grid_left = min(grid_rects)
                    grid_right = max(
                        item["x"] + item["w"]
                        for d in chart_page.get("drawings", [])
                        for item in d.get("items", [])
                        if item.get("op") == "re" and item.get("h", 0) > 600
                    )
                    actual_cols = round((grid_right - actual_grid_left) / 31.65)
            _draw_reserved_cell_lines(
                pdf,
                pn,
                ucd_path,
                block_start_cp=block_start_cp,
                block_end_cp=block_end_cp,
                num_cols=actual_cols,
                grid_left=actual_grid_left,
                assigned_cps=assigned_cps,
            )

        # -- Phase 3: border / stroke lines (on top of hatching)
        for drawing in page_info.get("drawings", []):
            items = drawing.get("items", [])
            if not items:
                continue
            stroke_rgb = to_rgb(drawing.get("color"))
            fill_rgb = to_rgb(drawing.get("fill"))
            # Only stroke drawings (or stroke+fill combos) at this stage
            if stroke_rgb is None:
                continue
            w = max(drawing.get("width", 0.5), 0.1)
            for item in items:
                op = item["op"]
                if op == "l":
                    pdf.set_draw_color(*stroke_rgb)
                    pdf.set_line_width(w)
                    pdf.line(item["x1"], item["y1"], item["x2"], item["y2"])
                elif op == "re":
                    if fill_rgb:
                        pdf.set_fill_color(*fill_rgb)
                    pdf.set_draw_color(*stroke_rgb)
                    style = "D"
                    if fill_rgb:
                        style = "FD"
                    pdf.set_line_width(w)
                    pdf.rect(item["x"], item["y"], item["w"], item["h"], style)

        # Draw text spans
        pdf.set_draw_color(0, 0, 0)
        pdf.set_fill_color(0, 0, 0)
        pdf.set_text_color(0, 0, 0)

        for span in page_info.get("text_spans", []):
            text = span["text"]
            if not text or text == " ":
                continue
            font_name = span["font"]
            size = span["size"]
            color = span.get("color", 0)
            bbox = span.get("bbox", [0, 0, 0, 0])

            # Resolve font: try explicit map first, then font name itself
            # (works for block-specific fonts registered under their own name),
            # finally fall back to LiberationSans.
            family, style = fm.get(font_name) or (font_name, "")
            rgb = to_rgb(color)
            if rgb:
                pdf.set_text_color(*rgb)
            try:
                pdf.set_font(family, style, size)
            except Exception:
                pdf.set_font("LiberationSans", "", size)
            origin = span.get("origin", [bbox[0], bbox[3]])
            pdf.text(origin[0], origin[1], text)

        pdf.set_text_color(0, 0, 0)

    pdf.output(str(output_path))
    fsize = Path(output_path).stat().st_size
    print(f"Saved: {output_path} ({fsize:,} bytes)")
    print("Done!")
