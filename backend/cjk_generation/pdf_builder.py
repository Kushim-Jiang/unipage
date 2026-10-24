"""PDF code chart generation using fpdf2 (shared with non-CJK).

Renders proof layouts (produced by ``layout.make_proof``) into
print-ready PDF documents.  Uses fpdf2 for PDF output and cairosvg
for SVG‑glyph → PNG conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Optional

import cairosvg
from fpdf import FPDF

from backend.cjk_generation.fonts import CJKRadicals, LiberationSansNarrow_Regular, use_font
from backend.cjk_generation.layout import CjkPageData
from backend.cjk_generation.svg_builder import build_svg_glyphs
from backend.file_management.parser import ParseError, show_rs
from backend.models.dataclasses import ProofLayout
from backend.pathutil import PROJECT_ROOT, PathLike, require_path, to_str
from backend.non_cjk_generation.models import Drawing, Page, TextSpan
from backend.non_cjk_generation.renderer import register_fonts

# -- Constants -------------------------------------------------------

PDF_W, PDF_H = 612, 792

# Layout geometry
_BLOCK_LEFT, _BLOCK_RIGHT = 82.80, 529.20
_BLOCK_UP, _BLOCK_DOWN = 76.74, 733.08
_FORMAT_SHIFT = 15.96
_NONIVD_RS_GAP = 7
_RS_PART_GAP = 1.2  # space between the radical glyph and its value
_IVD_BLOCK_GAP = 243

# Non-IVD column x positions: codepoint / source reference (both centred on
# these values) and the left edge of the glyph box.  A 40-cell page has six
# glyph columns -- C, C, C, J, K, V -- whose groups the header row is
# centred over.
_NONIVD_X = [101.96, 137.96, 127.96]
_IVD_X = [90, 142.40, 132]
_NONIVD_Y = [116, 98, 108, 106]
_IVD_Y = [124, 131, 138, 107, 114]

# Header positions (distance from page top, matching non-CJK layout)
_HEAD_X = [82.80, 306.77, 528.70]
_HEAD_Y = 44.48
_HEAD_RECT_Y = 34.14
_HEAD_RECT_H = 13.62

# Footer positions (distance from page top)
_FOOTER_Y = 748.77
_FOOTER_RECT_Y = 740.46
_FOOTER_RECT_H = 10.80
_FOOTER_RIGHT = 529.40
_FOOTER_COPY_W = 327.72

_PAGE_LAYOUT: dict[int, tuple[int, float, float, float]] = {
    24: (4, 45, 31.8, 54),
    40: (6, 30.11, 31.8, 54),
    60: (3, 35, 31.8, 54),
    80: (2, 35, 31.8, 54),
    100: (1, 0, 31.8, 54),
}

_TITLE_Y = 90.24


# -- CJK‑specific data types -----------------------------------------


@dataclass
class CjkLayout:
    """Dimension constants for one CJK code chart.

    Derived from ``_PAGE_LAYOUT[char_count]`` and the block range.
    """

    char_count: int
    col_count: int  # cc — number of columns of cells
    row_count: int  # rc — rows per column
    glyph_cols: int  # col_c — glyphs per cell
    glyph_gap: float  # gap_x — horizontal spacing between glyphs in a cell
    row_gy: float  # row_gy — row height (non‑IVD)
    ivd_row_gy: float  # ivd_row_gy — row height (IVD)

    @property
    def is_ivd(self) -> bool:
        return self.char_count == 24

    @property
    def cell_width(self) -> float:
        return (_BLOCK_RIGHT - _BLOCK_LEFT) / self.col_count

    @classmethod
    def from_proof(cls, proof: ProofLayout) -> CjkLayout:
        col_c, gap_x, row_gy, ivd_row_gy = _PAGE_LAYOUT[proof.char_count]
        cc = int(ceil(proof.char_count / 20))
        rc = int(proof.char_count / cc)
        return cls(
            char_count=proof.char_count,
            col_count=cc,
            row_count=rc,
            glyph_cols=col_c,
            glyph_gap=gap_x,
            row_gy=row_gy,
            ivd_row_gy=ivd_row_gy,
        )


@dataclass
class CjkPageContext:
    """Per‑page drawing context bundling layout, shift, and boundaries."""

    layout: CjkLayout
    page_type: str  # "Left" | "Right"
    bx: list[float] = field(default_factory=list)  # column boundary x positions


# -- Helpers ---------------------------------------------------------


def _hex(val: int) -> str:
    return hex(val).upper().replace("0X", "")


def _shift(arr: list, page_type: str) -> list:
    if page_type == "Left":
        return [round(x - _FORMAT_SHIFT, 2) for x in arr]
    if page_type == "Right":
        return [round(x + _FORMAT_SHIFT, 2) for x in arr]
    return list(arr)


def _collect_fonts(pages: list[CjkPageData]) -> set[tuple[str, str]]:
    fonts: set[tuple[str, str]] = set()
    for page in pages:
        for f in page.font_keys:
            # Unused glyph slots hold "" rather than a (name, path) pair.
            if isinstance(f, tuple) and len(f) == 2 and f[0] and f[1]:
                fonts.add(f)
    return fonts


# -- fpdf2 drawing helpers -------------------------------------------


def _put_text(pdf: FPDF, x: float, y: float, text: str, font_name: str, size: float, anchor: str = "start") -> None:
    """Place text at (x, y) in fpdf2 top‑left coordinates; ``x`` follows ``anchor``."""
    if not text:
        return
    use_font(pdf, font_name, size)
    if anchor == "middle":
        x -= pdf.get_string_width(text) / 2
    elif anchor == "end":
        x -= pdf.get_string_width(text)
    pdf.set_text_color(0, 0, 0)
    pdf.text(x, y, text)


def _to_int_rgb(val) -> Optional[tuple[int, int, int]]:
    """Convert a colour value to (r, g, b) ints in 0‑255."""
    if val is None:
        return None
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        return (int(val[0] * 255), int(val[1] * 255), int(val[2] * 255))
    if isinstance(val, (int, float)):
        v = int(val)
        return ((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)
    return None


# -- fpdf2 Page renderer (reuses non‑CJK Page model) -----------------


def _render_page(pdf: FPDF, page: Page) -> None:
    """Render a ``Page`` object with fpdf2.  Coordinates use top‑left origin."""
    # Phase 1: filled rectangles
    for drawing in page.drawings:
        items = drawing.items
        if not items:
            continue
        fill_rgb = _to_int_rgb(drawing.fill)
        stroke_rgb = _to_int_rgb(drawing.color)
        if stroke_rgb is not None or fill_rgb is None:
            continue
        for item in items:
            if item.op == "re":
                pdf.set_fill_color(*fill_rgb)
                pdf.set_line_width(0)
                pdf.rect(item.x, item.y, item.w, item.h, "F")

    # Phase 2: strokes / borders
    for drawing in page.drawings:
        items = drawing.items
        if not items:
            continue
        stroke_rgb = _to_int_rgb(drawing.color)
        fill_rgb = _to_int_rgb(drawing.fill)
        if stroke_rgb is None:
            continue
        w = max(drawing.width or 0.25, 0.1)
        for item in items:
            if item.op == "l":
                pdf.set_draw_color(*stroke_rgb)
                pdf.set_line_width(w)
                pdf.line(item.x, item.y, item.w, item.h)
            elif item.op == "re":
                if fill_rgb:
                    pdf.set_fill_color(*fill_rgb)
                pdf.set_draw_color(*stroke_rgb)
                style = "FD" if fill_rgb else "D"
                pdf.set_line_width(w)
                pdf.rect(item.x, item.y, item.w, item.h, style)

    # Phase 3: text
    pdf.set_text_color(0, 0, 0)
    for span in page.text_spans:
        text = span.text
        if not text or text == " ":
            continue
        _put_text(pdf, span.origin[0], span.origin[1], text, span.font, span.size, span.anchor)


# -- Title page ------------------------------------------------------


def _draw_title_page(pdf: FPDF, proof: ProofLayout, version: str = "17.0", year: str = "2025") -> None:
    """Draw a title page using the non‑CJK ``compute_title_page`` path."""
    from backend.non_cjk_generation.layout import compute_title_page
    from backend.non_cjk_generation.models import BlockInfo, LayoutContext, TitlePageConfig

    block = BlockInfo(name=proof.name, start_cp=proof.start_cp, end_cp=proof.end_cp)
    ctx = LayoutContext(
        version=f"{version}.0",
        short_version=version,
        year=year,
        block=block,
    )
    title_page = compute_title_page(ctx, cfg=TitlePageConfig())
    _render_page(pdf, title_page)


# -- Chart page layout builders (populate Page objects) --------------


def _add_grid_to_page(page: Page, proof: ProofLayout, data: CjkPageData, ctx: CjkPageContext) -> None:
    """Add grid lines and column headers to *page*."""
    lay = ctx.layout
    if data.codepoints[0]:
        page.drawings.append(Drawing.line(ctx.bx[0], _BLOCK_UP - 0.5, ctx.bx[0], _BLOCK_DOWN + 0.5, 1.0))
    for i in range(lay.col_count):
        if not data.codepoints[lay.row_count * i]:
            continue
        x1, x2 = ctx.bx[i], ctx.bx[i + 1]
        page.drawings.append(Drawing.line(x2, _BLOCK_UP - 0.5, x2, _BLOCK_DOWN + 0.5, 1.0))
        page.drawings.append(Drawing.line(x1, _BLOCK_UP, x2, _BLOCK_UP, 1.0))
        page.drawings.append(Drawing.line(x1, _BLOCK_DOWN, x2, _BLOCK_DOWN, 1.0))
        if lay.char_count == 40:
            page.drawings.append(Drawing.line(x1, _TITLE_Y, x2, _TITLE_Y, 1.0))
            # Each label sits over the column it names: HEX over the codepoint
            # column, C/J/K/V over the middle column of their group of the
            # six glyph columns (C, C, C, J, K, V).
            nx = _shift(_NONIVD_X, ctx.page_type)
            head_x = [nx[0]] + [nx[1] + g * lay.glyph_gap for g in (1, 3, 4, 5)]
            for j, lab in enumerate(["HEX", "C", "J", "K", "V"]):
                page.text_spans.append(
                    TextSpan.make(
                        lab,
                        "LiberationSans-Regular",
                        11,
                        head_x[j] + i * lay.cell_width,
                        86.88,
                        anchor="middle",
                    )
                )


def _add_header_to_page(page: Page, proof: ProofLayout, data: CjkPageData, ctx: CjkPageContext) -> None:
    """Add header text + white rect borders to *page*."""
    hx = _shift(_HEAD_X, ctx.page_type)

    page.text_spans.append(TextSpan.make(data.min_cp, "OpenSans-Bold", 11, hx[0], _HEAD_Y))
    page.drawings.append(Drawing.rect(hx[0], _HEAD_RECT_Y, 24.48, _HEAD_RECT_H))

    page.text_spans.append(TextSpan.make(proof.name, "OpenSans-Bold", 11, hx[1], _HEAD_Y))
    page.drawings.append(Drawing.rect(hx[1] - 80, _HEAD_RECT_Y, 160, _HEAD_RECT_H))

    page.text_spans.append(TextSpan.make(data.max_cp, "OpenSans-Bold", 11, hx[2], _HEAD_Y))
    page.drawings.append(Drawing.rect(hx[2] - 40, _HEAD_RECT_Y, 40, _HEAD_RECT_H))


def _add_footer_to_page(
    page: Page, pg_idx: int, ctx: CjkPageContext, version: str = "17.0", year: str = "2025"
) -> None:
    """Add footer text + white rect borders to *page*."""
    fx = _shift([_HEAD_X[0], _FOOTER_RIGHT], ctx.page_type)
    copyright_text = (
        f"The Unicode Standard, Version {version}, " f"Copyright \u00a9 1991-{year} Unicode, Inc. All rights reserved."
    )
    page_text = f"\u2014  {pg_idx + 1}  \u2014"

    page.text_spans.append(TextSpan.make(copyright_text, "OpenSans-Italic", 9, fx[0], _FOOTER_Y))
    page.drawings.append(Drawing.rect(fx[0], _FOOTER_RECT_Y, _FOOTER_COPY_W, _FOOTER_RECT_H))

    page.text_spans.append(TextSpan.make(page_text, "LiberationSans-Regular", 9, fx[1], _FOOTER_Y))
    page.drawings.append(Drawing.rect(fx[1] - 60, _FOOTER_RECT_Y, 60, _FOOTER_RECT_H))


def _add_content_to_page(page: Page, proof: ProofLayout, data: CjkPageData, ctx: CjkPageContext) -> None:
    """Add codepoint / RS / source labels to *page*."""
    lay = ctx.layout
    is_ivd = lay.is_ivd
    nx = _shift(_NONIVD_X, ctx.page_type)
    ix = _shift(_IVD_X, ctx.page_type)
    ny = _NONIVD_Y if lay.char_count != 40 else [round(y + 8, 2) for y in _NONIVD_Y]
    iy = _IVD_Y
    cw = lay.cell_width

    for bi in range(lay.col_count):
        for li in range(lay.row_count):
            idx = li + bi * lay.row_count
            if not is_ivd:
                page.text_spans.append(
                    TextSpan.make(
                        str(data.codepoints[idx]),
                        "LiberationSans-Regular",
                        10,
                        nx[0] + bi * cw,
                        ny[1] + li * lay.row_gy,
                        anchor="middle",
                    )
                )
                for ri, rs_val in enumerate(data.rs_values[idx]):
                    rs_text = show_rs(rs_val)
                    rs_y = ny[2] + li * lay.row_gy + ri * _NONIVD_RS_GAP
                    if rs_text and "\u3000" in rs_text:
                        # Radical glyph (CJKRadicals) + value (Narrow), centred
                        # on the codepoint column as a single unit.
                        radical, number = rs_text.split("\u3000", 1)
                        mid = nx[0] + bi * cw
                        page.text_spans.append(
                            TextSpan.make(radical, CJKRadicals, 6, mid - _RS_PART_GAP / 2, rs_y, anchor="end")
                        )
                        page.text_spans.append(
                            TextSpan.make(
                                number,
                                LiberationSansNarrow_Regular,
                                6,
                                mid + _RS_PART_GAP / 2,
                                rs_y,
                                anchor="start",
                            )
                        )
                    elif rs_text:
                        page.text_spans.append(
                            TextSpan.make(
                                rs_text,
                                LiberationSansNarrow_Regular,
                                6,
                                nx[0] + bi * cw,
                                rs_y,
                                anchor="middle",
                            )
                        )
            else:
                page.text_spans.append(
                    TextSpan.make(
                        str(data.codepoints[idx]),
                        "LiberationSans-Regular",
                        10,
                        ix[0] + bi * _IVD_BLOCK_GAP,
                        iy[3] + li * lay.ivd_row_gy,
                        anchor="middle",
                    )
                )

            for si in range(lay.glyph_cols):
                gi = si + li * lay.glyph_cols + bi * lay.row_count * lay.glyph_cols
                if is_ivd:
                    if data.glyph_ids[gi] != "":
                        page.text_spans.append(
                            TextSpan.make(
                                _hex(data.glyph_ids[gi][0]),
                                "LiberationSans-Regular",
                                6,
                                ix[1] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP,
                                iy[0] + li * lay.ivd_row_gy,
                                anchor="middle",
                            )
                        )
                    if data.source_labels[gi] != "":
                        page.text_spans.append(
                            TextSpan.make(
                                data.source_labels[gi][1],
                                "LiberationSansNarrow-Regular",
                                6,
                                ix[1] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP,
                                iy[1] + li * lay.ivd_row_gy,
                                anchor="middle",
                            )
                        )
                        page.text_spans.append(
                            TextSpan.make(
                                data.source_labels[gi][0],
                                "LiberationSansNarrow-Regular",
                                6,
                                ix[1] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP,
                                iy[2] + li * lay.ivd_row_gy,
                                anchor="middle",
                            )
                        )
                else:
                    page.text_spans.append(
                        TextSpan.make(
                            data.source_labels[gi],
                            "LiberationSansNarrow-Regular",
                            6,
                            nx[1] + si * lay.glyph_gap + bi * cw,
                            ny[0] + li * lay.row_gy,
                            anchor="middle",
                        )
                    )


def _collect_glyph_images(proof: ProofLayout, data: CjkPageData, ctx: CjkPageContext) -> list[dict]:
    """Convert SVG glyphs → PNG bytes for fpdf2 embedding.

    Returns list of ``{"x","y","w","h","data"}`` dicts in fpdf2 top‑left coords.
    """
    lay = ctx.layout
    is_ivd = lay.is_ivd
    nx = _shift(_NONIVD_X, ctx.page_type)
    ix = _shift(_IVD_X, ctx.page_type)
    ny = _NONIVD_Y if lay.char_count != 40 else [round(y + 8, 2) for y in _NONIVD_Y]
    iy = _IVD_Y
    cw = lay.cell_width
    gd = proof.glyph_dict
    GS = 21  # glyph image size (pt)

    images: list[dict] = []
    for bi in range(lay.col_count):
        for li in range(lay.row_count):
            for si in range(lay.glyph_cols):
                gi = si + li * lay.glyph_cols + bi * lay.row_count * lay.glyph_cols
                g_key = data.glyph_ids[gi]
                f_key = tuple(data.font_keys[gi])
                lookup = gd.get((tuple(g_key) if is_ivd else g_key, f_key))
                if lookup is None or lookup[0] is None:
                    continue

                svg_path, advance, em_height = lookup
                fix = gd.get(("fix", tuple(data.font_keys[gi])), 0)

                # Keep the em box aspect: a 21pt-wide box is (em/w) tall.
                ratio = em_height / advance if advance else 1.0
                height = GS * ratio
                try:
                    png_data = cairosvg.svg2png(
                        url=to_str(svg_path),
                        output_width=int(GS * 4),
                        output_height=max(1, round(GS * 4 * ratio)),
                    )
                except Exception:
                    continue

                # Anchor the em box by its bottom (baseline-ish), like the
                # pre-WebUI renderer did, and grow upwards from there.
                if not is_ivd:
                    x = nx[2] + si * lay.glyph_gap + bi * cw
                    y_bottom = ny[3] + li * lay.row_gy + GS * fix
                else:
                    x = ix[2] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP
                    y_bottom = iy[4] + li * lay.ivd_row_gy + GS * fix

                images.append({"x": x, "y": y_bottom - height, "w": GS, "h": height, "data": png_data})
    return images


# ==================================================================
# Public API
# ==================================================================


def generate_pdf(
    proof: ProofLayout,
    output_dir: PathLike,
    progress_callback: Optional[callable] = None,
    version: str = "17.0",
    year: str = "2025",
) -> str:
    """Generate a PDF file from a ProofLayout using fpdf2."""
    from backend.models.dataclasses import BugEntry

    out_dir = require_path(output_dir, "output_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = out_dir / f"{proof.name}.pdf"
    pdf_path.touch()

    lay = CjkLayout.from_proof(proof)

    # Convert raw pages → typed pages (compat with ProofLayout.print_pages: list)
    pages_data = [CjkPageData.from_raw(p) for p in proof.print_pages]

    # Build SVG glyphs
    from backend.models.state import STATE

    proj = STATE.project
    svg_dir = require_path(proj.project_info.project_dir, "project_dir") / "svg" if proj else out_dir / "svg"
    svg_dir.mkdir(parents=True, exist_ok=True)

    glyph_dict = build_svg_glyphs(pages_data, svg_dir, progress_callback)
    if isinstance(glyph_dict, tuple):
        raise ParseError(BugEntry(0, "C008", proof.name, f"Font {glyph_dict[0]} missing glyph for {glyph_dict[1]}."))
    glyph_dict[("", ())] = (None, None, None)
    glyph_dict[((), ())] = (None, None, None)
    proof.glyph_dict = glyph_dict

    # Font directory for registration
    font_dir = require_path(proj.project_info.project_dir, "project_dir") if proj else out_dir
    font_set = _collect_fonts(pages_data)
    extra_fonts = [(f[0], "", Path(f[1]).name) for f in font_set if f[1]]

    # -- Create PDF ----------------------------------------------
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    register_fonts(
        pdf,
        font_dir,
        extra_fonts=extra_fonts,
        extra_font_dirs=[font_dir / "data" / "fonts", PROJECT_ROOT / "data" / "fonts"],
    )

    # -- Title page ----------------------------------------------
    if proof.page_title:
        pdf.add_page()
        _draw_title_page(pdf, proof, version=version, year=year)

    # -- Chart pages ---------------------------------------------
    for pg_idx, data in enumerate(pages_data):
        pt = proof.page_class[pg_idx % 2]
        bx = _shift(
            [
                round(_BLOCK_LEFT + i * (_BLOCK_RIGHT - _BLOCK_LEFT) / lay.col_count, 2)
                for i in range(lay.col_count + 1)
            ],
            pt,
        )
        ctx = CjkPageContext(layout=lay, page_type=pt, bx=bx)

        page = Page(page_num=pg_idx + 1)

        if not lay.is_ivd:
            _add_grid_to_page(page, proof, data, ctx)

        _add_header_to_page(page, proof, data, ctx)
        _add_footer_to_page(page, pg_idx, ctx, version=version, year=year)
        _add_content_to_page(page, proof, data, ctx)

        images = _collect_glyph_images(proof, data, ctx)

        pdf.add_page()
        _render_page(pdf, page)

        # Overlay glyph images
        for img in images:
            try:
                pdf.image(BytesIO(img["data"]), x=img["x"], y=img["y"], w=img["w"], h=img["h"])
            except Exception:
                pass

    # -- Output --------------------------------------------------
    pdf.output(to_str(pdf_path))
    print(f"Saved: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
    print("Done!")

    return to_str(pdf_path)
