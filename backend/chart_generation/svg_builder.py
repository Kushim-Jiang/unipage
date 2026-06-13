"""SVG glyph generation from TrueType/OpenType fonts.

Extracts individual glyph outlines and writes them as standalone SVG files.
"""

from __future__ import annotations

from os.path import basename
from re import sub as _sub
from textwrap import dedent
from typing import Any, Optional

from fontTools import ttLib
from fontTools.pens import boundsPen, svgPathPen
from numpy import mean


def _hex_str(val: int) -> str:
    return hex(val).upper().replace("0X", "")


def _resolve_glyph_name(cp: Any, font: ttLib.TTFont, font_cmap: dict) -> tuple[str, str]:
    """Resolve a codepoint/int/tuple to (display_label, glyph_name)."""
    if isinstance(cp, int):
        label = f"\u2039{cp} ({_hex_str(cp)})\u203a"
        glyph_name = font_cmap[cp]
    elif isinstance(cp, (list, tuple)):
        cp_int, sel = int(cp[0]), int(cp[1])
        label = f"\u2039{sel} ({_hex_str(sel)}), {cp_int} ({_hex_str(cp_int)})\u203a"
        uvs_table = font["cmap"].getcmap(0, 5)
        pair = [t for t in uvs_table.uvsDict.get(cp_int, []) if t[0] == sel]
        glyph_name = pair[0][1] if pair else font_cmap.get(sel, ".notdef")
    else:
        label = str(cp)
        glyph_name = font_cmap.get(int(cp), ".notdef")
    return label, glyph_name


def build_svg_glyphs(
    pages: list,
    svg_dir: str,
    progress_callback: Optional[callable] = None,
) -> dict | tuple[str, str]:
    """Generate SVG files for all unique glyphs used across pages.

    Parameters
    ----------
    pages : list
        Each page is ``[cps, rss, glyphs, src_refs, fonts, min_cp, max_cp]``.
    svg_dir : str
        Directory to write SVG files into (trailing slash included).
    progress_callback : callable, optional
        ``fn(progress: float)`` called with 0.0–1.0.

    Returns
    -------
    dict
        ``{(cp, font_tuple) -> (svg_path, glyph_width)}``.
        Also contains ``("fix", font_tuple) -> vertical_offset_correction``.
    tuple
        ``(font_name, cp_str)`` on error (glyph not found in font).
    """
    # Collect unique (glyph, font) pairs
    glyph_set: set = set()
    for page in pages:
        for i in range(len(page[2])):
            data = page[2][i]
            font_key = tuple(page[4][i])
            if isinstance(data, int):
                glyph_set.add((data, font_key))
            elif isinstance(data, (list, tuple)):
                glyph_set.add((tuple(data), font_key))

    # Count glyphs per font for progress
    font_glyph_counts: dict = {}
    for item in glyph_set:
        if item not in (("", ()), ((), ())):
            fnt = item[1]
            font_glyph_counts[fnt] = font_glyph_counts.get(fnt, 0) + 1
    total = sum(font_glyph_counts.values())

    result: dict = {}
    processed = 0

    for font_key in set(item[1] for item in glyph_set if item not in (("", ()), ((), ()))):
        cps = [item[0] for item in glyph_set if item[1] == font_key]
        widths: list[float] = []

        try:
            font = ttLib.TTFont(font_key[1])
            font_cmap = font.getBestCmap()
            font_gs = font.getGlyphSet()
            bp = boundsPen.BoundsPen(font_gs)

            for cp in cps:
                label, glyph_name = _resolve_glyph_name(cp, font, font_cmap)
                glyph = font_gs[glyph_name]
                pen = svgPathPen.SVGPathPen(font_gs)
                glyph.draw(pen)
                glyph.draw(bp)

                asc = font["OS/2"].sTypoAscender
                desc = font["OS/2"].sTypoDescender
                w = glyph.width
                widths.append(w)
                h = asc - desc

                svg = dedent(f"""\
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {-asc} {w} {h}">
                        <g transform="scale(1, -1)">
                            <path d="{pen.getCommands()}"/>
                        </g>
                    </svg>
                """)
                fname = f"{_sub(r'\.', '_', basename(font_key[1]))}" f"_{_sub(r'\.', '_', glyph_name)}.svg"
                fpath = f"{svg_dir}{fname}"
                with open(fpath, "w") as fp:
                    fp.write(svg)

                k = (cp, font_key)
                result[k] = (fpath, w)

                processed += 1
                if progress_callback:
                    progress_callback(processed / total)

        except (KeyError, AttributeError):
            return (font_key[0], label)
        except FileNotFoundError:
            raise  # Propagate — caller handles C009

        if widths:
            fix = (bp.bounds[3] - bp.bounds[1]) / 2 / mean(widths) - 0.25
            result[("fix", font_key)] = fix
        bp.init()

    return result
