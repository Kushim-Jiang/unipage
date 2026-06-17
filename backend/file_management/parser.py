"""Resource file parsers for .json (project), .tsv (block/attribute) files.

All parser functions follow the same contract::

    (parsed_content, bugs: list[list])

where each bug entry is ``[severity, code, basename, detail_message]``
with severity ``0`` = error, ``1`` = warning, ``2`` = info.
"""

from __future__ import annotations

from copy import deepcopy
from json import JSONDecodeError, load
from os.path import basename
from re import compile as _compile

from backend.models.dataclasses import BlockInfo, BugEntry

# -- Source name helpers ----------------------------------------------

_SUBMITTER_NAMES = ["G", "H", "M", "T", "K", "KP", "J", "V", "GS", "UK", "UTC", "SAT"]

_SUBMITTER_PREFIXES: dict[str, int] = {
    "SAT": 11,
    "UTC": 10,
    "UK": 9,
    "GS": 8,
    "V": 7,
    "J": 6,
    "KP": 5,
    "K": 4,
    "T": 3,
    "M": 2,
    "H": 1,
    "G": 0,
}


def submitter_name(source: int) -> str:
    """Map source index (0-11) to source name string."""
    return _SUBMITTER_NAMES[source]


def submitter_no(reference: str) -> int:
    """Map a reference source prefix (e.g. ``'G0-523B'``) to index (0-11)."""
    upper = reference.upper()
    for prefix, idx in _SUBMITTER_PREFIXES.items():
        if upper.startswith(prefix):
            return idx
    return 0


# -- Radical-stroke display ------------------------------------------

_RS_VARIANTS: dict[str, str] = {
    "90'": "\u2ea6",
    "120'": "\u2eb0",
    "147'": "\u2ec5",
    "149'": "\u2ec8",
    "154'": "\u2ec9",
    "159'": "\u2ecb",
    "167'": "\u2ed0",
    "168'": "\u2ed3",
    "169'": "\u2ed4",
    "178'": "\u2ed9",
    "181'": "\u2eda",
    "182'": "\u2edb",
    "183'": "\u2edc",
    "184'": "\u2ee0",
    "187'": "\u2ee2",
    "195'": "\u2ee5",
    "196'": "\u2ee6",
    "197'": "\u2ee7",
    "199'": "\u2ee8",
    "201'": "\u2ee9",
    "205'": "\u2eea",
    "210'": "\u2eec",
    "211'": "\u2eee",
    "212'": "\u2ef0",
    "213'": "\u2ef3",
    # Double-prime variants
    "182''": "\U000322c4",
    "208''": "\u9f21",
    "210''": "\u2eeb",
    "211''": "\u2eed",
    "212''": "\u2eef",
    "213''": "\u2ef2",
    # Triple-prime variant
    "212'''": "\U00031de5",
}


def show_rs(rs: str) -> str | None:
    """Format a radical-stroke value like ``'90.0'`` into a display string."""
    key = rs.split(".")[0]
    if "'" not in key:
        num = int(key)
        if 1 <= num <= 214:
            return chr(0x2EFF + num) + "\u3000" + rs
        return None
    return (_RS_VARIANTS.get(key, "") + "\u3000" + rs) if key in _RS_VARIANTS else None


# -- Custom exception ------------------------------------------------


class ParseError(Exception):
    """Carries a bug entry: ``BugEntry``."""

    def __init__(self, arg: list | BugEntry) -> None:
        if isinstance(arg, BugEntry):
            self.arg = arg
        else:
            self.arg = BugEntry.from_list(arg)


# -- Internal helpers ------------------------------------------------


def _encode(line: str) -> str:
    return line.encode("unicode_escape").decode("utf-8")


def _bug(severity: int, code: str, url: str, detail: str = "") -> BugEntry:
    return BugEntry(severity, code, basename(url), detail)


def _handle_exc(exc: Exception, url: str, line: str = "") -> BugEntry:
    name = type(exc).__name__
    if name == "ValueError":
        return _bug(0, "C001", url, _encode(line))
    if name == "UnicodeDecodeError":
        return _bug(0, "C001", url, "")
    if name == "ParseError":
        return exc.arg  # type: ignore[union-attr]
    return _bug(0, "C000", url, f"{name}: {_encode(line)}")


def _read_lines(path: str):
    """Yield stripped non-empty lines from a UTF-8 file until ``# EOF``."""
    with open(path, "r", encoding="utf-8") as fp:
        for raw in fp:
            line = raw.strip()
            if line.lower() == "# eof":
                return
            yield line


# ==================================================================
# TSV type detection (both block and attribute use .tsv now)
# ==================================================================


_BLK_TYPES = {"RF-W", "RF-H", "RF-V"}
_ATT_TYPES = {"RS-W", "RS-H", "NL", "CD", "FT"}


