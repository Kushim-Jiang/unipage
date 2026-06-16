"""
CFL (Character Font List) and NamesList file parsers.

CFL files define which font covers which codepoint ranges.
NamesList files contain character names, annotations, and cross-references
per the Unicode NamesList Format specification.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.non_cjk_generation.models import FontConfig, NamesListEntry


def detect_block_from_nameslist(filepath: str) -> tuple[str, int, int]:
    """Extract block name and codepoint range from the first @@ header in a NamesList file.

    Returns (block_name, start_cp, end_cp).  Returns ("", 0, 0) if not found.
    """
    with open(filepath, "r", encoding="utf-8") as fp:
        for line in fp:
            m = _RE_BLOCK_HEADER.match(line.rstrip("\r\n"))
            if m:
                return m.group(2).strip(), int(m.group(1), 16), int(m.group(3), 16)
    return "", 0, 0


def split_data_tsv(filepath: str) -> tuple[str, str]:
    """Split a combined data.tsv into (nameslist_text, cfl_text).

    The file uses CJK-style section headers::

        # <range>; <block>; NL
        <nameslist content>

        # <range>; <block>; FT
        <cfl content>

    Returns two strings ready to be passed to ``parse_nameslist`` and
    ``parse_cfl`` respectively.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split on section headers: # ...; NL  and  # ...; FT
    m_nl = re.search(r"^# .*?; NL\s*$\n(.*?)(?=^# .*?; FT\s*$|\Z)", content, re.MULTILINE | re.DOTALL)
    m_ft = re.search(r"^# .*?; FT\s*$\n(.*)", content, re.MULTILINE | re.DOTALL)

    if m_nl:
        names_text = m_nl.group(1).strip()
    if m_ft:
        cfl_text = m_ft.group(1).strip()

    return names_text, cfl_text


# ==================================================================->
#  CFL Parser
# ==================================================================->

_RE_SECTION = re.compile(r"^\$(\*|\$|FE[0-9A-Fa-f]{2}(?:_\w+)?)\s*")
_RE_FONT_LINE = re.compile(r"^([^,]+)\s*,\s*(\d+(?:\.\d+)?)((?:\s*,[-\d]+)*)\s*(.*)$")
_RE_Q_OFFSET = re.compile(r"/Q=([0-9A-Fa-f]+)")
_RE_R_RANGE = re.compile(r"/R=([0-9A-Fa-f]+)-([0-9A-Fa-f]+)")
_RE_X_EXCLUDE = re.compile(r"/X=([0-9A-Fa-f]+)-([0-9A-Fa-f]+)")
_RE_I_INCLUDE = re.compile(r"/I=([0-9A-Fa-f]+)-([0-9A-Fa-f]+)")
_RE_S_START = re.compile(r"/S=([0-9A-Fa-f]+)")
_RE_O_START = re.compile(r"/O=([0-9A-Fa-f]+)")
_RE_M_MINSIZE = re.compile(r"/M=(\d+)")


def parse_hex(s: str) -> int:
    return int(s.strip(), 16)


