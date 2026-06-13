"""PDF code chart generation using ReportLab.

Renders proof layouts (produced by ``layout.make_proof``) into
print-ready PDF documents with SVG glyphs embedded.
"""

from __future__ import annotations

from datetime import datetime
from math import ceil
from os import makedirs
from os.path import exists
from typing import Optional

from fontTools import ttLib
from reportlab.graphics import renderPDF, shapes
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from backend.chart_generation.svg_builder import build_svg_glyphs
from backend.file_management.parser import ParseError, show_rs

# ── Constants ───────────────────────────────────────────────────────

PDF_W, PDF_H = 612, 792

NOTO = {
    "regular": "Noto Sans Regular",
    "black": "Noto Sans Black",
    "italic": "Noto Sans Italic",
    "extra_cond": "Noto Sans Extra Condensed",
    "light": "Noto Sans Light",
}

_NOTO_PATHS = [
    (NOTO["regular"], "fonts/NotoSans-Regular.ttf"),
    (NOTO["black"], "fonts/NotoSans-Black.ttf"),
    (NOTO["italic"], "fonts/NotoSans-Italic.ttf"),
    (NOTO["extra_cond"], "fonts/NotoSans-ExtraCondensed.ttf"),
    (NOTO["light"], "fonts/NotoSans-Light.ttf"),
]

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
_HEAD_X = [83.33, 306.77, 530.21, 538.04]
_HEAD_Y = [45, 749, 772]

_PAGE_LAYOUT = {
    24: (4, 45, 31.8, 54),
    40: (6, 30.11, 31.8, 54),
    60: (3, 35, 31.8, 54),
    80: (2, 35, 31.8, 54),
    100: (1, 0, 31.8, 54),
}

_TITLE_X_40 = [101.96, 166.66, 226.34, 257.52, 287.49, 325.16, 389.86, 449.54, 480.72, 510.69]
_TITLE_Y = 90.24


def _hex(val: int) -> str:
    return hex(val).upper().replace("0X", "")


def _shift(arr: list, page_type: str) -> list:
    if page_type == "Left":
        return [round(x - _FORMAT_SHIFT, 2) for x in arr]
    if page_type == "Right":
        return [round(x + _FORMAT_SHIFT, 2) for x in arr]
    return list(arr)


# ── Font registration ──────────────────────────────────────────────


def _register_noto():
    for name, path in _NOTO_PATHS:
        pdfmetrics.registerFont(ttfonts.TTFont(name, path))


def _collect_fonts(pages: list) -> set:
    fonts = set()
    for page in pages:
        for f in page[4]:
            fonts.add(f)
    fonts.discard("")
    return fonts


# ── Title page ──────────────────────────────────────────────────────


def _build_title_lines(proof, fonts: set) -> list:
    lines = [
        [proof.name, 80, 80, 11, NOTO["black"]],
        [f"Range: {_hex(proof.start_cp)} \u2013 {_hex(proof.end_cp)}", 0, 13, 9, NOTO["black"]],
        [
            "This file contains the codepoints, the reference glyphs and " "the other information of characters in",
            0,
            20,
            9,
            NOTO["light"],
        ],
    ]
    suffix = "the database." if proof.char_count == 24 else "the blocks."
    lines.append([suffix, 0, 11, 9, NOTO["light"]])

    for section in (
        ["Disclaimer", 0, 23, 9, NOTO["black"]],
        [
            "These charts are intended to show the code point, the character name " "(if not inferable) and other",
            0,
            13,
            9,
            NOTO["light"],
        ],
        [
            "partial information of the characters only, and do not indicate the " "character set model and exact",
            0,
            11,
            9,
            NOTO["light"],
        ],
        [
            "understanding of each character for any scripts involved. For a complete " "understanding of the use",
            0,
            11,
            9,
            NOTO["light"],
        ],
        [
            "of the characters contained in this file, please consult the specification, " "the technical notes,",
            0,
            11,
            9,
            NOTO["light"],
        ],
        ["the annexes or the proposals associated.", 0, 11, 9, NOTO["light"]],
        ["Fonts", 0, 23, 9, NOTO["black"]],
        [
            "The shapes of the reference glyphs used in these code charts are " "not prescriptive. Considerable",
            0,
            13,
            9,
            NOTO["light"],
        ],
        [
            "variation is to be expected in actual fonts. The particular fonts "
            "used in these charts are shown below:",
            0,
            11,
            9,
            NOTO["light"],
        ],
        ["", 30, 8, 9, NOTO["light"]],
    ):
        lines.append(section)

    for font in fonts:
        tf = ttLib.TTFont(font[1])
        full = tf["name"].getBestFullName()
        n = tf["name"].names[5]
        style = n.toBytes().decode(n.getEncoding())
        lines.append([full, -15, 11, 9, NOTO["regular"]])
        lines.append([style, 15, 11, 9, NOTO["light"]])

    lines.append(["", -30, 3, 9, NOTO["light"]])
    for t in (
        ["Terms of Use", 0, 23, 9, NOTO["black"]],
        [
            "The code charts are compiled and printed by Unipage software, maintained " "by Kushim Jiang in his",
            0,
            13,
            9,
            NOTO["light"],
        ],
        [
            "public GitHub repository named Unipage, which does not retain copyright " "on the production process.",
            0,
            11,
            9,
            NOTO["light"],
        ],
        [
            "The fonts and font data used in production of these code charts may NOT " "be extracted, or used in",
            0,
            11,
            9,
            NOTO["light"],
        ],
        [
            "any other way in any product or publication, without permission or " "license granted by the typeface",
            0,
            11,
            9,
            NOTO["light"],
        ],
        ["owner(s).", 0, 11, 9, NOTO["light"]],
    ):
        lines.append(t)
    return lines


