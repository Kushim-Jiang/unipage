"""
Page layout computation for Unicode code charts.

Generates page structures from parsed CFL data, nameslist entries,
and block configuration. Produces a list of page dicts ready for
JSON serialization and PDF rendering.

Pipeline:
  1. Title page (block name, range, template text)
  2. Code chart pages (glyph grid)
  3. Information section pages (two-column nameslist)
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.non_cjk_generation.models import (
    PAGE_W,
    BlockInfo,
    Drawing,
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
    TitlePageConfig,
    measure_text,
    shift_x,
    wrap_text,
)
from backend.non_cjk_generation.parsers import extract_block_entries, find_font_for_range, parse_cfl, parse_nameslist

# ==================================================================->
#  Title page
# ==================================================================->


def _make_span(text: str, font: str, size: float, x: float, y: float, color: int = 0) -> TextSpan:
    if not text or text == " ":
        width = 0.0
    else:
        width = measure_text(font, size, text)
    return TextSpan(
        text=text,
        font=font,
        size=size,
        color=color,
        bbox=[x, y - size * 0.8, x + width, y + size * 0.2],
        origin=[x, y],
    )


def compute_title_page(ctx: LayoutContext, title_md_path: str = "", cfg: TitlePageConfig = None) -> Page:
    """Compute the title/front-matter page layout.

    Reads text content from a Markdown template file (title.md) and
    lays it out with positions and fonts driven by *cfg*.
    Block name and range lines are generated from context.
    """
    if cfg is None:
        cfg = TitlePageConfig()

    page = Page(page_num=0)
    spans: list[TextSpan] = []
    x = cfg.margin_left

    from backend.non_cjk_generation.models import FontMetrics

    fm = FontMetrics(ctx.font_dir, ctx.extra_font_dirs)

    block = ctx.block
    if not block:
        return page

    # -- Line 0: Block name ---------------------------------
    w = fm.measure(cfg.block_name_font[0], cfg.block_name_font[1], block.name)
    spans.append(
        TextSpan(
            text=block.name,
            font=cfg.block_name_font[0],
            size=cfg.block_name_font[1],
            bbox=[
                x,
                cfg.block_name_y - cfg.block_name_font[1] * 0.8,
                x + w,
                cfg.block_name_y + cfg.block_name_font[1] * 0.2,
            ],
            origin=[x, cfg.block_name_y],
        )
    )

    # -- Line 1: Range --------------------------------------
    if block.draft_mode:
        range_text = f"Range: {block.format_draft_cp(0)}\u2013{block.format_draft_cp(block.block_size - 1)}"
    else:
        range_text = f"Range: {block.start_cp:04X}\u2013{block.end_cp:04X}"
    w = fm.measure(cfg.range_font[0], cfg.range_font[1], range_text)
    spans.append(
        TextSpan(
            text=range_text,
            font=cfg.range_font[0],
            size=cfg.range_font[1],
            bbox=[x, cfg.range_y - cfg.range_font[1] * 0.8, x + w, cfg.range_y + cfg.range_font[1] * 0.2],
            origin=[x, cfg.range_y],
        )
    )

    # -- Parse title.md template ----------------------------
    if title_md_path:
        template_lines = _parse_title_md(title_md_path, ctx, cfg, fm)
    else:
        template_lines = _default_title_lines(ctx)

    for y_pos, text, font, size in template_lines:
        w = fm.measure(font, size, text) if fm else measure_text(font, size, text)
        spans.append(
            TextSpan(
                text=text,
                font=font,
                size=size,
                bbox=[x, y_pos - size * 0.8, x + w, y_pos + size * 0.2],
                origin=[x, y_pos],
            )
        )

    page.text_spans = spans
    return page


def _parse_title_md(filepath: str, ctx: LayoutContext, cfg: TitlePageConfig, fm=None) -> list:
    """Parse title.md into (y, text, font, size) tuples.

    Each markdown line maps to one layout line ->no automatic word-wrapping.
    The user controls line breaks by editing the markdown file directly.
    """
    from backend.non_cjk_generation.models import wrap_text

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Substitute placeholders
    block = ctx.block
    content = content.replace("[name]", block.name if block else "")
    if block and block.draft_mode:
        content = content.replace("[start]", block.format_draft_cp(0))
        content = content.replace("[end]", block.format_draft_cp(block.block_size - 1))
    else:
        content = content.replace("[start]", f"{block.start_cp:04X}" if block else "")
        content = content.replace("[end]", f"{block.end_cp:04X}" if block else "")
    content = content.replace("[version-long]", ctx.version)
    content = content.replace("[version]", ctx.short_version)
    content = content.replace("[year]", ctx.year)

    # Replace smart-quote markers
    content = content.replace("\u201c", "\u201c")
    content = content.replace("\u201d", "\u201d")

    lines = content.split("\n")
    result: list = []
    y = cfg.body_start_y

    last_type = "subtitle"  # we just output the Range subtitle
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip title/range lines ->already output above
        if line.startswith("## "):
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            continue
        if line.startswith("### Range:"):
            i += 1
            continue

        # Peek at next non-empty line type for spacing decisions
        def _peek_type(start):
            j = start
            while j < len(lines):
                nl = lines[j].strip()
                if not nl:
                    return "blank"
                if nl.startswith("### "):
                    return "heading"
                if nl.startswith("_") and nl.rstrip().endswith("_"):
                    return "italic"
                return "body"
            return "eof"

        # Blank line ->space (formatter-safe: only one blank line matters)
        if not line.strip():
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            next_line = lines[i].strip() if i < len(lines) else ""

            if last_type == "heading":
                continue
            if last_type == "subtitle":
                if next_line.startswith("### "):
                    y += cfg.space_to_heading
                elif next_line.startswith("_"):
                    y += cfg.space_to_italic
                else:
                    y += cfg.space_to_body
                continue

            if last_type == "body":
                y += cfg.body_to_space - cfg.body_leading
            elif last_type == "italic":
                y += cfg.italic_to_space - cfg.body_leading
            elif last_type == "space":
                pass
            else:
                y += cfg.body_to_space

            result.append((y, " ", cfg.space_font[0], cfg.space_font[1]))
            last_type = "space"

            if next_line.startswith("### "):
                y += cfg.space_to_heading
            elif next_line.startswith("_"):
                y += cfg.space_to_italic
            else:
                y += cfg.space_to_body
            continue

        # ### heading ->bold (word-wrapped)
        if line.startswith("### "):
            heading = line[4:].strip()
            font_path = fm.resolve_font_path(cfg.bold_font[0]) if fm else None
            wrapped = wrap_text(cfg.bold_font[0], cfg.bold_font[1], heading, cfg.max_width, font_path=font_path)
            for wi, wline in enumerate(wrapped):
                result.append((y, wline, cfg.bold_font[0], cfg.bold_font[1]))
                if wi < len(wrapped) - 1:
                    y += cfg.body_leading
            y += cfg.heading_to_body
            last_type = "heading"
            i += 1
            continue

        # Italic line (_..._) ->word-wrapped, <br> forces line break
        if line.startswith("_") and line.rstrip().endswith("_"):
            text = line[1:].rstrip()[:-1]
            parts = [p.strip() for p in text.split("<br>")]
            font_path = fm.resolve_font_path(cfg.italic_font[0]) if fm else None
            for pi, part in enumerate(parts):
                if not part:
                    continue
                wrapped = wrap_text(cfg.italic_font[0], cfg.italic_font[1], part, cfg.max_width, font_path=font_path)
                for wi, wline in enumerate(wrapped):
                    result.append((y, wline, cfg.italic_font[0], cfg.italic_font[1]))
                    if wi < len(wrapped) - 1:
                        y += cfg.body_leading
                is_last = pi == len(parts) - 1
                if is_last:
                    nxt = _peek_type(i + 1)
                    if nxt == "body":
                        y += cfg.body_leading
                    elif nxt == "italic":
                        y += cfg.body_leading
                    else:
                        y += cfg.body_leading
                else:
                    y += cfg.body_leading
            last_type = "italic"
            i += 1
            continue

        # Body line — merge consecutive body lines (ignore single newlines),
        # then word-wrap at cfg.max_width.  <br> forces a line break.
        body_lines = [line.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                # blank line — stop merging
                break
            if nxt.startswith("### ") or (nxt.startswith("_") and nxt.rstrip().endswith("_")):
                # heading or italic — stop merging
                break
            body_lines.append(nxt)
            i += 1
        full_text = " ".join(body_lines)
        # Word-wrap with precise measurement
        font_path = fm.resolve_font_path(cfg.body_font[0]) if fm else None
        wrapped = wrap_text(cfg.body_font[0], cfg.body_font[1], full_text, cfg.max_width, font_path=font_path)
        for wi, wline in enumerate(wrapped):
            result.append((y, wline, cfg.body_font[0], cfg.body_font[1]))
            is_last = wi == len(wrapped) - 1
            if is_last:
                nxt = _peek_type(i)
                if nxt == "italic":
                    y += cfg.body_to_italic
                elif nxt == "body":
                    y += cfg.body_leading
                elif nxt == "heading":
                    y += cfg.body_leading
                else:
                    y += cfg.body_leading
            else:
                y += cfg.body_leading
        last_type = "body"
        continue

    return result


def _default_title_lines(ctx: LayoutContext) -> list:
    """Fallback template lines when no title.md is provided."""
    return []


# ==================================================================->
#  Code chart pages
# ==================================================================->

# Global config instances (defaults; callers can override)
_grid = GridConfig()
_info_cfg = InfoConfig()

# Font constants for chart pages
FONT_CHART_HEADER = ("OpenSans-Bold", 11.0)
FONT_CHART_FOOTER = ("OpenSans-Italic", 9.0)
FONT_COL_HEADER = ("LiberationSans-Regular", 10.0)
FONT_ROW_IDX = ("LiberationSans-Regular", 10.0)
FONT_CP_LABEL = ("LiberationSansNarrow-Regular", 6.0)
FONT_DOLLAR = ("SpecialsUC6", 22.0)


def _hex4(v: int) -> str:
    return f"{v:04X}"


def _get_assigned(sc: int, ec: int, assigned_cps: set[int] | None = None) -> set:
    if assigned_cps is not None:
        return {cp for cp in assigned_cps if sc <= cp <= ec}
    return set()


def _get_combining(combining_cps: set[int] | None = None) -> set:
    """Return set of combining-mark codepoints (General Category M*)."""
    return combining_cps or set()


class ChartPageBuilder:
    """Builds a single Unicode code chart grid page.

    Consolidates what were formerly 6+ standalone functions
    (_chart_header, _col_headers, _row_indices, _glyph_cells,
     _grid_drawings, _chart_footer) into a single class.

    Usage::

        builder = ChartPageBuilder(ctx, font_map, col_start=0, col_end=12,
                                   page_index=0, total_pages=2)
        page = builder.build()
    """

    def __init__(
        self,
        ctx: LayoutContext,
        font_map: dict[int, FontConfig],
        col_start: int,
        col_end: int,
        page_index: int,
        total_pages: int,
        page_type: PageType = PageType.CENTER,
        grid: GridConfig | None = None,
        font_metrics: FontMetrics | None = None,
    ):
        self.ctx = ctx
        self.font_map = font_map
        self.block = ctx.block
        self.col_start = col_start
        self.col_end = col_end
        self.page_index = page_index
        self.total_pages = total_pages
        self.page_type = page_type
        self.grid = grid or _grid
        self.fm = font_metrics or FontMetrics(ctx.font_dir, ctx.extra_font_dirs)

        self.page = Page(page_num=0)

    # -- Properties derived from config --------------------

    @property
    def num_cols(self) -> int:
        return self.col_end - self.col_start

    @property
    def is_first_page(self) -> bool:
        return self.page_index == 0

    @property
    def is_last_page(self) -> bool:
        return self.page_index == self.total_pages - 1

    @property
    def grid_left(self) -> float:
        bl = self.block
        if bl and bl.grid_left is not None:
            return bl.grid_left
        return self.grid.center_grid_left(self.num_cols)

    # -- Build method --------------------------------------

    def build(self) -> Page:
        self._add_header()
        self._add_col_headers()
        self._add_row_indices()
        self._add_glyph_cells()
        self._add_grid_drawings()
        self._add_footer()
        return self.page

    # -- Header --------------------------------------------

    def _add_header(self):
        block = self.block
        if not block:
            return
        pt = self.page_type
        g = self.grid
        xs = shift_x(82.80, pt)

        if block.draft_mode:
            start_label = block.format_draft_cp(0)
            pe = block.draft_cp(block.start_cp + self.col_end * 16 - 1)
            if self.is_last_page:
                pe = block.draft_cp(block.end_cp)
            end_label = block.format_draft_cp(pe)
        else:
            start_label = _hex4(block.start_cp)
            pe = block.start_cp + self.col_end * 16 - 1
            if self.is_last_page:
                pe = block.end_cp
            end_label = _hex4(pe)

        name_w = measure_text(FONT_CHART_HEADER[0], FONT_CHART_HEADER[1], block.name)
        xn = shift_x(PAGE_W / 2 - name_w / 2, pt)
        end_w = measure_text(FONT_CHART_HEADER[0], FONT_CHART_HEADER[1], end_label)
        xe = shift_x(g.chart_header_right - end_w, pt)

        self.page.text_spans.append(
            TextSpan(
                text=start_label,
                font=FONT_CHART_HEADER[0],
                size=FONT_CHART_HEADER[1],
                origin=[xs, g.header_y],
                bbox=[xs, 36, xs + 24, 47],
            )
        )
        self.page.text_spans.append(
            TextSpan(
                text=block.name,
                font=FONT_CHART_HEADER[0],
                size=FONT_CHART_HEADER[1],
                origin=[xn, g.header_y],
                bbox=[xn, 36, xn + name_w, 47],
            )
        )
        self.page.drawings.append(Drawing.rect(xn, 34.14, name_w, 13.62))
        self.page.text_spans.append(
            TextSpan(
                text=end_label,
                font=FONT_CHART_HEADER[0],
                size=FONT_CHART_HEADER[1],
                origin=[xe, g.header_y],
                bbox=[xe, 36, xe + end_w, 47],
            )
        )
        self.page.drawings.append(Drawing.rect(xe, 34.14, end_w, 13.62))
        self.page.drawings.append(Drawing.rect(xs, 34.14, 24.48, 13.62))

    # -- Column headers ------------------------------------

    def _add_col_headers(self):
        block = self.block
        if not block:
            return
        pt = self.page_type
        g = self.grid
        gl = self.grid_left
        base = block.start_cp
        for i in range(self.num_cols):
            if block.draft_mode:
                col_draft_cp = block.draft_cp(base + (self.col_start + i) * 16)
                text = block.format_draft_cp(col_draft_cp)[:-1]
            else:
                text = f"{(base + (self.col_start + i) * 16) >> 4:03X}"
            text_w = measure_text(FONT_COL_HEADER[0], FONT_COL_HEADER[1], text)
            cell_left = gl + i * g.cell_w
            x = shift_x(cell_left + (g.cell_w - text_w) / 2, pt)
            self.page.text_spans.append(
                TextSpan(
                    text=text,
                    font=FONT_COL_HEADER[0],
                    size=FONT_COL_HEADER[1],
                    origin=[x, g.col_header_y],
                    bbox=[x, 78.4, x + text_w, 88.4],
                )
            )

    # -- Row indices ---------------------------------------

    def _add_row_indices(self):
        pt = self.page_type
        g = self.grid
        gl = self.grid_left
        row_idx_x = gl + (g.row_idx_x - g.grid_left)
        for row in range(g.num_rows):
            y = g.first_glyph_y + row * g.cell_row_h
            x = shift_x(row_idx_x, pt)
            self.page.text_spans.append(
                TextSpan(
                    text=f"{row:X}",
                    font=FONT_ROW_IDX[0],
                    size=FONT_ROW_IDX[1],
                    origin=[x, y],
                    bbox=[x, y - 8, x + 7, y + 2],
                )
            )

    # -- Glyph cells ---------------------------------------

    def _add_glyph_cells(self):
        block = self.block
        if not block:
            return
        pt = self.page_type
        g = self.grid
        gl = self.grid_left
        base = block.start_cp
        assigned = _get_assigned(block.start_cp, block.end_cp, self.ctx.assigned_cps)
        COMB = _get_combining(self.ctx.combining_cps)
        for col in range(self.num_cols):
            cb = base + (self.col_start + col) * 16
            cl = shift_x(gl, pt) + col * g.cell_w
            cc = cl + g.cell_w / 2
            for row in range(g.num_rows):
                cp = cb + row
                if cp > block.end_cp:
                    break
                fc = self.font_map.get(cp)
                gy = g.first_glyph_y + row * g.cell_row_h
                # Compute draft label if draft_mode is enabled
                if block.draft_mode:
                    label_text = block.format_draft_cp(block.draft_cp(cp))
                else:
                    label_text = _hex4(cp)
                if fc and cp in assigned:
                    ch = self.fm.resolve_glyph_char(cp, fc)
                    if not ch:
                        continue
                    bw = self.fm.glyph_bbox_width(cp, fc)
                    gx = cc - bw / 2 - 1.0
                    if cp in COMB:
                        dx = cc - 7.51
                        self.page.text_spans.append(
                            TextSpan(
                                text="$",
                                font=FONT_DOLLAR[0],
                                size=FONT_DOLLAR[1],
                                origin=[dx, gy],
                                bbox=[dx, gy - 18, dx + 8, gy + 4],
                            )
                        )
                        self.page.text_spans.append(
                            TextSpan(
                                text=ch,
                                font=fc.font_name,
                                size=fc.size,
                                origin=[dx + 13.5, gy],
                                bbox=[dx + 13.5, gy - 18, dx + 13.5 + bw, gy + 4],
                            )
                        )
                    else:
                        self.page.text_spans.append(
                            TextSpan(
                                text=ch,
                                font=fc.font_name,
                                size=fc.size,
                                origin=[gx, gy],
                                bbox=[gx, gy - fc.size * 0.9, gx + bw, gy + fc.size * 0.2],
                            )
                        )
                    # Codepoint label
                    label_w = measure_text(FONT_CP_LABEL[0], FONT_CP_LABEL[1], label_text)
                    lx = cc - label_w / 2
                    self.page.text_spans.append(
                        TextSpan(
                            text=label_text,
                            font=FONT_CP_LABEL[0],
                            size=FONT_CP_LABEL[1],
                            origin=[lx, gy + g.label_offset_y],
                            bbox=[lx, gy + 7.3, lx + label_w, gy + 13.8],
                        )
                    )

    # -- Grid drawings -------------------------------------

    def _add_grid_drawings(self):
        pt = self.page_type
        g = self.grid
        nc = self.num_cols
        gl = self.grid_left
        lx = shift_x(gl, pt)
        rx = lx + nc * g.cell_w
        ty = g.grid_top
        by = ty + g.num_rows * g.cell_row_h
        for col in range(nc):
            self.page.drawings.append(Drawing.rect(lx + col * g.cell_w, ty, g.cell_w, g.num_rows * g.cell_row_h))
        for row in range(g.num_rows + 1):
            ry = ty + row * g.cell_row_h
            is_edge = row == 0 or row == g.num_rows
            self.page.drawings.append(Drawing.line(lx, ry, rx, ry, g.thin_border))
            if is_edge:
                self.page.drawings.append(Drawing.line(lx, ry, rx, ry, g.thick_border))
        for col in range(nc + 1):
            vlx = lx + col * g.cell_w
            self.page.drawings.append(Drawing.line(vlx, ty, vlx, by, g.thin_border))
        if self.is_first_page:
            self.page.drawings.append(Drawing.line(lx, ty - g.thick_extend, lx, by, g.thick_border))
        if self.is_last_page:
            self.page.drawings.append(Drawing.line(rx, ty - g.thick_extend, rx, by, g.thick_border))

    # -- Footer --------------------------------------------

    def _add_footer(self):
        pt = self.page_type
        g = self.grid
        xl = shift_x(82.80, pt)
        page_num_text = str(self.ctx.chart_page_base + self.page_index)
        page_num_w = measure_text(FONT_CHART_FOOTER[0], FONT_CHART_FOOTER[1], page_num_text)
        xp = shift_x(g.chart_footer_right - page_num_w, pt)
        ct = (
            f"The Unicode Standard, Version {self.ctx.short_version}, "
            f"Copyright \u00a9 1991-{self.ctx.year} Unicode, Inc. All rights reserved."
        )
        self.page.text_spans.append(
            TextSpan(
                text=ct,
                font=FONT_CHART_FOOTER[0],
                size=FONT_CHART_FOOTER[1],
                origin=[xl, g.footer_y],
                bbox=[xl, 741.5, xl + 430, 750.5],
            )
        )
        self.page.text_spans.append(
            TextSpan(
                text=page_num_text,
                font=FONT_CHART_FOOTER[0],
                size=FONT_CHART_FOOTER[1],
                origin=[xp, g.footer_y],
                bbox=[xp, 741.5, xp + page_num_w, 750.5],
            )
        )
        self.page.drawings.append(Drawing.rect(xl, 740.46, 327.72, 10.8))
        self.page.drawings.append(Drawing.rect(xp, 740.46, page_num_w, 10.8))


# -- Top-level chart page orchestration --------------------


def compute_code_chart_pages(ctx: LayoutContext, font_map: dict[int, FontConfig]) -> list[Page]:
    """Compute code chart grid pages."""
    block = ctx.block
    if not block:
        return []
    tc = block.column_count
    cp = min(tc, 12)
    np = (tc + cp - 1) // cp
    pages = []
    fm = FontMetrics(ctx.font_dir, ctx.extra_font_dirs)
    for pg in range(np):
        cs = pg * cp
        ce = min(cs + cp, tc)
        builder = ChartPageBuilder(
            ctx=ctx,
            font_map=font_map,
            col_start=cs,
            col_end=ce,
            page_index=pg,
            total_pages=np,
            page_type=PageType.CENTER,
            font_metrics=fm,
        )
        page = builder.build()
        page.page_num = 1 + pg
        pages.append(page)
    return pages


# ==================================================================->
#  Information section pages
# ==================================================================->

# Font constants for info pages
FONT_INFO_HEADER = ("OpenSans-Bold", 11.0)
FONT_INFO_FOOTER = ("OpenSans-Italic", 9.0)
FONT_CP = ("LiberationSansNarrow-Regular", 9.0)
FONT_NAME = ("LiberationSans-Regular", 9.0)
FONT_ANNO = ("LiberationSans-Italic", 9.0)
FONT_BULLET = ("LiberationSerif-Regular", 10.0)
FONT_BULLET_TEXT = ("LiberationSans-Regular", 9.0)
FONT_SECTION = ("LiberationSans-Bold", 9.0)
FONT_RESERVED = ("LiberationSans-Regular", 9.0)
FONT_ARROW = ("LiberationSerif-Regular", 9.0)
FONT_INFO_DOLLAR = ("SpecialsUC6", 10.0)
FONT_RESERVED_MARKER = ("SpecialsUC6", 10.0)
FONT_DOTCIRCLE = ("LiberationSerif-Regular", 10.0)
# Gap from "$" origin to combining glyph origin, scaled from code-chart spacing
DOLLAR_GLYPH_GAP = FONT_INFO_DOLLAR[1] * 13.5 / FONT_DOLLAR[1]
FONT_XREF_CP = ("LiberationSans-Regular", 9.0)
FONT_XREF_GLYPH = ("LiberationSerif-Regular", 10.0)
FONT_XREF_TEXT = ("LiberationSans-Regular", 9.0)

_RE_XREF = re.compile(r"^x\s*\((.+?)\s*-\s*([0-9A-Fa-f]+)\)$")


class InfoPageBuilder:
    """Builds two-column information section pages from NamesList entries.

    Consolidates what were formerly 8+ standalone functions
    (_info_header, _info_col, _info_wrap, _info_extra, _info_footer,
     _xref, _xline, _build_info_entries) into a single class.

    Usage::

        builder = InfoPageBuilder(ctx, font_map, nameslist_entries)
        pages = builder.build_pages(start_page_num=130)
    """

    def __init__(
        self,
        ctx: LayoutContext,
        font_map: dict[int, FontConfig],
        nameslist: list[NamesListEntry],
        info_cfg: InfoConfig | None = None,
        font_metrics: FontMetrics | None = None,
    ):
        self.ctx = ctx
        self.font_map = font_map
        self.nameslist = nameslist
        self.cfg = info_cfg or _info_cfg
        self.fm = font_metrics or FontMetrics(ctx.font_dir, ctx.extra_font_dirs)
        self.block = ctx.block

    # -- Public API ----------------------------------------

    def build_pages(self, start_page_num: int) -> list[Page]:
        """Compute all two-column info pages."""
        if not self.block:
            return []
        entries = self._build_entries()
        if not entries:
            return []
        mr = int((743 - self.cfg.first_y) / self.cfg.line_h)
        epp = mr * 2
        np = (len(entries) + epp - 1) // epp
        pages = []
        offset = 0
        for pg in range(np):
            pt = PageType.CENTER
            page = Page(page_num=start_page_num + pg)
            s = offset
            if pg == 0:
                e = min(s + epp - 1, len(entries))
                mid = min(mr - 1, e - s)
                rem = mr
            else:
                e = min(s + epp, len(entries))
                mid = min(mr, e - s)
                rem = mr
            pe = entries[s:e]

            first_cp = None
            last_cp = None
            for entry in pe:
                if "codepoint" in entry:
                    cp = int(entry["codepoint"], 16)
                    if first_cp is None:
                        first_cp = cp
                    last_cp = cp
            if first_cp is None:
                first_cp = self.block.start_cp
            if last_cp is None:
                last_cp = self.block.end_cp
            self._add_header(page, pt, first_cp, last_cp)

            col1_entries = pe[:mid]
            col2_entries = pe[mid : mid + rem] if len(pe) > mid else []
            col1_offset = -3.0 if mid != rem else 0.0
            n1 = self._add_col(page, col1_entries, False, pt, start_y=self.cfg.first_y + col1_offset)
            n2 = self._add_col(page, col2_entries, True, pt)
            self._add_footer(page, start_page_num + pg, pt)
            pages.append(page)
            offset = s + n1 + n2
            if offset >= len(entries):
                break
        return pages

    def estimate_page_count(self) -> int:
        """Return estimated info page count (for layout decisions)."""
        entries = self._build_entries()
        if not entries:
            return 0
        mr = int((743 - self.cfg.first_y) / self.cfg.line_h)
        epp = mr * 2
        return (len(entries) + epp - 1) // epp

    def estimate_total_entries(self) -> int:
        return len(self._build_entries())

    # -- Entry builder ------------------------------------

    def _build_entries(self) -> list[dict]:
        """Build flat info entry list from parsed NamesList entries."""
        entries = []
        assigned = set()
        COMB = _get_combining(self.ctx.combining_cps)
        block = self.block
        for e in self.nameslist:
            if e.codepoint:
                try:
                    cp = int(e.codepoint, 16)
                    if block.start_cp <= cp <= block.end_cp:
                        assigned.add(cp)
                except ValueError:
                    pass
        for nl in self.nameslist:
            if nl.type in ("subheader", "notice"):
                txt = nl.text
                if not txt:
                    continue
                if "(" in txt and "\u2013" in txt:
                    continue
                if txt.startswith("Also known as") or txt.startswith("The aliases"):
                    entries.append({"type": "block_anno", "text": txt})
                    continue
                entries.append({"type": "section", "text": txt})
                continue
            if nl.type == "name":
                try:
                    cp = int(nl.codepoint, 16)
                except ValueError:
                    continue
                if not (block.start_cp <= cp <= block.end_cp):
                    continue
                prev_cp = None
                has_section_between = False
                for e in reversed(entries):
                    if e["type"] == "char":
                        prev_cp = int(e["codepoint"], 16)
                        break
                    if e["type"] == "section":
                        has_section_between = True
                        break
                if prev_cp is not None and not has_section_between:
                    for g in range(prev_cp + 1, cp):
                        if g not in assigned:
                            entries.append({"type": "reserved", "codepoint": f"{g:04X}", "name": "<reserved>"})
                fc = self.font_map.get(cp)
                glyph_char = self.fm.resolve_glyph_char(cp, fc) if fc else ""
                entries.append(
                    {
                        "type": "char",
                        "codepoint": nl.codepoint,
                        "name": nl.name,
                        "glyph_char": glyph_char,
                        "font_name": fc.font_name if fc else "",
                        "is_combining": cp in COMB,
                    }
                )
                for a in nl.annotations:
                    if a.type == "cross_ref":
                        if a.target_cp and a.target_name:
                            entries.append({"type": "annotation", "text": f"x ({a.target_name} - {a.target_cp})"})
                        elif a.target_cp:
                            entries.append({"type": "annotation", "text": f"\u2192 {a.target_cp}"})
                        else:
                            entries.append({"type": "annotation", "text": f"\u2192 {a.target_name}"})
                    elif a.type == "alias":
                        entries.append({"type": "annotation", "text": f"= {a.text}"})
                    elif a.type == "formal_alias":
                        entries.append({"type": "annotation", "text": f"% {a.name}"})
                    elif a.type == "comment":
                        entries.append(
                            {
                                "type": "annotation",
                                "text": f"* {a.text}" if a.text.startswith(" ") or a.text[0].isalnum() else a.text,
                            }
                        )
                    elif a.type == "decomposition":
                        tag = f"{a.mapping_tag} " if a.mapping_tag else ""
                        entries.append({"type": "annotation", "text": f": {tag}{a.mapping_text}"})
                    elif a.type == "compat_mapping":
                        tag = f"{a.mapping_tag} " if a.mapping_tag else ""
                        entries.append({"type": "annotation", "text": f"# {tag}{a.mapping_text}"})
                    elif a.type == "variation":
                        entries.append(
                            {"type": "annotation", "text": f"~ {a.codepoint} {a.var_selector} {a.var_label}"}
                        )
                    else:
                        entries.append({"type": "annotation", "text": a.text or a.name or ""})
        return entries

    # -- Header --------------------------------------------

    def _add_header(self, page, pt, first_cp=None, last_cp=None):
        block = self.block
        if first_cp is None:
            first_cp = block.start_cp
        if last_cp is None:
            last_cp = block.end_cp
        g = _grid
        xs = shift_x(82.80, pt)
        xn = shift_x(285.90, pt)
        if block and block.draft_mode:
            start_text = block.format_draft_cp(block.draft_cp(first_cp))
            end_text = block.format_draft_cp(block.draft_cp(last_cp))
        else:
            start_text = f"{first_cp:04X}"
            end_text = f"{last_cp:04X}"
        end_w = measure_text(FONT_INFO_HEADER[0], FONT_INFO_HEADER[1], end_text)
        xe = shift_x(g.info_header_right - end_w, pt)
        page.text_spans.append(
            TextSpan(
                text=start_text,
                font=FONT_INFO_HEADER[0],
                size=FONT_INFO_HEADER[1],
                origin=[xs, g.header_y],
                bbox=[xs, 36, xs + 24, 47],
            )
        )
        page.text_spans.append(
            TextSpan(
                text=block.name,
                font=FONT_INFO_HEADER[0],
                size=FONT_INFO_HEADER[1],
                origin=[xn, g.header_y],
                bbox=[xn, 36, xn + 40, 47],
            )
        )
        page.text_spans.append(
            TextSpan(
                text=end_text,
                font=FONT_INFO_HEADER[0],
                size=FONT_INFO_HEADER[1],
                origin=[xe, g.header_y],
                bbox=[xe, 36, xe + end_w, 47],
            )
        )
        page.drawings.append(Drawing.rect(xe, 34.14, end_w, 13.62))
        page.drawings.append(Drawing.rect(xn, 34.14, 40.20, 13.62))
        page.drawings.append(Drawing.rect(xs, 34.14, 24.48, 13.62))

    # -- Column layout -------------------------------------

    def _display_cp_str(self, original_cp_str: str) -> str:
        """Convert an original codepoint hex string to draft format if draft_mode."""
        block = self.block
        if block and block.draft_mode:
            try:
                cp = int(original_cp_str, 16)
                return block.format_draft_cp(block.draft_cp(cp))
            except ValueError:
                return original_cp_str
        return original_cp_str

    def _column_params(self, is_col2: bool, pt: PageType) -> dict:
        p = self.cfg.column_params(is_col2)
        return {
            "cx": shift_x(p["cp_x"], pt),
            "gx": shift_x(p["glyph_x"], pt),
            "nx": shift_x(p["name_x"], pt),
            "mw": p["max_w"],
            "glyph_col_w": p["glyph_col_w"],
            "right": shift_x(p["right"], pt),
        }

    def _add_col(self, page, entries, is_col2, pt, font_map=None, start_y=None):
        """Render one column of info entries. Returns count of rendered entries."""
        cp = self._column_params(is_col2, pt)
        cx, gx, nx, mw, glyph_col_w, right = cp["cx"], cp["gx"], cp["nx"], cp["mw"], cp["glyph_col_w"], cp["right"]
        y = start_y if start_y is not None else self.cfg.first_y
        cfg = self.cfg
        fm = self.fm
        fm_font_map = font_map or self.font_map

        for idx, e in enumerate(entries):
            t = e["type"]
            if y > self.cfg.col_switch_y - 25 and t == "section":
                return idx
            if y > self.cfg.col_switch_y:
                return idx
            extra = 0
            if t == "block_anno":
                page.text_spans.append(
                    TextSpan(
                        text=e["text"],
                        font=FONT_ANNO[0],
                        size=FONT_ANNO[1],
                        origin=[cx, y],
                        bbox=[cx, y - 7.5, cx + 200, y + 1.5],
                    )
                )
            elif t == "section":
                y += 3.4
                page.text_spans.append(
                    TextSpan(
                        text=e["text"],
                        font=FONT_SECTION[0],
                        size=FONT_SECTION[1],
                        origin=[cx, y],
                        bbox=[cx, y - 7.5, cx + 300, y + 1.5],
                    )
                )
            elif t == "reserved":
                cp_display = self._display_cp_str(e["codepoint"])
                page.text_spans.append(
                    TextSpan(
                        text=cp_display,
                        font=FONT_CP[0],
                        size=FONT_CP[1],
                        origin=[cx, y],
                        bbox=[cx, y - 7.5, cx + 17, y + 1.5],
                    )
                )
                page.text_spans.append(
                    TextSpan(
                        text='"',
                        font=FONT_RESERVED_MARKER[0],
                        size=FONT_RESERVED_MARKER[1],
                        origin=[gx, y],
                        bbox=[gx, y - 8, gx + 5, y + 2],
                    )
                )
                page.text_spans.append(
                    TextSpan(
                        text="<reserved>",
                        font=FONT_RESERVED[0],
                        size=FONT_RESERVED[1],
                        origin=[nx, y],
                        bbox=[nx, y - 7.5, nx + 50, y + 1.5],
                    )
                )
            elif t == "char":
                cp_display = self._display_cp_str(e["codepoint"])
                cp_label_w = fm.measure(FONT_CP[0], FONT_CP[1], cp_display)
                page.text_spans.append(
                    TextSpan(
                        text=cp_display,
                        font=FONT_CP[0],
                        size=FONT_CP[1],
                        origin=[cx, y],
                        bbox=[cx, y - 7.5, cx + cp_label_w, y + 1.5],
                    )
                )
                if e.get("is_combining"):
                    page.text_spans.append(
                        TextSpan(
                            text="$",
                            font=FONT_INFO_DOLLAR[0],
                            size=FONT_INFO_DOLLAR[1],
                            origin=[gx, y],
                            bbox=[gx, y - 8, gx + 5, y + 2],
                        )
                    )
                    if e["glyph_char"] and e["font_name"]:
                        page.text_spans.append(
                            TextSpan(
                                text=e["glyph_char"],
                                font=e["font_name"],
                                size=10.0,
                                origin=[gx + DOLLAR_GLYPH_GAP, y + cfg.glyph_y_adjust],
                                bbox=[
                                    gx + DOLLAR_GLYPH_GAP,
                                    y - 8 + cfg.glyph_y_adjust,
                                    gx + DOLLAR_GLYPH_GAP + 8,
                                    y + 2 + cfg.glyph_y_adjust,
                                ],
                            )
                        )
                elif e["glyph_char"] and e["font_name"]:
                    glyph_center = fm.glyph_visual_center(e["font_name"], 9.0, e["glyph_char"])
                    col_center = gx + glyph_col_w / 2 - 4.0
                    glyph_x = col_center - glyph_center
                    page.text_spans.append(
                        TextSpan(
                            text=e["glyph_char"],
                            font=e["font_name"],
                            size=9.0,
                            origin=[glyph_x, y + cfg.glyph_y_adjust],
                            bbox=[glyph_x, y - 8 + cfg.glyph_y_adjust, glyph_x + 8, y + 1.5 + cfg.glyph_y_adjust],
                        )
                    )
                self._info_wrap(page, e["name"], FONT_NAME, nx, y, mw, fm=fm)
                extra = self._info_extra(e["name"], FONT_NAME, mw, fm=fm)
            elif t == "annotation":
                txt = e["text"]
                if txt.startswith("\u2192"):
                    extra = self._render_xref(page, txt, cx, gx, nx, y, fm_font_map, right)
                elif txt.startswith("x "):
                    extra = self._render_xline(page, txt, cx, gx, nx, y, fm_font_map, right)
                elif txt.startswith("* "):
                    page.text_spans.append(
                        TextSpan(
                            text="\u2022",
                            font=FONT_BULLET[0],
                            size=FONT_BULLET[1],
                            origin=[nx, y],
                            bbox=[nx, y - 8, nx + 6, y + 2],
                        )
                    )
                    self._info_wrap(page, " " + txt[2:], FONT_BULLET_TEXT, nx + 4, y, mw - 4, fm=fm)
                    extra = self._info_extra(" " + txt[2:], FONT_BULLET_TEXT, mw - 4, fm=fm)
                else:
                    self._info_wrap(page, txt, FONT_ANNO, nx, y, mw, fm=fm)
                    extra = self._info_extra(txt, FONT_ANNO, mw, fm=fm)
            if t == "block_anno":
                y += cfg.gap_after_blockanno + extra * cfg.line_h
            elif t == "section":
                y += cfg.gap_after_section + extra * cfg.line_h
            else:
                y += cfg.gap_after_regular * (1 + extra)
        return len(entries)

    # -- Cross-reference rendering -------------------------

    def _find_font_for_cp(self, cp, font_map):
        """Look up font for a codepoint: block-limited map first, then full CFL."""
        if cp in font_map:
            return font_map[cp]
        from backend.non_cjk_generation.parsers import find_font_for_codepoint

        return find_font_for_codepoint(self.ctx.cfl_config, cp)

    def _render_xref(self, page, txt, cx, gx, nx, y, font_map, right):
        """Render ->target_cp target_glyph target_name cross-reference.
        Returns number of extra wrapped lines for y-advancement."""
        rest = txt[1:].strip()
        parts = rest.split(None, 1)
        tcp_s = parts[0] if parts else ""
        extra_lines = 0
        cp_x = cx  # fallback: column cp_x; actual codepoint position captured below

        arrow_w = measure_text(FONT_ARROW[0], FONT_ARROW[1], "\u2192")
        page.text_spans.append(
            TextSpan(
                text="\u2192",
                font=FONT_ARROW[0],
                size=FONT_ARROW[1],
                origin=[nx, y],
                bbox=[nx, y - 7.5, nx + arrow_w, y + 1.5],
            )
        )
        cur = nx + arrow_w + 4

        if tcp_s:
            cp_x = cur  # align wraps to this codepoint, not column cx
            cp_w = measure_text(FONT_CP[0], FONT_CP[1], tcp_s)
            page.text_spans.append(
                TextSpan(
                    text=tcp_s,
                    font=FONT_CP[0],
                    size=FONT_CP[1],
                    origin=[cur, y],
                    bbox=[cur, y - 7.5, cur + cp_w, y + 1.5],
                )
            )
            cur += cp_w + 5
            try:
                tc = int(tcp_s, 16)
                fc = self._find_font_for_cp(tc, font_map)
                if fc:
                    glyph_char = chr(tc)
                    glyph_w = self.fm.measure(fc.font_name, 9.0, glyph_char)
                    page.text_spans.append(
                        TextSpan(
                            text=glyph_char,
                            font=fc.font_name,
                            size=9.0,
                            origin=[cur, y + self.cfg.glyph_y_adjust],
                            bbox=[
                                cur,
                                y - 8 + self.cfg.glyph_y_adjust,
                                cur + glyph_w,
                                y + 1.5 + self.cfg.glyph_y_adjust,
                            ],
                        )
                    )
                    cur += glyph_w + 8
            except ValueError:
                pass
            if len(parts) > 1:
                name_w = right - cur
                self._info_wrap(page, parts[1], FONT_NAME, cur, y, name_w, fm=self.fm, wrap_x=cp_x)
                extra_lines = self._info_extra(parts[1], FONT_NAME, name_w, fm=self.fm)
        return extra_lines

    def _render_xline(self, page, txt, cx, gx, nx, y, font_map, right):
        """Render x (name - codepoint) cross-reference.
        Returns number of extra wrapped lines for y-advancement."""
        extra_lines = 0
        m = _RE_XREF.match(txt)
        if m:
            cn = m.group(1).strip()
            ecs = m.group(2).strip()
            page.text_spans.append(
                TextSpan(
                    text="\u2192",
                    font=FONT_ARROW[0],
                    size=FONT_ARROW[1],
                    origin=[nx, y],
                    bbox=[nx, y - 7.5, nx + 8.3, y + 1.5],
                )
            )
            # Dynamic positioning: arrow → CP glyph (name)
            cur = nx + 12
            cp_x = cur  # codepoint position for wrap alignment
            cp_w = measure_text(FONT_XREF_CP[0], FONT_XREF_CP[1], ecs)
            page.text_spans.append(
                TextSpan(
                    text=ecs,
                    font=FONT_XREF_CP[0],
                    size=FONT_XREF_CP[1],
                    origin=[cur, y],
                    bbox=[cur, y - 7.5, cur + cp_w, y + 1.5],
                )
            )
            cur += cp_w + 5  # gap between codepoint and glyph

            try:
                ecp = int(ecs, 16)
                fc = self._find_font_for_cp(ecp, font_map)
                glyph_char = chr(ecp)
            except Exception:
                glyph_char = ""
                fc = None
            if glyph_char:
                gfont = fc.font_name if fc else FONT_XREF_GLYPH[0]
                gsize = 9.0 if fc else FONT_XREF_GLYPH[1]
                gw = self.fm.measure(gfont, gsize, glyph_char) if glyph_char else 10.0
                page.text_spans.append(
                    TextSpan(
                        text=glyph_char,
                        font=gfont,
                        size=gsize,
                        origin=[cur, y + self.cfg.glyph_y_adjust],
                        bbox=[
                            cur,
                            y - 8 + self.cfg.glyph_y_adjust,
                            cur + gw,
                            y + 1.5 + self.cfg.glyph_y_adjust,
                        ],
                    )
                )
                cur += gw + 8
            else:
                cur += 4
            name_w = right - cur
            self._info_wrap(page, cn, FONT_XREF_TEXT, cur, y, name_w, fm=self.fm, wrap_x=cp_x)
            extra_lines = self._info_extra(cn, FONT_XREF_TEXT, name_w, fm=self.fm)
        else:
            self._info_wrap(page, txt, FONT_ANNO, nx, y, right - nx, fm=self.fm)
        return extra_lines

    @staticmethod
    def _info_wrap(page, txt, fi, x, y, mw, fm=None, wrap_x=None):
        if not txt:
            return
        if wrap_x is None:
            wrap_x = x
        fn, fs = fi
        line_h = _info_cfg.line_h
        # Resolve font path for precise wrapping measurement
        font_path = fm.resolve_font_path(fn) if fm else None
        lines = wrap_text(fn, fs, txt, mw, font_path=font_path)
        for i, ln in enumerate(lines):
            lw = fm.measure(fn, fs, ln) if fm else measure_text(fn, fs, ln)
            lx = x if i == 0 else wrap_x
            page.text_spans.append(
                TextSpan(
                    text=ln,
                    font=fn,
                    size=fs,
                    origin=[lx, y + i * line_h],
                    bbox=[lx, y + i * line_h - fs * 0.8, lx + lw, y + i * line_h + fs * 0.2],
                )
            )

    @staticmethod
    def _info_extra(txt, fi, mw, fm=None):
        if not txt:
            return 0
        fn, fs = fi
        font_path = fm.resolve_font_path(fn) if fm else None
        return len(wrap_text(fn, fs, txt, mw, font_path=font_path)) - 1

    # -- Footer --------------------------------------------

    def _add_footer(self, page, pn, pt):
        g = _grid
        xl = shift_x(82.80, pt)
        page_num_text = str(pn)
        page_num_w = measure_text(FONT_INFO_FOOTER[0], FONT_INFO_FOOTER[1], page_num_text)
        xp = shift_x(g.info_footer_right - page_num_w, pt)
        ct = (
            f"The Unicode Standard, Version {self.ctx.short_version}, "
            f"Copyright \u00a9 1991-{self.ctx.year} Unicode, Inc. All rights reserved."
        )
        page.text_spans.append(
            TextSpan(
                text=ct,
                font=FONT_INFO_FOOTER[0],
                size=FONT_INFO_FOOTER[1],
                origin=[xl, g.footer_y],
                bbox=[xl, 741.5, xl + 430, 750.5],
            )
        )
        page.text_spans.append(
            TextSpan(
                text=page_num_text,
                font=FONT_INFO_FOOTER[0],
                size=FONT_INFO_FOOTER[1],
                origin=[xp, g.footer_y],
                bbox=[xp, 741.5, xp + page_num_w, 750.5],
            )
        )
        page.drawings.append(Drawing.rect(xl, 740.46, 327.72, 10.8))
        page.drawings.append(Drawing.rect(xp, 740.46, page_num_w, 10.8))


# -- Top-level info page orchestration ---------------------


def compute_info_pages(
    ctx: LayoutContext,
    font_map: dict[int, FontConfig],
    nameslist: list[NamesListEntry],
    start_page_num: int,
) -> list[Page]:
    """Compute two-column information section pages."""
    builder = InfoPageBuilder(ctx, font_map, nameslist)
    return builder.build_pages(start_page_num)


# ==================================================================->
#  Main entry point
# ==================================================================->


def generate_page_structure(
    cfl_path: str = "",
    nameslist_path: str = "",
    data_tsv_path: str = "",
    block_name: str = "",
    start_cp: int = 0,
    end_cp: int = 0,
    version: str = "17.0.0",
    short_version: str = "17.0",
    year: str = "2025",
    column_count: int = 0,  # 0 = auto-detect from block range
    ucd_path: str = "",
    font_dir: str = "",
    title_md_path: str = "",
    chart_page_base: int = 1,
    title_page_config: TitlePageConfig = None,
    grid_left: float | None = None,
    extra_font_dirs: list[str] | None = None,
    assigned_cps: set[int] | None = None,
    combining_cps: set[int] | None = None,
    chart_fonts: list[FontConfig] | None = None,
    nameslist_entries: list[NamesListEntry] | None = None,
    draft_mode: bool = False,
) -> list[dict]:
    """Generate a complete page_structure.json as a list of page dicts.

    Block info (name, start_cp, end_cp) is auto-detected from the NamesList
    file's ``@@`` header.  Pass explicit values to override.
    Combining marks are auto-detected from UnicodeData.txt (General Category M*).

    Parameters
    ----------
    cfl_path: Path to fonts.cfl
    nameslist_path: Path to NamesList.txt (block name + range auto-detected)
    block_name: Override block name (e.g. "Basic Latin")
    start_cp: Override first codepoint
    end_cp: Override last codepoint
    version: Full Unicode version, e.g. "17.0.0"
    short_version: Short version, e.g. "17.0"
    year: Copyright year
    column_count: Columns in code chart (24 for standard blocks)
    ucd_path: Path to UnicodeData.txt (for assigned codepoint detection)
    font_dir: Path to font files (for glyph bounding box measurement)
    extra_font_dirs: Additional directories to search for font files
        (e.g. block-specific .ttf files alongside block data).
    combining_cps: Set of codepoints that are combining marks (for dotted-circle display)

    Returns
    -------
    List of page dicts, ready for JSON serialization and PDF rendering.
    """
    from backend.non_cjk_generation.parsers import detect_block_from_nameslist

    # -- Resolve data source ------------------------------
    if data_tsv_path and not (chart_fonts and nameslist_entries):
        import os
        import tempfile

        from backend.non_cjk_generation.parsers import split_data_tsv

        nl_text, cfl_text = split_data_tsv(data_tsv_path)
        tmpdir = tempfile.mkdtemp()
        cfl_path = os.path.join(tmpdir, "fonts.cfl")
        nameslist_path = os.path.join(tmpdir, "nameslist.txt")
        with open(cfl_path, "w", encoding="utf-8") as f:
            f.write(cfl_text)
        with open(nameslist_path, "w", encoding="utf-8") as f:
            f.write(nl_text)

    need_files = not (chart_fonts and nameslist_entries)
    if need_files and (not cfl_path or not nameslist_path):
        raise ValueError("Either (cfl_path + nameslist_path) or (chart_fonts + nameslist_entries) is required")

    if not block_name:
        if need_files:
            block_name, start_cp, end_cp = detect_block_from_nameslist(nameslist_path)
        if not block_name:
            raise ValueError("Cannot detect block info; pass block_name/start_cp/end_cp explicitly")
    elif not start_cp:
        raise ValueError("start_cp is required when block_name is provided")

    # Auto-detect column count
    if column_count <= 0:
        column_count = (end_cp >> 4) - (start_cp >> 4) + 1

    block = BlockInfo(
        name=block_name,
        start_cp=start_cp,
        end_cp=end_cp,
        column_count=column_count,
        grid_left=grid_left,
        draft_mode=draft_mode,
    )
    ctx = LayoutContext(
        version=version,
        short_version=short_version,
        short_version_label=short_version,
        year=year,
        block=block,
        font_dir=font_dir,
        extra_font_dirs=extra_font_dirs or [],
        title_md_path=title_md_path,
        chart_page_base=chart_page_base,
        assigned_cps=assigned_cps,
        combining_cps=combining_cps,
    )

    # Parse or use provided CFL / NamesList
    if chart_fonts is not None:
        ctx.cfl_config = chart_fonts
        font_map = find_font_for_range(chart_fonts, start_cp, end_cp)
    else:
        chart_fonts, _common_fonts = parse_cfl(cfl_path)
        ctx.cfl_config = chart_fonts
        font_map = find_font_for_range(chart_fonts, start_cp, end_cp)

    if nameslist_entries is not None:
        block_entries = extract_block_entries(nameslist_entries, start_cp, end_cp)
    else:
        all_entries = parse_nameslist(nameslist_path)
        block_entries = extract_block_entries(all_entries, start_cp, end_cp)
    ctx.nameslist = block_entries

    # Generate pages
    all_pages: list[Page] = []

    if title_page_config is None:
        title_page_config = TitlePageConfig()

    title_page = compute_title_page(ctx, ctx.title_md_path, title_page_config)
    all_pages.append(title_page)

    chart_pages = compute_code_chart_pages(ctx, font_map)

    # -- Combined layout: chart + info on one page ----------
    # Condition: exactly 1 chart page with -> columns (half-page),
    # and info fits in 1 page.
    info_builder = InfoPageBuilder(ctx, font_map, block_entries)
    info_entries_for_count = info_builder._build_entries()
    mr = int((743 - _info_cfg.first_y) / _info_cfg.line_h)
    epp = mr * 2
    info_np = (len(info_entries_for_count) + epp - 1) // epp if info_entries_for_count else 0
    chart_cp = min(ctx.block.column_count, 12)

    if len(chart_pages) == 1 and chart_cp <= 6 and info_np <= 1 and len(info_entries_for_count) <= mr:
        # Auto-set grid_left for left-half positioning if not already set
        if ctx.block.grid_left is None:
            ctx.block.grid_left = PAGE_W / 2 - chart_cp * _grid.cell_w - 64
        # Rebuild chart page with the updated grid_left
        chart_pages = compute_code_chart_pages(ctx, font_map)
        combined = chart_pages[0]

        if info_entries_for_count:
            info_pages = compute_info_pages(ctx, font_map, block_entries, ctx.chart_page_base + 1)
            if info_pages:
                info = info_pages[0]
                # Shift info content to the right half, skipping header/footer
                shift = PAGE_W / 2 - _info_cfg.col1_cp_x
                merged_spans = []
                for s in info.text_spans:
                    if s.origin[1] < _grid.header_y + 10 or s.origin[1] > _grid.footer_y - 10:
                        continue
                    s.origin[0] += shift
                    s.bbox[0] += shift
                    s.bbox[2] += shift
                    merged_spans.append(s)
                for d in info.drawings:
                    for item in d.items:
                        item.x += shift
                        if item.op == "l":
                            item.w += shift
                combined.text_spans.extend(merged_spans)
                combined.drawings.extend(info.drawings)

        all_pages.append(combined)
    else:
        all_pages.extend(chart_pages)
        next_page_num = ctx.chart_page_base + len(chart_pages)
        info_pages = compute_info_pages(ctx, font_map, block_entries, next_page_num)
        all_pages.extend(info_pages)

    structure = PageStructure(pages=all_pages)
    return structure.to_list()
