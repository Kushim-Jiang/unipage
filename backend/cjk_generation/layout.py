"""Proof layout -- calculates how characters are arranged onto pages.

This is the core of ``make_proof`` from the old ``printer.py``,
extracted into its own module with no UI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Optional

from backend.file_management.parser import ParseError, submitter_name, submitter_no
from backend.models.dataclasses import BlockSetting, BugEntry, ProofLayout

# -- Column configuration -------------------------------------------

_COLUMN_MAP: dict[int, tuple[int, int]] = {
    0: (40, 240),
    1: (60, 180),
    2: (80, 160),
    3: (100, 100),
}

_SRC_GROUP_A = {0, 1, 3, 4, 6, 7}
_SRC_GROUP_B = {2, 5, 8, 9, 10, 11}

_SRC_ORDER_40: dict[tuple[bool, bool], list[int]] = {
    (True, False): [0, 1, 3, 6, 4, 7],
    (False, True): [2, 10, 9, 11, 5, 8],
    (True, True): [0, 1, 3, 6, 4, 7, 2, 10, 9, 11, 5, 8],
}
_SRC_ORDER_DEFAULT = [0, 3, 1, 2, 6, 4, 5, 7, 8, 9, 10, 11]


# -- Shared data types ----------------------------------------------


@dataclass
class CjkPageData:
    """One code‑chart page ready for PDF rendering.

    Produced by :func:`make_proof`, consumed by
    :func:`pdf_builder.generate_pdf` and :func:`svg_builder.build_svg_glyphs`.

    The raw layout is a list of seven elements::

        [codepoints, rs_values, glyph_ids, source_labels, font_keys, min_cp, max_cp]
    """

    codepoints: list[str]  # page[0]
    rs_values: list  # page[1]
    glyph_ids: list  # page[2]
    source_labels: list  # page[3]
    font_keys: list  # page[4]
    min_cp: str  # page[5]
    max_cp: str  # page[6]

    @classmethod
    def from_raw(cls, raw: list) -> CjkPageData:
        return cls(
            codepoints=raw[0],
            rs_values=raw[1],
            glyph_ids=raw[2],
            source_labels=raw[3],
            font_keys=raw[4],
            min_cp=raw[5],
            max_cp=raw[6],
        )

    def to_raw(self) -> list:
        """Backward‑compatible serialisation."""
        return [
            self.codepoints,
            self.rs_values,
            self.glyph_ids,
            self.source_labels,
            self.font_keys,
            self.min_cp,
            self.max_cp,
        ]


@dataclass
class _PageBuffer:
    """Mutable working buffer for building one page during layout."""

    char_count: int
    glyph_count: int
    codepoints: list[str] = field(default_factory=list)
    rs_values: list = field(default_factory=list)
    glyph_ids: list = field(default_factory=list)
    source_labels: list = field(default_factory=list)
    font_keys: list = field(default_factory=list)

    def __post_init__(self) -> None:
        n_c = self.char_count
        n_g = self.glyph_count
        self.codepoints = [""] * n_c
        self.rs_values = [""] * n_c
        self.glyph_ids = [""] * n_g
        self.source_labels = [""] * n_g
        self.font_keys = [""] * n_g

    def reset(self) -> None:
        n_c = self.char_count
        n_g = self.glyph_count
        for i in range(n_c):
            self.codepoints[i] = ""
            self.rs_values[i] = ""
        for i in range(n_g):
            self.glyph_ids[i] = ""
            self.source_labels[i] = ""
            self.font_keys[i] = ""

    def finalise(self) -> CjkPageData:
        cp_l = self.codepoints
        mn = _extreme_cp(cp_l, "min")
        mx = _extreme_cp(cp_l, "max")
        return CjkPageData(
            codepoints=list(cp_l),
            rs_values=list(self.rs_values),
            glyph_ids=list(self.glyph_ids),
            source_labels=list(self.source_labels),
            font_keys=list(self.font_keys),
            min_cp=mn,
            max_cp=mx,
        )


# -- Helpers ---------------------------------------------------------


def _hex_str(val: int) -> str:
    return hex(val).upper().replace("0X", "")


def _extreme_cp(cp_list: list[str], opt: str) -> str:
    vals = [int(cp, 16) for cp in cp_list if cp]
    if not vals:
        return ""
    return _hex_str(min(vals) if opt == "min" else max(vals))


# -- Column / glyph counts -------------------------------------------


def get_column_config(blk_setting: BlockSetting, blk_type: str) -> tuple[int, int]:
    """Return ``(char_count, glyph_count)`` for a block's settings."""
    if blk_type in ("RF-H", "RF-W"):
        return _COLUMN_MAP[blk_setting.content["column"]]
    if blk_type == "RF-V":
        return (24, 96)
    return (0, 0)