def _draw_title(cv, proof, fonts):
    dw = shapes.Drawing(PDF_W, PDF_H)
    writer = (0, 0)
    for text, dx, dy, size, font_name in _build_title_lines(proof, fonts):
        writer = (writer[0] + dx, writer[1] + dy)
        dw.add(
            shapes.String(
                writer[0],
                PDF_H - writer[1],
                text,
                textAnchor="start",
                fillColor="black",
                fontName=font_name,
                fontSize=size,
            )
        )
    try:
        renderPDF.draw(dw, cv, 0, 0, showBoundary=False)
    except Exception:
        pass
    cv.showPage()


# ── Page drawing ────────────────────────────────────────────────────


def _draw_grid(dw, proof, page, pt, cc, rc, bx):
    if page[0][0]:
        dw.add(
            shapes.Line(
                bx[0], PDF_H - (_BLOCK_UP - 0.5), bx[0], PDF_H - (_BLOCK_DOWN + 0.5), strokeColor="black", strokeWidth=1
            )
        )
    for i in range(cc):
        if not page[0][rc * i]:
            continue
        x1, x2 = bx[i], bx[i + 1]
        dw.add(
            shapes.Line(
                x2, PDF_H - (_BLOCK_UP - 0.5), x2, PDF_H - (_BLOCK_DOWN + 0.5), strokeColor="black", strokeWidth=1
            )
        )
        dw.add(shapes.Line(x1, PDF_H - _BLOCK_UP, x2, PDF_H - _BLOCK_UP, strokeColor="black", strokeWidth=1))
        dw.add(shapes.Line(x1, PDF_H - _BLOCK_DOWN, x2, PDF_H - _BLOCK_DOWN, strokeColor="black", strokeWidth=1))
        if proof.char_count == 40:
            tx = _shift(_TITLE_X_40, pt)
            dw.add(shapes.Line(x1, PDF_H - _TITLE_Y, x2, PDF_H - _TITLE_Y, strokeColor="black", strokeWidth=1))
            for j, lab in enumerate(["HEX", "C", "J", "K", "V"]):
                dw.add(
                    shapes.String(
                        tx[5 * i + j],
                        PDF_H - 86.88,
                        lab,
                        textAnchor="middle",
                        fillColor="black",
                        fontName=NOTO["regular"],
                        fontSize=11,
                    )
                )


