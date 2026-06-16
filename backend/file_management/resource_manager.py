"""High-level resource lifecycle -- import, parse, remove, build.

Sits on top of ``parser`` and ``models.project`` to provide
the operations that were previously spread across ``tools.py``.
"""

from __future__ import annotations

from os.path import splitext
from typing import Optional

from backend.file_management.parser import parse_attribute_file, parse_block_file, submitter_no
from backend.file_management.validator import BugEntry, has_errors
from backend.models.dataclasses import BlockInfo, BlockSetting
from backend.models.project import VALID_IMPORT_EXTS, Project

# -- Status constants ------------------------------------------------

UNCOMPILED = 0
COMPILE_FAILED = 1
COMPILED_OK = 2

# -- Resource import -------------------------------------------------


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


# -- Resource parsing ------------------------------------------------


# -- Font parsing ----------------------------------------------------


def parse_font_file(path: str) -> tuple[Optional[dict], list]:
    """Validate a TTF/OTF font file and extract basic metadata.

    Returns (metadata_dict, bugs_list).
    """
    bugs: list = []
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path)
        # Basic validation -- check required tables
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

    Supports .tsv (data files) and .ttf/.otf (font files).
    Returns the bug list from parsing.
    """

    ext = splitext(path)[1].lower()

    # -- Font files ---------------------------------------------
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

    # -- TSV data files (multi-type) ----------------------------
    if ext != ".tsv":
        return []

    parsed, bugs = parse_data_tsv(path)
    rsc = project.find_resource(path)
    if rsc is None:
        return bugs

    if has_errors(bugs):
        rsc.check_status = COMPILE_FAILED
    else:
        rsc.parse_data = parsed
        rsc.check_status = COMPILED_OK
    return bugs


def _get_parser_for_type(tsv_type: str):
    """Return the appropriate parser function for a TSV section type code."""
    if tsv_type in ("RF-W", "RF-H", "RF-V"):
        return parse_block_file
    if tsv_type in ("RS-W", "RS-H"):
        return parse_attribute_file
    if tsv_type == "NL":
        return parse_nameslist_file
    if tsv_type == "CD":
        return parse_ucd_file
    if tsv_type == "FT":
        return parse_cfl_file
    return None


def parse_resource(project: Project, path: str) -> tuple[Optional[list], list]:
    """Parse a resource and return (parsed_data, bugs)."""
    ext = splitext(path)[1].lower()
    if ext != ".tsv":
        return None, []
    return parse_data_tsv(path)


# ==================================================================
#  Multi-type TSV parser
# ==================================================================

_ALL_TSV_TYPES = {"RF-W", "RF-H", "RF-V", "RS-W", "RS-H", "NL", "CD", "FT"}


def parse_data_tsv(path: str) -> tuple[dict, list]:
    """Parse a .tsv file that may contain multiple section types.

    Sections are delimited by ``#`` header lines::\n
        # <range>; <name>; <TYPE>

    Each section is dispatched to the appropriate sub-parser.
    Returns a unified ``parse_data`` dict and bug list.
    """
    import tempfile
    import os

    bugs: list = []
    result: dict = {}

    # -- Read file and split into sections ---------------------
    sections: list[tuple[str, list[str]]] = []
    current_header = ""
    current_lines: list[str] = []

    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                if not line.strip():
                    continue
                if line.lower() == "# eof":
                    break
                if line.startswith("#"):
                    # Check if this is a section header or a comment
                    if _is_section_header(line):
                        # Flush previous section
                        if current_header:
                            sections.append((current_header, current_lines))
                        current_header = line
                        current_lines = []
                    else:
                        # Comment line within current section
                        if current_header:
                            current_lines.append(line)
                else:
                    if current_header:  # skip lines before first header
                        current_lines.append(line)
            # Flush last section
            if current_header:
                sections.append((current_header, current_lines))
    except Exception as exc:
        bugs.append(BugEntry(0, "C000", path, f"Read error: {exc}"))
        return result, bugs

    if not sections:
        bugs.append(BugEntry(1, "C013", path, "No data sections found in TSV file"))
        return result, bugs

    # -- Parse each section ------------------------------------
    block_list: list = []
    attr_list: list = []

    for header, lines in sections:
        type_code = _header_type(header)
        parser_fn = _get_parser_for_type(type_code)
        if parser_fn is None:
            bugs.append(BugEntry(1, "C014", path, f"Unknown TSV section type: {type_code}"))
            continue
        if not lines:
            continue

        # Write section lines to a temp file for the parser
        hdr_line = header.lstrip("#").strip()
        hdr_parts = hdr_line.split(";")
        section_name = hdr_parts[1].strip() if len(hdr_parts) >= 2 else type_code
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in section_name).strip()[:40]
        fd, tmp_path = tempfile.mkstemp(suffix=".tsv", prefix=f"unipage_{safe_name}_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                tf.write(header + "\n")
                tf.write("\n".join(lines) + "\n")
                tf.write("# EOF\n")

            parsed, sec_bugs = parser_fn(tmp_path)
            bugs.extend(sec_bugs)

            if parsed is not None:
                if type_code in ("RF-W", "RF-H", "RF-V"):
                    if isinstance(parsed, list):
                        block_list.extend(parsed)
                    else:
                        block_list.append(parsed)
                elif type_code in ("RS-W", "RS-H"):
                    if isinstance(parsed, list):
                        attr_list.extend(parsed)
                    else:
                        attr_list.append(parsed)
                elif type_code == "NL":
                    result.update(parsed if isinstance(parsed, dict) else {})
                elif type_code == "CD":
                    result.update(parsed if isinstance(parsed, dict) else {})
                elif type_code == "FT":
                    result.update(parsed if isinstance(parsed, dict) else {})
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # -- Assemble result ---------------------------------------
    if block_list:
        result["blocks"] = [b.to_dict() if isinstance(b, BlockInfo) else b for b in block_list]
    if attr_list:
        result["attributes"] = attr_list

    return result, bugs


def _header_type(header: str) -> str:
    """Extract the type code from a TSV ``#`` header line."""
    parts = header.lstrip("#").strip().split(";")
    if len(parts) >= 3:
        return parts[2].strip()
    return "unknown"