def _compute_line_use(
    blk_type: str, c_count: int, g_count: int, cp: str, blk_info, cp_submitter: dict[int, tuple]
) -> int:
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
    col_size = 12 if blk_type == "RF-V" else 20
    fits_page = (c_index + line_use - 1) % c_count >= c_index

    if not fits_page or c_index >= c_count:
        return 0
    if (c_index % col_size + line_use - 1) % col_size < c_index % col_size:
        return 1
    return 3 if not has_more else 2


# -- Glyph fill helpers ----------------------------------------------


def _resolve_font(font_info: tuple[str | None, str], blk_set: BlockSetting) -> tuple[str, str] | None:
    """Resolve ``(name, url)`` or ``None`` if unset."""
    from backend.models.state import STATE

    font_name = font_info[1] if font_info[0] is None else font_info[0]
    if font_name == "(none)":
        return None
    proj = STATE.project
    if proj is None:
        return None
    for entry in proj.resources.font:
        if entry.basename == font_name:
            return (font_name, entry.url)
    return None


def _resolve_glyph(glyph_info: tuple, blk_type: str):
    if blk_type != "RF-V":
        return glyph_info[0] if glyph_info[0] is not None else glyph_info[1]
    return glyph_info


def _fill_40(
    cp: str,
    cp_submitter: dict[int, tuple],
    blk_set: BlockSetting,
    in_a: bool,
    in_b: bool,
    buf: _PageBuffer,
    ci: int,
    name: str,
) -> None:
    key = (bool(in_a), bool(in_b))
    src_list = _SRC_ORDER_40.get(key, [])
    gc = buf.glyph_count
    cc = buf.char_count
    for i, src_idx in enumerate(src_list):
        if src_idx not in cp_submitter:
            continue
        temp_fnt, temp_gly, temp_src = cp_submitter[src_idx]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][src_idx][1]), blk_set)
        in_gly = _resolve_glyph((temp_gly, int(cp)), "RF-H")
        if in_fnt is None:
            raise ParseError(BugEntry(0, "C007", name, f"{submitter_name(src_idx)} source"))
        pos = round(ci * gc / cc) + i
        buf.glyph_ids[pos] = in_gly
        buf.source_labels[pos] = temp_src
        buf.font_keys[pos] = in_fnt


def _fill_variant(cp: str, blk_info, blk_set: BlockSetting, buf: _PageBuffer, ci: int, lu: int, name: str) -> None:
    g_info: list[list] = []
    for entry in blk_info.content.get(cp, []):
        temp_fnt, _, temp_src = entry[1], entry[2], [entry[3], entry[4]]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][1]), blk_set)
        in_gly = _resolve_glyph((entry[0], int(cp)), "RF-V")
        if in_fnt is None:
            raise ParseError(BugEntry(0, "C007", name, "IVD"))
        g_info.append([in_gly, temp_src, in_fnt])
    gc = buf.glyph_count
    cc = buf.char_count
    for i in range(round(lu * gc / cc)):
        if i < len(g_info):
            pos = round(ci * gc / cc + i)
            buf.glyph_ids[pos] = g_info[i][0]
            buf.source_labels[pos] = g_info[i][1]
            buf.font_keys[pos] = g_info[i][2]


def _fill_default(
    cp: str, cp_submitter: dict[int, tuple], blk_set: BlockSetting, buf: _PageBuffer, ci: int, lu: int, name: str
) -> None:
    g_info: list[list] = []
    for src_idx in _SRC_ORDER_DEFAULT:
        if src_idx not in cp_submitter:
            continue
        temp_fnt, temp_gly, temp_src = cp_submitter[src_idx]
        in_fnt = _resolve_font((temp_fnt, blk_set.content["font"][src_idx][1]), blk_set)
        in_gly = _resolve_glyph((temp_gly, int(cp)), "RF-H")
        if in_fnt is None:
            raise ParseError(BugEntry(0, "C007", name, f"{submitter_name(src_idx)} source"))
        g_info.append([in_gly, temp_src, in_fnt])
    gc = buf.glyph_count
    cc = buf.char_count
    for i in range(round(lu * gc / cc)):
        if i < len(g_info):
            pos = round(ci * gc / cc + i)
            buf.glyph_ids[pos] = g_info[i][0]
            buf.source_labels[pos] = g_info[i][1]
            buf.font_keys[pos] = g_info[i][2]