def _draw_header(dw, proof, page, pg_idx, date_s, pt):
    hx = _shift(_HEAD_X, pt)
    dw.add(
        shapes.String(
            hx[1],
            PDF_H - _HEAD_Y[0],
            proof.name,
            textAnchor="middle",
            fillColor="black",
            fontName=NOTO["black"],
            fontSize=11,
        )
    )
    dw.add(
        shapes.String(
            hx[0],
            PDF_H - _HEAD_Y[0],
            page[5],
            textAnchor="start",
            fillColor="black",
            fontName=NOTO["black"],
            fontSize=11,
        )
    )
    dw.add(
        shapes.String(
            hx[2], PDF_H - _HEAD_Y[0], page[6], textAnchor="end", fillColor="black", fontName=NOTO["black"], fontSize=11
        )
    )
    dw.add(
        shapes.String(
            hx[3],
            PDF_H - _HEAD_Y[1],
            f"Printed by Unipage, {date_s}.",
            textAnchor="end",
            fillColor="black",
            fontName=NOTO["italic"],
            fontSize=9,
        )
    )
    dw.add(
        shapes.String(
            hx[1],
            PDF_H - _HEAD_Y[2],
            f"\u2014  {pg_idx + 1}  \u2014",
            textAnchor="middle",
            fillColor="black",
            fontName=NOTO["regular"],
            fontSize=9,
        )
    )


def _draw_content(dw, proof, page, cc, rc, col_c, gap_x, row_gy, ivd_row_gy, pt):
    is_ivd = proof.char_count == 24
    nx = _shift(_NONIVD_X, pt)
    ix = _shift(_IVD_X, pt)
    ny = _NONIVD_Y if proof.char_count != 40 else [round(y + 8, 2) for y in _NONIVD_Y]
    iy = _IVD_Y
    cw = (_BLOCK_RIGHT - _BLOCK_LEFT) / cc

    for bi in range(cc):
        for li in range(rc):
            idx = li + bi * rc
            if not is_ivd:
                dw.add(
                    shapes.String(
                        nx[0] + bi * cw,
                        PDF_H - (ny[1] + li * row_gy),
                        str(page[0][idx]),
                        textAnchor="middle",
                        fillColor="black",
                        fontName=NOTO["regular"],
                        fontSize=10,
                    )
                )
                for ri, rs_val in enumerate(page[1][idx]):
                    dw.add(
                        shapes.String(
                            nx[0] + bi * cw,
                            PDF_H - (ny[2] + li * row_gy + ri * _NONIVD_RS_GAP),
                            show_rs(rs_val),
                            textAnchor="middle",
                            fillColor="black",
                            fontName=NOTO["extra_cond"],
                            fontSize=6,
                        )
                    )
            else:
                dw.add(
                    shapes.String(
                        ix[0] + bi * _IVD_BLOCK_GAP,
                        PDF_H - (iy[3] + li * ivd_row_gy),
                        str(page[0][idx]),
                        textAnchor="middle",
                        fillColor="black",
                        fontName=NOTO["regular"],
                        fontSize=10,
                    )
                )

            for si in range(col_c):
                gi = si + li * col_c + bi * rc * col_c
                if is_ivd:
                    if page[2][gi] != "":
                        dw.add(
                            shapes.String(
                                ix[1] + si * gap_x + bi * _IVD_BLOCK_GAP,
                                PDF_H - (iy[0] + li * ivd_row_gy),
                                _hex(page[2][gi][0]),
                                textAnchor="middle",
                                fillColor="black",
                                fontName=NOTO["regular"],
                                fontSize=6,
                            )
                        )
                    if page[3][gi] != "":
                        dw.add(
                            shapes.String(
                                ix[1] + si * gap_x + bi * _IVD_BLOCK_GAP,
                                PDF_H - (iy[1] + li * ivd_row_gy),
                                page[3][gi][1],
                                textAnchor="middle",
                                fillColor="black",
                                fontName=NOTO["extra_cond"],
                                fontSize=6,
                            )
                        )
                        dw.add(
                            shapes.String(
                                ix[1] + si * gap_x + bi * _IVD_BLOCK_GAP,
                                PDF_H - (iy[2] + li * ivd_row_gy),
                                page[3][gi][0],
                                textAnchor="middle",
                                fillColor="black",
                                fontName=NOTO["extra_cond"],
                                fontSize=6,
                            )
                        )
                else:
                    dw.add(
                        shapes.String(
                            nx[1] + si * gap_x + bi * cw,
                            PDF_H - (ny[0] + li * row_gy),
                            page[3][gi],
                            textAnchor="middle",
                            fillColor="black",
                            fontName=NOTO["extra_cond"],
                            fontSize=6,
                        )
                    )