def parse_cfl(filepath: str) -> tuple[list[FontConfig], list[FontConfig]]:
    """Parse a CFL file.  Returns (chart_fonts, common_fonts)."""
    chart_fonts: list[FontConfig] = []
    common_fonts: list[FontConfig] = []
    in_common = False

    with open(filepath, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            m = _RE_SECTION.match(line)
            if m:
                kind = m.group(1)
                if kind == "*":
                    in_common = True
                else:
                    in_common = False
                continue
            m = _RE_FONT_LINE.match(line)
            if not m:
                continue
            font_name = m.group(1).strip()
            font_size = float(m.group(2))
            rest = m.group(4).strip()
            if not rest:
                continue

            config = FontConfig(font_name=font_name, size=font_size)

            qm = _RE_Q_OFFSET.search(rest)
            if qm:
                config.offset = parse_hex(qm.group(1))

            rm = _RE_R_RANGE.search(rest)
            if rm:
                config.range_start = parse_hex(rm.group(1))
                config.range_end = parse_hex(rm.group(2))

            im = _RE_I_INCLUDE.search(rest)
            if im:
                config.range_start = parse_hex(im.group(1))
                config.range_end = parse_hex(im.group(2))

            sm = _RE_S_START.search(rest)
            if sm:
                start = parse_hex(sm.group(1))
                config.range_start = start
                config.range_end = start + 127

            om = _RE_O_START.search(rest)
            if om:
                start = parse_hex(om.group(1))
                config.range_start = start
                config.range_end = start + 127

            for xm in _RE_X_EXCLUDE.finditer(rest):
                config.excludes.append((parse_hex(xm.group(1)), parse_hex(xm.group(2))))

            mm = _RE_M_MINSIZE.search(rest)
            if mm:
                config.min_size = int(mm.group(1))

            if in_common:
                common_fonts.append(config)
            else:
                chart_fonts.append(config)

    return chart_fonts, common_fonts


def find_font_for_codepoint(configs: list[FontConfig], codepoint: int) -> Optional[FontConfig]:
    """Find the first font covering a given codepoint (top-down search).

    Respects /X= exclude ranges.  When a font has a Q offset (below 0xF0000),
    the /R= range is the font's *internal* glyph range (often PUA); the Q
    offset maps Unicode codepoints into that range.
    """
    for cfg in configs:
        # Q values >= 0xF0000 are identity mappings (font uses Unicode codepoints)
        if cfg.offset and cfg.offset < 0xF0000:
            font_cp = cfg.range_start + (codepoint - cfg.offset)
            if cfg.range_start <= font_cp <= cfg.range_end:
                excluded = any(ex_start <= codepoint <= ex_end for ex_start, ex_end in cfg.excludes)
                if not excluded:
                    return cfg
        else:
            if cfg.range_start <= codepoint <= cfg.range_end:
                excluded = any(ex_start <= codepoint <= ex_end for ex_start, ex_end in cfg.excludes)
                if not excluded:
                    return cfg
    return None


def find_font_for_range(configs: list[FontConfig], start_cp: int, end_cp: int) -> dict[int, FontConfig]:
    """Map each codepoint in [start_cp, end_cp] to its FontConfig."""
    result: dict[int, FontConfig] = {}
    for cp in range(start_cp, end_cp + 1):
        font = find_font_for_codepoint(configs, cp)
        if font:
            result[cp] = font
    return result


# ==================================================================->
#  NamesList Parser  ->Unicode NamesList Format v17.0
# ==================================================================->

# -- Structural lines (@-prefix, longer first) ------------------

_RE_BLOCK_HEADER = re.compile(r"^@@\t([0-9A-F]{4,6})\t(.+?)\t([0-9A-F]{4,6})$")
_RE_PAGE_BREAK = re.compile(r"^@@$")
_RE_INDEX_TAB = re.compile(r"^@@\+$")
_RE_TITLE = re.compile(r"^@@@\t(.+)$")
_RE_SUBTITLE = re.compile(r"^@@@\+\t(.+)$")
_RE_MIXED_SUBHEADER = re.compile(r"^@@@~\t?(.*)$")
_RE_ALTGLYPH_SUBHEADER = re.compile(r"^@@~\t?(.*)$")
_RE_VARIATION_SUBHEADER = re.compile(r"^@~\t?(.*)$")
_RE_NOTICE = re.compile(r"^@\+\t(\* )?(.+)$")
_RE_SUBHEADER = re.compile(r"^@\t(.+)$")

# -- Character entries ------------------------------------------

_RE_RESERVED = re.compile(r"^([0-9A-F]{4,6})\t<reserved>$")
_RE_NAME_LINE = re.compile(
    r"^([0-9A-F]{4,6})\t"
    r"(?:<([a-z][A-Za-z0-9 \-]*(?:-[0-9A-F]{4,6})?)>|"
    r"([A-Z][A-Z0-9 \-]+(?:-[0-9A-F]{4,6})?))"
    r"(?: (.+))?$"
)

# -- TAB-prefix annotations -------------------------------------

_RE_ALIAS = re.compile(r"^\t= (.+)$")
_RE_FORMAL_ALIAS = re.compile(r"^\t% (.+)$")
_RE_CROSS_REF = re.compile(r"^\tx (.+)$")
_RE_VARIATION = re.compile(r"^\t~ (.+)$")
_RE_DECOMPOSITION = re.compile(r"^\t: (?:(<[a-z]+>) )?(.+)$")
_RE_COMPAT_MAPPING = re.compile(r"^\t# (?:(<[A-Za-z]+>) )?(.+)$")
_RE_BULLET_COMMENT = re.compile(r"^\t\* (.+)$")
_RE_IGNORED = re.compile(r"^\t;.*$")

# -- Other lines ------------------------------------------------

_RE_SIDEBAR = re.compile(r"^;; (.+)$")
_RE_FILE_COMMENT = re.compile(r"^;(.*)$")

# -- Cross-reference sub-parser ---------------------------------

_RE_XREF_STANDARD = re.compile(
    r"^([0-9A-F]{4,6}) " r"(?:<([a-z][A-Za-z0-9 \-]*(?:-[0-9A-F]{4,6})?)>|" r"([a-z][a-z0-9 \-]+(?:-[0-9A-F]{4,6})?))$"
)
_RE_XREF_IDEOGRAPH = re.compile(r"^([0-9A-F]{4,6})$")
_RE_XREF_PAREN = re.compile(
    r"^\( ?(?:<([a-z][A-Za-z0-9 \-]*(?:-[0-9A-F]{4,6})?)>|"
    r"([a-z][a-z0-9 \-]+(?:-[0-9A-F]{4,6})?)) ?- ?([0-9A-F]{4,6}) ?\)$"
)

# -- Variation sub-parser ---------------------------------------

_RE_VARIATION_PARTS = re.compile(r"^([0-9A-F]{4,6}) (ALT[1-9]|[0-9A-F]{4,6}) (.+?)(?: \(([a-z]+)\))?$")


# ==================================================================->


def parse_nameslist(filepath: str) -> list[NamesListEntry]:
    """Parse a Unicode NamesList.txt file per the NamesList Format spec."""
    with open(filepath, "r", encoding="utf-8") as fp:
        lines = [raw.rstrip("\r\n") for raw in fp]
    return parse_nameslist_from_lines(lines)


def parse_nameslist_from_lines(lines: list[str]) -> list[NamesListEntry]:
    """Parse NamesList content from a list of lines.

    Same semantics as :func:`parse_nameslist`, but accepts pre‑read lines
    so callers that already have the content in memory can avoid file I/O.
    """
    entries: list[NamesListEntry] = []
    current: Optional[NamesListEntry] = None

    def _flush():
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    for line in lines:

        # -- Empty line ------------------------------------
        if not line.strip():
            _flush()
            entries.append(NamesListEntry(type="empty"))
            continue

        # -- File comment (; prefix) -----------------------
        m = _RE_FILE_COMMENT.match(line)
        if m:
            _flush()
            entries.append(NamesListEntry(type="file_comment", text=m.group(1).strip()))
            continue

        # -- Sidebar (;; prefix) ---------------------------
        m = _RE_SIDEBAR.match(line)
        if m:
            _flush()
            entries.append(NamesListEntry(type="sidebar", text=m.group(1).lstrip("\t ")))
            continue

        # -- @-prefix structural lines (longer prefix first) --

        m = _RE_SUBTITLE.match(line)  # @@@+
        if m:
            _flush()
            entries.append(NamesListEntry(type="subtitle", text=m.group(1).lstrip("\t ")))
            continue

        m = _RE_TITLE.match(line)  # @@@
        if m:
            _flush()
            entries.append(NamesListEntry(type="title", text=m.group(1).lstrip("\t ")))
            continue

        m = _RE_MIXED_SUBHEADER.match(line)  # @@@~
        if m:
            _flush()
            entries.append(NamesListEntry(type="mixed_subheader", text=m.group(1).lstrip("\t ")))
            continue

        if _RE_INDEX_TAB.match(line):  # @@+
            _flush()
            entries.append(NamesListEntry(type="index_tab"))
            continue

        m = _RE_BLOCK_HEADER.match(line)  # @@ TAB start name end
        if m:
            _flush()
            start_cp = m.group(1)
            raw_name = m.group(2).strip()
            end_cp = m.group(3)

            # Alternate ISO label:  NAME SP (alt_label)
            alt_label = ""
            alt_m = re.match(r"^(.+?) \(([^)]+)\)$", raw_name)
            if alt_m:
                raw_name = alt_m.group(1).strip()
                alt_label = alt_m.group(2).strip()

            entries.append(
                NamesListEntry(
                    type="block_header",
                    block_name=raw_name,
                    block_start=start_cp,
                    block_end=end_cp,
                    alt_label=alt_label,
                )
            )
            continue

        if _RE_PAGE_BREAK.match(line):  # @@ alone
            _flush()
            entries.append(NamesListEntry(type="page_break"))
            continue

        m = _RE_ALTGLYPH_SUBHEADER.match(line)  # @@~
        if m:
            _flush()
            entries.append(NamesListEntry(type="altglyph_subheader", text=m.group(1).lstrip("\t ")))
            continue

        m = _RE_VARIATION_SUBHEADER.match(line)  # @~
        if m:
            _flush()
            entries.append(NamesListEntry(type="variation_subheader", text=m.group(1).lstrip("\t ")))
            continue

        m = _RE_NOTICE.match(line)  # @+
        if m:
            bullet = m.group(1) is not None
            text = m.group(2).lstrip("\t ")
            _flush()
            entries.append(NamesListEntry(type="notice", text=text, name=("*" if bullet else "")))
            continue

        m = _RE_SUBHEADER.match(line)  # @  (lowest @ priority)
        if m:
            _flush()
            entries.append(NamesListEntry(type="subheader", text=m.group(1).lstrip("\t ")))
            continue

        # -- Reserved line ---------------------------------
        m = _RE_RESERVED.match(line)
        if m:
            _flush()
            current = NamesListEntry(type="reserved", codepoint=m.group(1), name="<reserved>")
            continue

        # -- Name line -------------------------------------
        m = _RE_NAME_LINE.match(line)
        if m:
            _flush()
            cp = m.group(1)
            ctrl_name = m.group(2)
            reg_name = m.group(3)
            comment = m.group(4)
            name = f"<{ctrl_name}>" if ctrl_name else (reg_name or "")
            entry = NamesListEntry(type="name", codepoint=cp, name=name)
            if comment:
                entry.annotations.append(NamesListEntry(type="comment", text=comment))
            current = entry
            continue

        # -- TAB-prefix annotation lines -------------------

        if _RE_IGNORED.match(line):  # TAB ;
            ann = NamesListEntry(type="ignored", text=line.strip())
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_ALIAS.match(line)  # TAB =
        if m:
            ann = NamesListEntry(type="alias", text=m.group(1).lstrip("\t "))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_FORMAL_ALIAS.match(line)  # TAB %
        if m:
            ann = NamesListEntry(type="formal_alias", name=m.group(1).lstrip("\t "))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_CROSS_REF.match(line)  # TAB x
        if m:
            ann = _parse_cross_ref(m.group(1))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_VARIATION.match(line)  # TAB ~
        if m:
            ann = _parse_variation(m.group(1))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_DECOMPOSITION.match(line)  # TAB :
        if m:
            ann = NamesListEntry(type="decomposition", mapping_tag=m.group(1) or "", mapping_text=m.group(2))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_COMPAT_MAPPING.match(line)  # TAB #
        if m:
            ann = NamesListEntry(type="compat_mapping", mapping_tag=m.group(1) or "", mapping_text=m.group(2))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        m = _RE_BULLET_COMMENT.match(line)  # TAB *
        if m:
            ann = NamesListEntry(type="comment", text=m.group(1).lstrip("\t "))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        # Unmarked comment: TAB ... (lowest TAB priority)
        if line.startswith("\t"):
            ann = NamesListEntry(type="comment", text=line.lstrip("\t"))
            if current:
                current.annotations.append(ann)
            else:
                _flush()
                entries.append(ann)
            continue

        # -- Fallback --------------------------------------
        _flush()
        entries.append(NamesListEntry(type="comment", text=line))

    _flush()
    return entries


def _parse_cross_ref(rest: str) -> NamesListEntry:
    """Parse cross-reference content (after 'x ')."""
    # Parenthesized: ( LCNAME - CHAR )
    m = _RE_XREF_PAREN.match(rest)
    if m:
        ctrl, reg, cp = m.group(1), m.group(2), m.group(3)
        name = f"<{ctrl}>" if ctrl else (reg or "")
        return NamesListEntry(type="cross_ref", target_cp=cp, target_name=name)

    # Standard: CHAR SP LCNAME
    m = _RE_XREF_STANDARD.match(rest)
    if m:
        cp, ctrl, reg = m.group(1), m.group(2), m.group(3)
        name = f"<{ctrl}>" if ctrl else (reg or "")
        return NamesListEntry(type="cross_ref", target_cp=cp, target_name=name)

    # Ideograph: CHAR only
    m = _RE_XREF_IDEOGRAPH.match(rest)
    if m:
        return NamesListEntry(type="cross_ref", target_cp=m.group(1))

    return NamesListEntry(type="cross_ref", target_name=rest)


def _parse_variation(rest: str) -> NamesListEntry:
    """Parse variation sequence content (after '~ ')."""
    m = _RE_VARIATION_PARTS.match(rest)
    if m:
        return NamesListEntry(
            type="variation",
            codepoint=m.group(1),
            var_selector=m.group(2),
            var_label=m.group(3),
            var_tag=m.group(4) or "",
        )
    return NamesListEntry(type="variation", var_label=rest)


def extract_block_entries(
    entries: list[NamesListEntry],
    start_cp: int,
    end_cp: int,
) -> list[NamesListEntry]:
    """Filter nameslist entries to those within [start_cp, end_cp]."""
    result: list[NamesListEntry] = []
    in_block = False

    for entry in entries:
        cp_in_range = False
        cp_val = None
        if entry.codepoint:
            try:
                cp_val = int(entry.codepoint, 16)
                cp_in_range = start_cp <= cp_val <= end_cp
            except ValueError:
                pass

        # block_header marks the start of the block even without a codepoint field
        if entry.type == "block_header":
            try:
                bs = int(entry.block_start, 16)
                be = int(entry.block_end, 16)
                # If this block overlaps our range, we're entering the block now
                if bs <= end_cp and be >= start_cp:
                    in_block = True
            except ValueError:
                pass
            continue

        if cp_in_range:
            if not in_block:
                in_block = True
            result.append(entry)
            continue

        if cp_val is not None and cp_val > end_cp:
            if in_block:
                break
            continue

        # Structural entries within the block
        if in_block and entry.type in (
            "block_header",
            "subheader",
            "notice",
            "cross_ref",
            "comment",
            "empty",
            "file_comment",
            "ignored",
            "page_break",
            "sidebar",
            "alias",
            "formal_alias",
            "decomposition",
            "compat_mapping",
            "variation",
        ):
            result.append(entry)
            continue

    return result