# ==================================================================
# Public API
# ==================================================================


def make_proof(block_name: str) -> tuple[Optional[ProofLayout], list[BugEntry]]:
    """Build a proof for a named block.

    Parameters
    ----------
    block_name : str
        The block name to generate a proof for.

    Returns
    -------
    proof : ProofLayout or None
        ``None`` if the block type is not yet supported.
    bugs : list[BugEntry]
        Any bugs encountered during layout.
    """
    from backend.models.state import STATE

    proj = STATE.project
    if proj is None:
        return None, []

    blk_set = next((s for s in proj.settings if s.name == block_name), None)
    blk_info = next((b for b in proj.blocks if b.name == block_name), None)
    if blk_set is None or blk_info is None:
        return None, [BugEntry(0, "C000", block_name, "Block not found in project.")]

    blk_type = blk_info.type
    if blk_type not in ("RF-H", "RF-W", "RF-V"):
        return None, [BugEntry(2, "G005", block_name, f"Block type {blk_type} not supported for proof generation.")]

    c_count, g_count = get_column_config(blk_set, blk_type)
    buf = _PageBuffer(char_count=c_count, glyph_count=g_count)
    pages: list[CjkPageData] = []
    c_index = 0

    cps = sorted((int(k) for k in blk_info.content.keys()), reverse=True)
    if not cps:
        return None, [BugEntry(1, "G001", block_name, "Empty block -- no content codepoints.")]
    cps.append(cps[-1])  # sentinel

    bugs: list[BugEntry] = []

    try:
        while cps:
            cp = str(cps.pop())

            # Build source-ref index
            cp_submitter: dict[int, tuple] = {}
            if blk_type != "RF-V":
                for entry in blk_info.content.get(cp, [None, []])[1]:
                    if entry is not None:
                        cp_submitter[submitter_no(entry[-1])] = entry

            lu = _compute_line_use(blk_type, c_count, g_count, cp, blk_info, cp_submitter)
            flag = _detect_flag(c_index, lu, c_count, bool(cps), blk_type)

            if flag == 0:  # New page
                pages.append(buf.finalise())
                buf.reset()
                c_index = 0
                cps.append(cp)
                continue

            if flag == 1:  # New column
                col_size = 12 if blk_type == "RF-V" else 20
                c_index = col_size * ceil(c_index / col_size)
                cps.append(cp)
                continue

            # Fill current position
            buf.codepoints[c_index] = _hex_str(int(cp))
            if blk_type != "RF-V":
                buf.rs_values[c_index] = blk_info.content.get(cp, [None])[0]
                if buf.rs_values[c_index] is None:
                    raise ParseError(
                        BugEntry(0, "C002", block_name, f"{cp} ({_hex_str(int(cp))}) missing corresponding RS.")
                    )

            if c_count == 40:
                in_a = bool(cp_submitter.keys() & _SRC_GROUP_A)
                in_b = bool(cp_submitter.keys() & _SRC_GROUP_B)
                _fill_40(cp, cp_submitter, blk_set, in_a, in_b, buf, c_index, block_name)
            elif c_count == 24:
                _fill_variant(cp, blk_info, blk_set, buf, c_index, lu, block_name)
            else:
                _fill_default(cp, cp_submitter, blk_set, buf, c_index, lu, block_name)

            c_index += lu

            if flag == 3:  # Last entry
                pages.append(buf.finalise())
                buf.reset()

    except ParseError as exc:
        bugs.append(exc.arg)
        return None, bugs
    except Exception as exc:
        bugs.append(BugEntry(0, "C000", block_name, f"{type(exc).__name__}: {exc.args[0]}"))
        return None, bugs

    # Build proof
    page_class = [("Right", "Left"), ("Left", "Right"), ("Center", "Center")][blk_set.content["format"]]

    proof = ProofLayout(
        name=blk_info.name,
        start_cp=blk_info.start_cp,
        end_cp=blk_info.end_cp,
        page_title=blk_set.content["title"],
        print_pages=[p.to_raw() for p in pages],
        page_class=page_class,
        char_count=c_count,
    )
    return proof, bugs