def _draw_glyphs(cv, proof, page, cc, rc, col_c, gap_x, row_gy, ivd_row_gy, pt):
    is_ivd = proof.char_count == 24
    nx = _shift(_NONIVD_X, pt)
    ix = _shift(_IVD_X, pt)
    ny = _NONIVD_Y if proof.char_count != 40 else [round(y + 8, 2) for y in _NONIVD_Y]
    iy = _IVD_Y
    cw = (_BLOCK_RIGHT - _BLOCK_LEFT) / cc
    gd = proof.glyph_dict

    for bi in range(cc):
        for li in range(rc):
            for si in range(col_c):
                gi = si + li * col_c + bi * rc * col_c
                g_key = page[2][gi]
                f_key = tuple(page[4][gi])
                lookup = gd.get((tuple(g_key) if is_ivd else g_key, f_key))
                if lookup is None or lookup[0] is None:
                    continue

                svg_path, scale = lookup
                drawing = svg2rlg(svg_path)
                drawing.scale(21 / scale, 21 / scale)

                fix = gd.get(("fix", tuple(page[4][gi])), 0)
                if not is_ivd:
                    x = nx[2] + si * gap_x + bi * cw
                    y = PDF_H - (ny[3] + li * row_gy + 21 * fix)
                else:
                    x = ix[2] + si * gap_x + bi * _IVD_BLOCK_GAP
                    y = PDF_H - (iy[4] + li * ivd_row_gy + 21 * fix)

                renderPDF.draw(drawing, cv, x, y)


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════


def generate_pdf(proof, output_dir: str, progress_callback: Optional[callable] = None) -> str:
    """Generate a PDF file from a ProofLayout.

    Parameters
    ----------
    proof : ProofLayout
        Output of ``layout.make_proof``.
    output_dir : str
        Directory to write the PDF into.
    progress_callback : callable, optional
        ``fn(progress: float)``.

    Returns
    -------
    str
        Path to the generated PDF file.

    Raises
    ------
    ParseError
        If a glyph is missing from a font.
    """
    from backend.models.dataclasses import BugEntry

    # Ensure output dir
    if not exists(output_dir):
        makedirs(output_dir, exist_ok=True)

    pdf_path = f"{output_dir}/{proof.name}.pdf"
    open(pdf_path, "w+").close()

    col_c, gap_x, row_gy, ivd_row_gy = _PAGE_LAYOUT[proof.char_count]
    cc = int(ceil(proof.char_count / 20))
    rc = int(proof.char_count / cc)

    # Build SVG glyphs
    from backend.models.state import STATE

    proj = STATE.project
    svg_dir = f"{proj.project_info.project_dir}/svg/" if proj else f"{output_dir}/svg/"
    if not exists(svg_dir):
        makedirs(svg_dir, exist_ok=True)

    glyph_dict = build_svg_glyphs(proof.print_pages, svg_dir, progress_callback)
    if isinstance(glyph_dict, tuple):
        raise ParseError(BugEntry(0, "C008", proof.name, f"Font {glyph_dict[0]} missing glyph for {glyph_dict[1]}."))
    glyph_dict[("", ())] = (None, None)
    glyph_dict[((), ())] = (None, None)
    proof.glyph_dict = glyph_dict

    # Canvas
    cv = canvas.Canvas(pdf_path)
    _register_noto()

    font_set = _collect_fonts(proof.print_pages)
    for font in font_set:
        pdfmetrics.registerFont(ttfonts.TTFont(font[0], font[1]))

    # Title page
    if proof.page_title:
        _draw_title(cv, proof, font_set)

    # Code chart pages
    date_s = str(datetime.today().date())
    for pg_idx, page in enumerate(proof.print_pages):
        pt = proof.page_class[pg_idx % 2]
        dw = shapes.Drawing(PDF_W, PDF_H)
        bx = _shift(
            [round(_BLOCK_LEFT + i * (_BLOCK_RIGHT - _BLOCK_LEFT) / cc, 2) for i in range(cc + 1)],
            pt,
        )

        if proof.char_count != 24:
            _draw_grid(dw, proof, page, pt, cc, rc, bx)

        _draw_header(dw, proof, page, pg_idx, date_s, pt)
        _draw_content(dw, proof, page, cc, rc, col_c, gap_x, row_gy, ivd_row_gy, pt)

        try:
            renderPDF.draw(dw, cv, 0, 0, showBoundary=False)
        except Exception:
            pass

        _draw_glyphs(cv, proof, page, cc, rc, col_c, gap_x, row_gy, ivd_row_gy, pt)

        if pg_idx != len(proof.print_pages) - 1:
            cv.showPage()
        else:
            cv.save()

    return pdf_path