def detect_tsv_type(path: str) -> str:
    """Detect the internal type of a .tsv data file from its header.

    Returns the type code: ``'RF-W'``, ``'RF-H'``, ``'RF-V'`` (blocks),
    ``'RS-W'``, ``'RS-H'``, ``'NL'``, ``'CD'``, ``'FT'`` (other data),
    or ``'unknown'``.
    """
    try:
        with open(path, "r", encoding="utf-8") as fp:
            for raw in fp:
                line = raw.strip()
                if line and line[0] == "#":
                    parts = line[1:].strip().split(";")
                    if len(parts) >= 3:
                        type_field = parts[2].strip()
                        if type_field in _BLK_TYPES | _ATT_TYPES:
                            return type_field
                    return "unknown"
    except Exception:
        pass
    return "unknown"


# ==================================================================
# Public parsers
# ==================================================================


def parse_project_file(path: str) -> tuple[dict | list, list[BugEntry]]:
    """Parse a ``.json`` (project) file."""
    bugs: list[BugEntry] = []
    try:
        with open(path, "r", encoding="utf-8") as fp:
            content = load(fp)
    except JSONDecodeError as exc:
        content = {}
        bugs.append(_bug(0, "C006", path, str(exc.args[0])))
    except Exception as exc:
        content = {}
        bugs.append(_bug(0, "C000", path, f"{type(exc).__name__}: {exc.args[0]}"))
    return content, bugs


def parse_block_file(path: str) -> tuple[list[BlockInfo], list[BugEntry]]:
    """Parse a ``.tsv`` block (Unicode block) file.

    Returns (blocks, bugs).  Each block is a ``BlockInfo``.
    """
    blocks: list[BlockInfo] = []
    bugs: list[BugEntry] = []

    blk_name = blk_type = ""
    blk_init = blk_fina = 0
    content: dict = {}

    try:
        for raw in _read_lines(path):
            if not raw:
                continue
            line = raw

            if line[0] == "#":
                # Finalize previous block
                if blk_name:
                    blocks.append(
                        BlockInfo(
                            name=blk_name,
                            type=blk_type,
                            start_cp=blk_init,
                            end_cp=blk_fina,
                            content=deepcopy(content),
                        )
                    )

                # Parse header: # range;name;type
                parts = line[1:].strip().split(";")
                blk_range_s, blk_name, blk_type = (s.strip() for s in parts)
                lo_s, hi_s = blk_range_s.split("..")
                blk_init, blk_fina = int(lo_s.strip(), 16), int(hi_s.strip(), 16)
                content = {}

                if not blk_name:
                    raise ParseError(_bug(0, "C003", path, _encode(line)))
                if not blk_type:
                    raise ParseError(_bug(0, "C004", path, _encode(line)))
                if blk_init >= blk_fina:
                    raise ParseError(_bug(0, "C005", path, _encode(line)))
                if blk_init % 16 != 0:
                    bugs.append(_bug(0, "J001", path, _encode(line)))
                if blk_fina % 16 != 15:
                    bugs.append(_bug(0, "J002", path, _encode(line)))
            else:
                # Data lines -- delegate by block type
                _dispatch_blk_line(blk_type, content, line, blk_init, path, bugs)

        # Finalize last block
        if blk_name:
            blocks.append(
                BlockInfo(
                    name=blk_name,
                    type=blk_type,
                    start_cp=blk_init,
                    end_cp=blk_fina,
                    content=deepcopy(content),
                )
            )

    except Exception as exc:
        bugs.append(_handle_exc(exc, path))

    return blocks, bugs


# -- Block line-type dispatchers ---------------------------------------


def _dispatch_blk_line(blk_type: str, cont: dict, line: str, blk_init: int, path: str, bugs: list) -> None:
    parsers = {
        "RF-W": _parse_block_w_line,
        "RF-H": _parse_block_h_line,
        "RF-V": _parse_block_v_line,
    }
    parser = parsers.get(blk_type)
    if parser:
        parser(cont, line, blk_init, path, bugs)


def _parse_block_w_line(cont: dict, line: str, blk_init: int, path: str, bugs: list) -> None:
    """Parse a W-type (word / reference) data line."""
    parts = line.strip().split("\t")
    if len(parts) == 3:
        sq_s, reference, pua_s = parts
        sq = int(sq_s.strip(), 10)
        reference = reference.strip()
        pua = int(pua_s.upper().strip().replace("U+", ""), 16)
        key = f"{sq}\u3000{blk_init + sq - 1}\u3000{submitter_name(submitter_no(reference))}"
        cont[key] = [None, pua, reference]
    elif len(parts) == 2:
        sq_s, reference = parts
        sq = int(sq_s.strip(), 16)
        reference = reference.strip()
        key = f"{sq}\u3000{blk_init + sq - 1}\u3000{submitter_name(submitter_no(reference))}"
        cont[key] = [None, None, reference]
    else:
        raise ValueError


