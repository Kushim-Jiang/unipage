"""Proof layout — calculates how characters are arranged onto pages.

This is the core of ``make_proof`` from the old ``printer.py``,
extracted into its own module with no UI dependencies.
"""

from __future__ import annotations

from math import ceil
from typing import Optional

from backend.file_management.parser import ParseError, submitter_name, submitter_no
from backend.models.dataclasses import BugEntry, ProofLayout

# ── Column configuration ───────────────────────────────────────────

_COLUMN_MAP = {
    0: (40, 240),  # "2 columns, 6 glyphs each"
    1: (60, 180),  # "3 columns, 3 glyphs each"
    2: (80, 160),  # "4 columns, 2 glyphs each"
    3: (100, 100),  # "5 columns, 1 glyph each"
}

_SRC_GROUP_A = {0, 1, 3, 4, 6, 7}
_SRC_GROUP_B = {2, 5, 8, 9, 10, 11}

_SRC_ORDER_40 = {
    (True, False): [0, 1, 3, 6, 4, 7],
    (False, True): [2, 10, 9, 11, 5, 8],
    (True, True): [0, 1, 3, 6, 4, 7, 2, 10, 9, 11, 5, 8],
}
_SRC_ORDER_DEFAULT = [0, 3, 1, 2, 6, 4, 5, 7, 8, 9, 10, 11]


def _hex_str(val: int) -> str:
    return hex(val).upper().replace("0X", "")


def _extreme_cp(cp_list: list, opt: str) -> str:
    vals = [int(cp, 16) for cp in cp_list if cp]
    if not vals:
        return ""
    return _hex_str(min(vals) if opt == "min" else max(vals))


# ── Column / glyph counts ───────────────────────────────────────────


def get_column_config(blk_setting, blk_type: str) -> tuple[int, int]:
    """Return ``(char_count, glyph_count)`` for a block's settings."""
    if blk_type in ("H", "W"):
        return _COLUMN_MAP[blk_setting.content["column"]]
    if blk_type == "V":
        return (24, 96)
    return (0, 0)


def _compute_line_use(blk_type: str, c_count: int, g_count: int, cp: str, blk_info, cp_submitter: dict) -> int:
    """How many vertical lines a single character occupies."""
    if c_count == 40:
        in_a = bool(cp_submitter.keys() & _SRC_GROUP_A)
        in_b = bool(cp_submitter.keys() & _SRC_GROUP_B)
        return int(in_a) + int(in_b)
    if c_count == 24:
        used = sum(1 for i in blk_info.content.get(cp, []) if any(i))
    else:
        used = sum(1 for i in blk_info.content.get(cp, [None, []])[1] if i)
    return int(ceil(round(used / g_count * c_count, 2)))


def _detect_flag(c_index: int, line_use: int, c_count: int, has_more: bool, blk_type: str) -> int:
    """Determine page-layout flag.

    Returns
    -------
    0 : new page needed
    1 : new column (within page) needed
    2 : continue filling
    3 : last entry, finalize page
    """
    col_size = 12 if blk_type == "V" else 20
    fits_page = (c_index + line_use - 1) % c_count >= c_index

    if not fits_page or c_index >= c_count:
        return 0
    if (c_index % col_size + line_use - 1) % col_size < c_index % col_size:
        return 1
    return 3 if not has_more else 2


# ── Empty page initializer ──────────────────────────────────────────


def _empty_lists(c: int, g: int) -> tuple:
    return ([""] * c, [""] * c, [""] * g, [""] * g, [""] * g)


def _finalize(print_pages: list, lists: tuple, c: int, g: int) -> tuple:
    cp_l, rs_l, gl_l, sr_l, ft_l = lists
    mn = _extreme_cp(cp_l, "min")
    mx = _extreme_cp(cp_l, "max")
    print_pages.append([cp_l, rs_l, gl_l, sr_l, ft_l, mn, mx])
    return _empty_lists(c, g)


def _fill_40(cp, cp_submitter, blk_set, in_a, in_b, gl, sr, ft, ci, gc, cc, name) -> None:
    key = (bool(in_a), bool(in_b))
    src_list = _SRC_ORDER_40.get(key, [])
    for i, src_idx in enumerate(src_list):
        if src_idx not in cp_submitter:
            continue
        temp_fnt, temp_gly, temp_src = cp_submitter[src_idx]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][src_idx][1]), blk_set)
        in_gly = _resolve_glyph((temp_gly, int(cp)), "H")
        if in_fnt == (None, None):
            raise ParseError(BugEntry(0, "C007", name, f"{submitter_name(src_idx)} source"))
        pos = round(ci * gc / cc) + i
        gl[pos], sr[pos], ft[pos] = in_gly, temp_src, in_fnt


def _fill_24(cp, blk_info, blk_set, gl, sr, ft, ci, gc, cc, lu, name) -> None:
    g_info = []
    for entry in blk_info.content.get(cp, []):
        temp_fnt, _, temp_src = entry[1], entry[2], [entry[3], entry[4]]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][1]), blk_set)
        in_gly = _resolve_glyph((entry[0], int(cp)), "V")
        if in_fnt == (None, None):
            raise ParseError(BugEntry(0, "C007", name, "IVD"))
        g_info.append([in_gly, temp_src, in_fnt])
    for i in range(round(lu * gc / cc)):
        if i < len(g_info):
            pos = round(ci * gc / cc + i)
            gl[pos], sr[pos], ft[pos] = g_info[i]