def _is_section_header(line: str) -> bool:
    """Check if a ``#`` line is a section header (3 semicolon-delimited fields)."""
    parts = line.lstrip("#").strip().split(";")
    if len(parts) >= 3:
        type_code = parts[2].strip()
        return type_code in _ALL_TSV_TYPES
    return False


# -- Block building from parsed data ---------------------------------


def build_blocks(project: Project) -> list[BlockInfo]:
    """Rebuild ``blocks`` from parsed data resources.

    Returns the new block list.
    """
    blocks: list[BlockInfo] = []

    def _extract(parsed_data):
        """Yield BlockInfo from various parse_data shapes."""
        if isinstance(parsed_data, list):
            for item in parsed_data:
                yield from _extract(item)
        elif isinstance(parsed_data, dict):
            # Unified parse_data: {"blocks": [...], "attributes": [...], ...}
            if "blocks" in parsed_data:
                for b in parsed_data["blocks"]:
                    if isinstance(b, BlockInfo):
                        yield b
                    elif isinstance(b, dict) and "type" in b:
                        yield BlockInfo.from_dict(b)
            elif "type" in parsed_data and "name" in parsed_data:
                yield BlockInfo.from_dict(parsed_data)
        elif isinstance(parsed_data, BlockInfo):
            yield parsed_data

    for entry in project.resources.data:
        if entry.check_status != COMPILED_OK or not entry.parse_data:
            continue
        for info in _extract(entry.parse_data):
            block = _merge_block_data(info, project)
            blocks.append(block)

    project.blocks = blocks

    # -- Non-CJK blocks from NamesList data ---------------------
    build_non_cjk_blocks(project)
    return project.blocks


def _merge_block_data(parsed: BlockInfo, project: Project) -> BlockInfo:
    """Merge parsed block data with RS info from data files."""
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

    if bt in ("RF-H", "RF-W"):
        _merge_hw_cont(result, parsed, init_cp, fina_cp, project)
    elif bt == "RF-V":
        _merge_v_cont(result, parsed)
    elif bt == "RS-W":
        # RS blocks: simple content copy
        result.content = dict(parsed.content)

    return result