def _parse_block_h_line(cont: dict, line: str, *args) -> int | None:
    """Parse an H-type (Han) data line."""
    cp_s, _, reference = line.strip().split("\t")
    cp = int(cp_s.upper().replace("U+", ""), 16)
    cont[f"{cp}\u3000{submitter_name(submitter_no(reference))}"] = [None, None, reference]
    return cp


def _parse_block_v_line(cont: dict, line: str, *args) -> int | None:
    """Parse a V-type (IVS / variation) data line."""
    ivs_part, charset, cid = line.strip().split("\t")
    cp_s, sel_s = ivs_part.strip().split(" ")
    cp = int(cp_s.strip(), 16)
    sel = int(sel_s.strip(), 16)
    cont[f"{cp}\u3000{sel}\u3000{charset.strip()}"] = [None, None, cid.strip()]
    return cp


# ==================================================================
# ATT parser
# ==================================================================


_RS_PATTERN = _compile(r"[1-9][0-9]{0,2}['\"]?\.-?[0-9]{1,2}")


def parse_attribute_file(path: str) -> tuple[list[dict], list[BugEntry]]:
    """Parse a ``.tsv`` attribute file.

    Returns (contents, bugs).  Each content dict has key ``inf_cont``
    which is either a dict (RS-H/RS-W) or a list (NL).
    """
    contents: list[dict] = []
    bugs: list[BugEntry] = []

    section_name = inf_type = ""
    set_cont: dict = {}
    lst_cont: list = []

    try:
        for raw in _read_lines(path):
            if not raw:
                continue
            line = raw

            if line[0] == "#":
                # Finalize previous section
                if section_name:
                    inf_cont = _finalise_section(inf_type, set_cont, lst_cont)
                    contents.append(deepcopy({"inf_cont": inf_cont}))
                    set_cont, lst_cont = {}, []

                # #range;name;type
                parts = line[1:].strip().split(";")
                _blk_range = parts[0].strip()
                section_name = parts[1].strip()
                inf_type = parts[2].strip()

                if inf_type not in ("RS-H", "RS-W", "NL"):
                    raise ValueError
            else:
                _dispatch_attribute_line(inf_type, set_cont, lst_cont, line, path, bugs)

        if section_name:
            inf_cont = _finalise_section(inf_type, set_cont, lst_cont)
            contents.append(deepcopy({"inf_cont": inf_cont}))

    except Exception as exc:
        bugs.append(_handle_exc(exc, path))

    return contents, bugs


def _parse_nameslist_lines(lines: list[str]):
    """Parse raw NL (NamesList) lines into structured entries.

    Delegates to the full parser in :mod:`backend.non_cjk_generation.parsers`.
    """
    from backend.non_cjk_generation.parsers import parse_nameslist_from_lines

    return parse_nameslist_from_lines(lines)


def _dispatch_attribute_line(inf_type: str, set_cont: dict, lst_cont: list, line: str, path: str, bugs: list) -> None:
    if inf_type == "RS-H":
        _parse_attribute_rsh(set_cont, line, path, bugs)
    elif inf_type == "RS-W":
        _parse_attribute_rsw(set_cont, line, path, bugs)
    elif inf_type == "NL":
        lst_cont.append(line)  # collect raw lines; parsed later


def _finalise_section(inf_type: str, set_cont: dict, lst_cont: list):
    """Convert collected raw data to the final ``inf_cont`` value."""
    if inf_type == "NL" and lst_cont:
        return _parse_nameslist_lines(lst_cont)
    return set_cont if set_cont else lst_cont


def _validate_rs(rs_value: str, line: str, path: str, bugs: list, severity: int = 1) -> None:
    if _RS_PATTERN.match(rs_value) is None or _RS_PATTERN.match(rs_value).group() != rs_value:
        raise ParseError(_bug(0, "C002", path, _encode(line)))
    if show_rs(rs_value) is None:
        code = "J004" if severity == 1 else "C002"
        bugs.append(_bug(severity, code, path, _encode(line)))


def _parse_attribute_rsh(set_cont: dict, line: str, path: str, bugs: list) -> None:
    cp_s, _, raw_vals = line.strip().split("\t")
    cp = int(cp_s.strip().upper().replace("U+", ""), 16)
    values = raw_vals.strip().split(" ")
    for v in values:
        _validate_rs(v.strip(), line, path, bugs, severity=1)
    set_cont[str(cp)] = values


def _parse_attribute_rsw(set_cont: dict, line: str, path: str, bugs: list) -> None:
    sq_s, raw_vals = line.strip().split("\t")
    sq = int(sq_s)
    values = raw_vals.strip().split(" ")
    for v in values:
        _validate_rs(v.strip(), line, path, bugs, severity=0)
    set_cont[str(sq)] = values