def _fill_default(cp, cp_submitter, blk_set, gl, sr, ft, ci, gc, cc, lu, name) -> None:
    g_info = []
    for src_idx in _SRC_ORDER_DEFAULT:
        if src_idx not in cp_submitter:
            continue
        temp_fnt, temp_gly, temp_src = cp_submitter[src_idx]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][src_idx][1]), blk_set)
        in_gly = _resolve_glyph((temp_gly, int(cp)), "H")
        if in_fnt == (None, None):
            raise ParseError(BugEntry(0, "C007", name, f"{submitter_name(src_idx)} source"))
        g_info.append([in_gly, temp_src, in_fnt])
    for i in range(round(lu * gc / cc)):
        if i < len(g_info):
            pos = round(ci * gc / cc + i)
            gl[pos], sr[pos], ft[pos] = g_info[i]


def _resolve_font(font_info: tuple, blk_set: dict) -> Optional[tuple]:
    """Resolve ``(name, url)`` or ``(None, None)`` if unset."""
    from backend.models.state import STATE

    font_name = font_info[1] if font_info[0] is None else font_info[0]
    if font_name == "(none)":
        return (None, None)
    proj = STATE.project
    if proj is None:
        return (None, None)
    for entry in proj.resources.font:
        if entry.basename == font_name:
            return (font_name, entry.url)
    return (None, None)


def _resolve_glyph(glyph_info: tuple, blk_type: str):
    if blk_type != "V":
        return glyph_info[0] if glyph_info[0] is not None else glyph_info[1]
    return glyph_info


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════


def make_proof(block_name: str) -> tuple[Optional[ProofLayout], list[BugEntry]]:
    """Build a proof for a named block.

    Parameters
    ----------
    block_name : str
        The block name to generate a proof for.

    Returns
    -------
    proof : ProofLayout or None
        ``None`` if the block type is not yet supported (e.g. ``"C"``).
    bugs : list[BugEntry]
        Any bugs encountered during layout.
    """
    from backend.models.state import STATE

    proj = STATE.project
    if proj is None:
        return None, []

    if proj is None:
        return None, []

    blk_set = next((s for s in proj.settings if s.name == block_name), None)
    blk_info = next((b for b in proj.blocks if b.name == block_name), None)
    if blk_set is None or blk_info is None:
        return None, [BugEntry(0, "C000", block_name, "Block not found in project.")]

    blk_type = blk_info.type
    if blk_type == "C":
        return None, []  # C-type not yet supported

    c_count, g_count = get_column_config(blk_set, blk_type)
    c_index = 0
    pages: list = []
    lists = _empty_lists(c_count, g_count)
    cp_l, rs_l, gl_l, sr_l, ft_l = lists

    cps = sorted((int(k) for k in blk_info.content.keys()), reverse=True)
    if not cps:
        return None, []
    cps.append(cps[-1])  # sentinel

    bugs: list[BugEntry] = []

    try:
        while cps:
            cp = str(cps.pop())

            # Build source-ref index
            cp_submitter: dict = {}
            if blk_type != "V":
                for entry in blk_info.content.get(cp, [None, []])[1]:
                    if entry is not None:
                        cp_submitter[submitter_no(entry[-1])] = entry

            lu = _compute_line_use(blk_type, c_count, g_count, cp, blk_info, cp_submitter)
            flag = _detect_flag(c_index, lu, c_count, bool(cps), blk_type)

            if flag == 0:  # New page
                lists = _finalize(pages, lists, c_count, g_count)
                cp_l, rs_l, gl_l, sr_l, ft_l = lists
                c_index = 0
                cps.append(cp)
                continue

            if flag == 1:  # New column
                col_size = 12 if blk_type == "V" else 20
                c_index = col_size * ceil(c_index / col_size)
                cps.append(cp)
                continue

            # Fill current position
            cp_l[c_index] = _hex_str(int(cp))
            if blk_type != "V":
                rs_l[c_index] = blk_info.content.get(cp, [None])[0]
                if rs_l[c_index] is None:
                    raise ParseError(
                        BugEntry(0, "C002", block_name, f"{cp} ({_hex_str(int(cp))}) missing corresponding RS.")
                    )

            if c_count == 40:
                in_a = bool(cp_submitter.keys() & _SRC_GROUP_A)
                in_b = bool(cp_submitter.keys() & _SRC_GROUP_B)
                _fill_40(cp, cp_submitter, blk_set, in_a, in_b, gl_l, sr_l, ft_l, c_index, g_count, c_count, block_name)
            elif c_count == 24:
                _fill_24(cp, blk_info, blk_set, gl_l, sr_l, ft_l, c_index, g_count, c_count, lu, block_name)
            else:
                _fill_default(cp, cp_submitter, blk_set, gl_l, sr_l, ft_l, c_index, g_count, c_count, lu, block_name)

            c_index += lu

            if flag == 3:  # Last entry
                lists = _finalize(pages, (cp_l, rs_l, gl_l, sr_l, ft_l), c_count, g_count)
                cp_l, rs_l, gl_l, sr_l, ft_l = lists

    except ParseError as exc:
        bugs.append(exc.arg)
        return None, bugs
    except Exception as exc:
        bugs.append(BugEntry(0, "C000", block_name, f"{type(exc).__name__}: {exc.args[0]}"))
        return None, bugs

    # Build proof dict
    page_class = [("Right", "Left"), ("Left", "Right"), ("Center", "Center")][blk_set.content["format"]]

    proof = ProofLayout(
        name=blk_info.name,
        start_cp=blk_info.start_cp,
        end_cp=blk_info.end_cp,
        page_title=blk_set.content["title"],
        print_pages=pages,
        page_class=page_class,
        char_count=c_count,
    )
    return proof, bugs