def _merge_hw_cont(result: BlockInfo, parsed: BlockInfo, init_cp: int, fina_cp: int, project: Project) -> None:
    """Merge H/W block content with 12-slot source arrays and RS info."""
    # Initialise all slots
    for cp in range(init_cp, fina_cp + 1):
        result.content[str(cp)] = [None, [None] * 12]

    # Fill from parsed data
    for key, val in parsed.content.items():
        parts = key.split("\u3000")
        chr_cp = parts[0] if result.type == "RF-H" else parts[1]
        chr_submitter = parts[-1]
        cp_int = int(chr_cp)
        if init_cp <= cp_int <= fina_cp:
            result.content[chr_cp][1][submitter_no(chr_submitter)] = val

    # Remove empty codepoints
    result.content = {k: v for k, v in result.content.items() if v[1] != [None] * 12}

    # Merge RS from ALL data resources
    for att_entry in project.resources.data:
        if att_entry.check_status != COMPILED_OK:
            continue
        for section in att_entry.parse_data or []:
            if not isinstance(section, dict):
                continue
            for key, val in section.get("inf_cont", {}).items():
                try:
                    cp_int = int(key)
                except (ValueError, TypeError):
                    continue
                if init_cp <= cp_int <= fina_cp:
                    if key in result.content:
                        result.content[key][0] = val


def _merge_v_cont(result: BlockInfo, parsed: BlockInfo) -> None:
    """Merge V-type (IVS) block content."""
    for key, val in parsed.content.items():
        parts = key.split("\u3000")
        cp_s, sel_s, charset = parts[0], parts[1], parts[2]
        entry = [int(sel_s)] + val + [charset]
        if cp_s not in result.content:
            result.content[cp_s] = [entry]
        else:
            result.content[cp_s].append(entry)
    for k in result.content:
        result.content[k].sort()


# -- Settings building -----------------------------------------------


def default_setting(blk_type: str, font_names: list[str]) -> dict:
    """Create a default settings dict for a block type."""
    defaults = {
        "print": 1,
        "column": 0,
        "yellow": [],
        "blue": [],
        "title": 0,
    }
    if blk_type in ("RF-H", "RF-W"):
        defaults["format"] = 0
    elif blk_type == "RF-V":
        defaults["format"] = 2
    return defaults


def build_settings(project: Project) -> list[BlockSetting]:
    """Build ``settings`` from ``blocks`` with defaults (both CJK and non-CJK)."""
    settings: list[BlockSetting] = []
    font_names = [f.basename for f in project.resources.font]

    for blk in project.blocks:
        if blk.type == "NL":
            continue  # handled by build_non_cjk_settings
        setting = BlockSetting(
            name=blk.name,
            type=blk.type,
            start_cp=blk.start_cp,
            end_cp=blk.end_cp,
            content=default_setting(blk.type, font_names),
        )
        settings.append(setting)

    project.settings = settings

    # -- Non-CJK settings --------------------------------------
    build_non_cjk_settings(project)
    return project.settings


# ==================================================================
#  Non-CJK resource parsing
# ==================================================================


def parse_cfl_file(path: str) -> tuple[Optional[list], list]:
    """Parse a CFL (Character Font List) file.

    Returns (parsed_data, bugs).  parsed_data is a list of font config dicts.
    """
    from backend.non_cjk_generation.parsers import parse_cfl

    bugs: list = []
    try:
        chart_fonts, common_fonts = parse_cfl(path)
    except Exception as exc:
        bugs.append(BugEntry(0, "N001", path, f"CFL parse error: {exc}"))
        return None, bugs

    result = {
        "chart_fonts": [
            {
                "font_name": c.font_name,
                "size": c.size,
                "offset": c.offset,
                "range_start": c.range_start,
                "range_end": c.range_end,
                "excludes": c.excludes,
                "min_size": c.min_size,
            }
            for c in chart_fonts
        ],
        "common_fonts": [
            {
                "font_name": c.font_name,
                "size": c.size,
                "offset": c.offset,
                "range_start": c.range_start,
                "range_end": c.range_end,
                "excludes": c.excludes,
                "min_size": c.min_size,
            }
            for c in common_fonts
        ],
    }
    return result, bugs


