"""High-level resource lifecycle — import, parse, remove, build.

Sits on top of ``parser`` and ``models.project`` to provide
the operations that were previously spread across ``tools.py``.
"""

from __future__ import annotations

from os.path import splitext
from typing import Optional

from backend.file_management.parser import detect_tsv_type, parse_attribute_file, parse_block_file, submitter_no
from backend.file_management.validator import BugEntry, has_errors
from backend.models.dataclasses import BlockInfo, BlockSetting
from backend.models.project import VALID_IMPORT_EXTS, Project

# ── Status constants ────────────────────────────────────────────────

UNCOMPILED = 0
COMPILE_FAILED = 1
COMPILED_OK = 2

# ── Resource import ─────────────────────────────────────────────────


def import_resource(
    project: Project,
    src_path: Optional[str],
    dest_path: str,
    check_status: int = UNCOMPILED,
    parse_data: Optional[list] = None,
) -> str:
    """Import a resource file into the project. Returns the resource key."""
    ext = splitext(dest_path)[1].lower()
    if ext not in VALID_IMPORT_EXTS and ext != ".json":
        raise ValueError(f"C011: Unsupported file extension: {ext}")
    return project.add_resource(src_path, dest_path, check_status, parse_data)


def remove_resource(project: Project, path: str) -> bool:
    """Remove a resource by its path. Returns True if found and removed."""
    return project.remove_resource_by_path(path)


# ── Resource parsing ────────────────────────────────────────────────


# ── Font parsing ────────────────────────────────────────────────────


def parse_font_file(path: str) -> tuple[Optional[dict], list]:
    """Validate a TTF/OTF font file and extract basic metadata.

    Returns (metadata_dict, bugs_list).
    """
    bugs: list = []
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path)
        # Basic validation — check required tables
        required = {"cmap", "head", "hhea", "hmtx", "maxp", "name", "OS/2", "post"}
        tables = set(font.keys())
        missing = required - tables
        if missing:
            bugs.append(BugEntry(1, "B005", path, f"Missing required tables: {', '.join(sorted(missing))}"))
            return None, bugs

        # Extract metadata
        name_table = font["name"]
        records = name_table.getName(1, 3, 1, 0x409)  # Font Family (Windows, English)
        family = records.toUnicode() if records else "Unknown"
        records = name_table.getName(2, 3, 1, 0x409)  # Font Subfamily (Windows, English)
        subfamily = records.toUnicode() if records else "Regular"

        head = font["head"]
        num_glyphs = font["maxp"].numGlyphs

        info = {
            "family": family,
            "subfamily": subfamily,
            "num_glyphs": num_glyphs,
            "units_per_em": head.unitsPerEm,
            "tables": sorted(tables),
        }
        font.close()
        return info, bugs
    except Exception as exc:
        bugs.append(BugEntry(0, "C009", path, f"Font parse error: {exc}"))
        return None, bugs


def parse_and_update(project: Project, path: str) -> list:
    """Parse a resource file and update its status in-place.

    Supports .tsv (block/attribute) and .ttf/.otf (font) files.
    Returns the bug list from parsing.
    """

    ext = splitext(path)[1].lower()

    # ── Font files ─────────────────────────────────────────────
    if ext in (".ttf", ".otf"):
        parsed, bugs = parse_font_file(path)
        rsc = project.find_resource(path)
        if rsc is None:
            return bugs
        if has_errors(bugs):
            rsc.check_status = COMPILE_FAILED
        else:
            rsc.parse_data = parsed
            rsc.check_status = COMPILED_OK
        return bugs

    # ── TSV files (block / attribute) ──────────────────────────
    if ext != ".tsv":
        return []
    tsv_type = detect_tsv_type(path)
    parser_fn = parse_block_file if tsv_type == "block" else parse_attribute_file if tsv_type == "attribute" else None
    if parser_fn is None:
        return []

    parsed, bugs = parser_fn(path)
    rsc = project.find_resource(path)
    if rsc is None:
        return bugs

    if has_errors(bugs):
        rsc.check_status = COMPILE_FAILED
    else:
        # Convert BlockInfo dataclass objects to dicts for JSON serialization
        if tsv_type == "block" and parsed and isinstance(parsed[0], BlockInfo):
            rsc.parse_data = [b.to_dict() for b in parsed]
        else:
            rsc.parse_data = parsed
        rsc.check_status = COMPILED_OK
    return bugs


def parse_resource(project: Project, path: str) -> tuple[Optional[list], list]:
    """Parse a resource and return (parsed_data, bugs)."""
    ext = splitext(path)[1].lower()
    if ext != ".tsv":
        return None, []
    tsv_type = detect_tsv_type(path)
    if tsv_type == "block":
        return parse_block_file(path)
    if tsv_type == "attribute":
        return parse_attribute_file(path)
    return None, []


# ── Block building from parsed data ─────────────────────────────────


