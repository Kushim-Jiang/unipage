"""PDF code chart generation using fpdf2 (shared with non-CJK).

Renders proof layouts (produced by ``layout.make_proof``) into
print-ready PDF documents.  Uses fpdf2 for PDF output and cairosvg
for SVG‑glyph → PNG conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from math import ceil
from os import makedirs
from os.path import basename, dirname, exists
from typing import Optional

import cairosvg
from fpdf import FPDF

from backend.cjk_generation.fonts import CJKRadicals, LiberationSansNarrow_Regular, use_font
from backend.cjk_generation.layout import CjkPageData
from backend.cjk_generation.svg_builder import build_svg_glyphs
from backend.file_management.parser import ParseError, show_rs
from backend.models.dataclasses import ProofLayout
from backend.non_cjk_generation.models import Drawing, Page, TextSpan
from backend.non_cjk_generation.renderer import register_fonts

# -- Constants -------------------------------------------------------

PDF_W, PDF_H = 612, 792

# Layout geometry
_BLOCK_LEFT, _BLOCK_RIGHT = 82.80, 529.20
_BLOCK_UP, _BLOCK_DOWN = 76.74, 733.08
_FORMAT_SHIFT = 15.96
_NONIVD_RS_GAP = 7
_IVD_BLOCK_GAP = 243

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

_TITLE_X_40 = [101.96, 166.66, 226.34, 257.52, 287.49, 325.16, 389.86, 449.54, 480.72, 510.69]
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
            fonts.add(f)
    fonts.discard(("", ""))
    return fonts


# -- fpdf2 drawing helpers -------------------------------------------


def _put_text(pdf: FPDF, x: float, y: float, text: str, font_name: str, size: float) -> None:
    """Place left-aligned text at (x, y) in fpdf2 top‑left coordinates."""
    if not text:
        return
    use_font(pdf, font_name, size)
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
        _put_text(pdf, span.origin[0], span.origin[1], text, span.font, span.size)


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
            tx = _shift(_TITLE_X_40, ctx.page_type)
            page.drawings.append(Drawing.line(x1, _TITLE_Y, x2, _TITLE_Y, 1.0))
            for j, lab in enumerate(["HEX", "C", "J", "K", "V"]):
                page.text_spans.append(TextSpan.make(lab, "LiberationSans-Regular", 11, tx[5 * i + j], 86.88))


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
                    )
                )
                for ri, rs_val in enumerate(data.rs_values[idx]):
                    rs_text = show_rs(rs_val)
                    if rs_text and "\u3000" in rs_text:
                        radical, number = rs_text.split("\u3000", 1)
                        rx = nx[0] + bi * cw
                        ry = ny[2] + li * lay.row_gy + ri * _NONIVD_RS_GAP
                        page.text_spans.append(TextSpan.make(radical, CJKRadicals, 6, rx, ry))
                        page.text_spans.append(TextSpan.make(number, LiberationSansNarrow_Regular, 6, rx + 7, ry))
                    elif rs_text:
                        page.text_spans.append(
                            TextSpan.make(
                                rs_text,
                                LiberationSansNarrow_Regular,
                                6,
                                nx[0] + bi * cw,
                                ny[2] + li * lay.row_gy + ri * _NONIVD_RS_GAP,
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
                            )
                        )
                        page.text_spans.append(
                            TextSpan.make(
                                data.source_labels[gi][0],
                                "LiberationSansNarrow-Regular",
                                6,
                                ix[1] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP,
                                iy[2] + li * lay.ivd_row_gy,
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

                svg_path, scale = lookup
                fix = gd.get(("fix", tuple(data.font_keys[gi])), 0)

                try:
                    png_data = cairosvg.svg2png(
                        url=svg_path,
                        output_width=int(GS * 4),
                        output_height=int(GS * 4),
                        scale=4,
                    )
                except Exception:
                    continue

                if not is_ivd:
                    x = nx[2] + si * lay.glyph_gap + bi * cw
                    y = ny[3] + li * lay.row_gy + GS * fix
                else:
                    x = ix[2] + si * lay.glyph_gap + bi * _IVD_BLOCK_GAP
                    y = iy[4] + li * lay.ivd_row_gy + GS * fix

                images.append({"x": x, "y": y, "w": GS, "h": GS, "data": png_data})
    return images


# ==================================================================
# Public API
# ==================================================================


def generate_pdf(
    proof: ProofLayout,
    output_dir: str,
    progress_callback: Optional[callable] = None,
    version: str = "17.0",
    year: str = "2025",
) -> str:
    """Generate a PDF file from a ProofLayout using fpdf2."""
    from backend.models.dataclasses import BugEntry

    if not exists(output_dir):
        makedirs(output_dir, exist_ok=True)

    pdf_path = f"{output_dir}/{proof.name}.pdf"
    open(pdf_path, "w+").close()

    lay = CjkLayout.from_proof(proof)

    # Convert raw pages → typed pages (compat with ProofLayout.print_pages: list)
    pages_data = [CjkPageData.from_raw(p) for p in proof.print_pages]

    # Build SVG glyphs
    from backend.models.state import STATE

    proj = STATE.project
    svg_dir = f"{proj.project_info.project_dir}/svg/" if proj else f"{output_dir}/svg/"
    if not exists(svg_dir):
        makedirs(svg_dir, exist_ok=True)

    glyph_dict = build_svg_glyphs(pages_data, svg_dir, progress_callback)
    if isinstance(glyph_dict, tuple):
        raise ParseError(BugEntry(0, "C008", proof.name, f"Font {glyph_dict[0]} missing glyph for {glyph_dict[1]}."))
    glyph_dict[("", ())] = (None, None)
    glyph_dict[((), ())] = (None, None)
    proof.glyph_dict = glyph_dict

    # Font directory for registration
    font_dir = proj.project_info.project_dir if proj else output_dir
    font_set = _collect_fonts(pages_data)
    extra_fonts = [(f[0], "", basename(f[1])) for f in font_set if f[1]]
    # Register CJK Radicals font for RS radical characters
    radicals_ttf = f"{dirname(dirname(dirname(__file__)))}/data/CJKRadicals-Regular.ttf"
    extra_fonts.append((CJKRadicals, "", radicals_ttf))

    # -- Create PDF ----------------------------------------------
    pdf = FPDF(unit="pt", format="letter")
    pdf.set_auto_page_break(False)
    register_fonts(
        pdf,
        font_dir,
        extra_fonts=extra_fonts,
        extra_font_dirs=[f"{font_dir}/data/fonts", f"{dirname(dirname(dirname(__file__)))}/data/fonts"],
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
    pdf.output(pdf_path)
    fsize = __import__("os").path.getsize(pdf_path)
    print(f"Saved: {pdf_path} ({fsize:,} bytes)")
    print("Done!")

    return pdf_path