def parse_nameslist_file(path: str) -> tuple[Optional[dict], list]:
    """Parse a NamesList file and extract block info + entries.

    Returns (parsed_data, bugs) where parsed_data is a dict with:
        - block_name, start_cp, end_cp
        - entries_count
    """
    from backend.non_cjk_generation.parsers import detect_block_from_nameslist, parse_nameslist

    bugs: list = []
    try:
        block_name, start_cp, end_cp = detect_block_from_nameslist(path)
        if not block_name:
            bugs.append(BugEntry(1, "N002", path, "No block header (@@) found in NamesList file"))
            return None, bugs

        # Validate block alignment: start must end with 0, end must end with F
        if start_cp % 16 != 0:
            bugs.append(BugEntry(0, "J001", path, f"Block start U+{start_cp:04X} not aligned to 16-cp boundary"))
        if end_cp % 16 != 15:
            bugs.append(
                BugEntry(0, "J002", path, f"Block end U+{end_cp:04X} not aligned to 16-cp boundary (must end with F)")
            )

        entries = parse_nameslist(path)

        result = {
            "block_name": block_name,
            "start_cp": start_cp,
            "end_cp": end_cp,
            "entries_count": len(entries),
            "entries_summary": _summarize_nameslist_entries(entries),
        }
        return result, bugs
    except Exception as exc:
        bugs.append(BugEntry(0, "N003", path, f"NamesList parse error: {exc}"))
        return None, bugs


def _summarize_nameslist_entries(entries: list) -> dict:
    """Summarize NamesList entries by type for display."""
    counts: dict[str, int] = {}
    for e in entries:
        t = e.type if hasattr(e, "type") else "unknown"
        counts[t] = counts.get(t, 0) + 1
    return counts


def parse_ucd_file(path: str) -> tuple[Optional[dict], list]:
    """Validate and summarize a UnicodeData.txt file.

    Returns (parsed_data, bugs).
    """
    bugs: list = []
    try:
        total = 0
        assigned = 0
        categories: dict[str, int] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) >= 2:
                    total += 1
                    cat = parts[2] if len(parts) >= 3 else "?"
                    categories[cat] = categories.get(cat, 0) + 1
                    try:
                        int(parts[0], 16)
                        assigned += 1
                    except ValueError:
                        pass

        result = {
            "total_lines": total,
            "assigned_codepoints": assigned,
            "categories": categories,
        }
        return result, bugs
    except Exception as exc:
        bugs.append(BugEntry(0, "N004", path, f"UnicodeData parse error: {exc}"))
        return None, bugs


# ==================================================================
#  Non-CJK block & settings building
# ==================================================================


def build_non_cjk_blocks(project: Project) -> list[BlockInfo]:
    """Build NL blocks from parsed NamesList data in any data resource."""
    blocks: list[BlockInfo] = []
    for entry in project.resources.data:
        if entry.check_status != COMPILED_OK or not entry.parse_data:
            continue
        data = entry.parse_data
        # Skip block lists — look for NamesList data (has block_name)
        if isinstance(data, list):
            continue
        if not isinstance(data, dict):
            continue
        block_name = data.get("block_name", "")
        if not block_name:
            continue

        start_cp = data.get("start_cp", 0)
        end_cp = data.get("end_cp", 0)

        existing = next((b for b in blocks if b.name == block_name), None)
        if existing:
            continue

        block = BlockInfo(
            name=block_name,
            type="NL",
            start_cp=start_cp,
            end_cp=end_cp,
            content={
                "entries_count": data.get("entries_count", 0),
                "entries_summary": data.get("entries_summary", {}),
            },
        )
        blocks.append(block)

    existing_names = {b.name for b in project.blocks}
    for blk in blocks:
        if blk.name not in existing_names:
            project.blocks.append(blk)

    return blocks


def default_non_cjk_setting(block_name: str, start_cp: int, end_cp: int) -> dict:
    """Create default settings for a NL block."""
    return {
        "print": 1,
        "title_page": 1,
        "chart_page_base": 1,
        "yellow": [],
        "purple": [],
    }


def build_non_cjk_settings(project: Project) -> list[BlockSetting]:
    """Build settings for NL blocks."""
    settings: list[BlockSetting] = []
    for blk in project.blocks:
        if blk.type != "NL":
            continue
        setting = BlockSetting(
            name=blk.name,
            type=blk.type,
            start_cp=blk.start_cp,
            end_cp=blk.end_cp,
            content=default_non_cjk_setting(blk.name, blk.start_cp, blk.end_cp),
        )
        settings.append(setting)

    # Merge with existing settings (keep non-N settings intact)
    existing = {s.name: s for s in project.settings}
    for st in settings:
        if st.name not in existing:
            project.settings.append(st)
        else:
            # Update existing non-CJK settings with any new defaults
            es = existing[st.name]
            for key, val in st.content.items():
                if key not in es.content:
                    es.content[key] = val

    return settings