def build_blocks(project: Project) -> list[BlockInfo]:
    """Rebuild ``blocks`` from parsed block resources.

    Returns the new block list.
    """
    blocks: list[BlockInfo] = []
    for blk_entry in project.resources.block:
        if blk_entry.check_status != COMPILED_OK:
            continue
        for parsed_block in blk_entry.parse_data or []:
            # parsed_block may be a dict (from JSON) or BlockInfo
            if isinstance(parsed_block, BlockInfo):
                info = parsed_block
            else:
                info = BlockInfo.from_dict(parsed_block)
            block = _merge_block_data(info, project)
            blocks.append(block)
    project.blocks = blocks
    return blocks


def _merge_block_data(parsed: BlockInfo, project: Project) -> BlockInfo:
    """Merge parsed block data with RS info from attribute files."""
    bt = parsed.type
    init_cp = parsed.start_cp
    fina_cp = parsed.end_cp

    result = BlockInfo(
        name=parsed.name,
        type=parsed.type,
        start_cp=parsed.start_cp,
        end_cp=parsed.end_cp,
        content={},
    )

    if bt in ("H", "W"):
        _merge_hw_cont(result, parsed, init_cp, fina_cp, project)
    elif bt == "V":
        _merge_v_cont(result, parsed)
    elif bt == "C":
        _merge_c_cont(result, parsed, project)

    return result


def _merge_hw_cont(result: BlockInfo, parsed: BlockInfo, init_cp: int, fina_cp: int, project: Project) -> None:
    """Merge H/W block content with 12-slot source arrays and RS info."""
    # Initialise all slots
    for cp in range(init_cp, fina_cp + 1):
        result.content[str(cp)] = [None, [None] * 12]

    # Fill from parsed data
    for key, val in parsed.content.items():
        parts = key.split("\u3000")
        chr_cp = parts[0] if result.type == "H" else parts[1]
        chr_submitter = parts[-1]
        cp_int = int(chr_cp)
        if init_cp <= cp_int <= fina_cp:
            result.content[chr_cp][1][submitter_no(chr_submitter)] = val

    # Remove empty codepoints
    result.content = {k: v for k, v in result.content.items() if v[1] != [None] * 12}

    # Merge RS from attribute files
    for att_entry in project.resources.attribute:
        if att_entry.check_status != COMPILED_OK:
            continue
        for section in att_entry.parse_data or []:
            for key, val in section.get("inf_cont", {}).items():
                cp_int = int(key)
                if init_cp <= cp_int <= fina_cp:
                    if key in result.content:
                        result.content[key][0] = val


def _merge_v_cont(result: BlockInfo, parsed: BlockInfo) -> None:
    """Merge V-type (IVS) block content."""
    for key, val in parsed.content.items():
        cp_s, sel_s, charset = key.split("\u3000")
        entry = [int(sel_s)] + val + [charset]
        if cp_s not in result.content:
            result.content[cp_s] = [entry]
        else:
            result.content[cp_s].append(entry)
    for k in result.content:
        result.content[k].sort()


def _merge_c_cont(result: BlockInfo, parsed: BlockInfo, project: Project) -> None:
    """Merge C-type (named character) block content with name list."""
    result.content = dict(parsed.content)
    name_list: list = []
    in_block = False
    for att_entry in project.resources.attribute:
        if not att_entry.parse_data:
            continue
        for section in att_entry.parse_data:
            for line in section.get("inf_cont", []):
                if not isinstance(line, list) or len(line) < 2:
                    continue
                if line[0] == "BLOCKHEADER":
                    in_block = isinstance(line[1], list) and len(line[1]) >= 1 and line[1][0] == parsed.name
                if in_block:
                    name_list.append(line)
    result.content["names_list"] = name_list


# ── Settings building ───────────────────────────────────────────────


def default_setting(blk_type: str, font_names: list[str]) -> dict:
    """Create a default settings dict for a block type."""
    defaults = {
        "print": 1,
        "column": 0,
        "yellow": [],
        "blue": [],
        "title": 0,
    }
    if blk_type in ("H", "W"):
        defaults["format"] = 0
        defaults["font"] = [[0, "(none)"] for _ in range(12)]
    elif blk_type == "V":
        defaults["format"] = 2
        defaults["font"] = [0, "(none)"]
    elif blk_type == "C":
        defaults["format"] = 0
        defaults["font"] = [0, "(none)"]
    return defaults


def build_settings(project: Project) -> list[BlockSetting]:
    """Build ``settings`` from ``blocks`` with defaults."""
    settings: list[BlockSetting] = []
    font_names = [f.basename for f in project.resources.font]

    for blk in project.blocks:
        setting = BlockSetting(
            name=blk.name,
            type=blk.type,
            start_cp=blk.start_cp,
            end_cp=blk.end_cp,
            content=default_setting(blk.type, font_names),
        )
        settings.append(setting)

    project.settings = settings
    return settings
