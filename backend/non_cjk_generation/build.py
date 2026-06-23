#!/usr/bin/env python3
"""
Unicode Code Chart PDF Builder -- CLI entry point.

Inputs:
  1. CFL file         -> fonts.cfl (codepoint -> font mapping)
  2. NamesList file   -> NamesList.txt (character names & annotations)
  3. Font directory   -> .ttf/.otf files for glyph rendering
  4. UnicodeData.txt  -> assigned codepoints (for reserved-cell hatching)

Pipeline:
  Parse CFL + NamesList  -> Compute layout  -> Render PDF

Usage:
  python -m backend.non_cjk_generation.build \\
      --block "Basic Latin" --start 0x0020 --end 0x007F \\
      --cfl path/to/fonts.cfl \\
      --nameslist path/to/NamesList.txt \\
      --fonts path/to/data/fonts/ \\
      --ucd path/to/UnicodeData.txt \\
      --output output.pdf
"""

from __future__ import annotations

import argparse
import json


def build_pdf(
    cfl_path: str = "",
    nameslist_path: str = "",
    data_tsv_path: str = "",
    font_dir: str = "",
    ucd_path: str = "",
    output_path: str = "output.pdf",
    structure_path: str = "",
    version: str = "17.0.0",
    short_version: str = "17.0",
    year: str = "2025",
    column_count: int = 24,
    block_name: str = "",
    start_cp: int = 0,
    end_cp: int = 0,
    draft_mode: bool = False,
) -> str:
    """Run the full pipeline: parse -> layout -> render.

    Block info auto-detected from NamesList.  Returns the output PDF path.
    """
    from backend.non_cjk_generation.layout import generate_page_structure
    from backend.non_cjk_generation.parsers import detect_block_from_nameslist
    from backend.non_cjk_generation.renderer import render_pdf

    if not block_name:
        src = data_tsv_path or nameslist_path
        block_name, start_cp, end_cp = detect_block_from_nameslist(src)

    # -- Step 1: Compute page layout --------------------------
    print("=" * 60)
    print(f"Unicode Chart PDF -- {block_name} (U+{start_cp:04X}-U+{end_cp:04X})")
    print("=" * 60)

    print("\n[1/2] Computing page layout...")
    print(f"  CFL:       {cfl_path}")
    print(f"  NamesList: {nameslist_path}")
    print(f"  Version:   {version}")

    pages_data = generate_page_structure(
        cfl_path=cfl_path,
        nameslist_path=nameslist_path,
        data_tsv_path=data_tsv_path,
        block_name=block_name,
        start_cp=start_cp,
        end_cp=end_cp,
        version=version,
        short_version=short_version,
        year=year,
        column_count=column_count,
        ucd_path=ucd_path,
        font_dir=font_dir,
        draft_mode=draft_mode,
    )

    print(f"  Generated {len(pages_data)} pages:")
    for p in pages_data:
        print(f"    Page {p['page_num']}: {len(p['text_spans'])} spans, {len(p['drawings'])} drawings")

    if structure_path:
        with open(structure_path, "w", encoding="utf-8") as f:
            json.dump(pages_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved structure to {structure_path}")

    # -- Step 2: Render PDF -----------------------------------
    print("\n[2/2] Rendering PDF...")
    print(f"  Fonts dir: {font_dir}")
    if ucd_path:
        print(f"  UCD:        {ucd_path}")

    render_pdf(
        pages_data=pages_data,
        output_path=output_path,
        font_dir=font_dir,
        ucd_path=ucd_path if ucd_path else None,
        block_start_cp=start_cp,
        block_end_cp=end_cp,
    )

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Unicode Code Chart PDF Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Example:
  python -m backend.non_cjk_generation.build --cfl fonts.cfl --nameslist names.txt --fonts ./data/fonts/ -o out.pdf
        """,
    )

    # Required
    parser.add_argument("--cfl", type=str, help="Path to fonts.cfl")
    parser.add_argument("--nameslist", type=str, help="Path to NamesList.txt (block auto-detected)")
    parser.add_argument("--fonts", type=str, help="Directory containing .ttf/.otf font files")
    parser.add_argument("--ucd", type=str, help="Path to UnicodeData.txt")
    parser.add_argument("--output", "-o", type=str, help="Output PDF path")
    parser.add_argument("--structure", type=str, help="Save page_structure JSON to path")

    # Optional overrides (auto-detected from NamesList)
    parser.add_argument("--block", type=str, help="Block name override")
    parser.add_argument("--start", type=str, help="Start codepoint override")
    parser.add_argument("--end", type=str, help="End codepoint override")

    # Version info
    parser.add_argument("--version", type=str, default="17.0.0", help="Unicode version")
    parser.add_argument("--short-version", type=str, default="17.0", help="Short version")
    parser.add_argument("--year", type=str, default="2025", help="Copyright year")
    parser.add_argument("--columns", type=int, default=24, help="Code chart columns")
    parser.add_argument("--draft-mode", action="store_true", help="Renumber all code points sequentially from 0")

    args = parser.parse_args()

    # Manual mode
    if not all([args.cfl, args.nameslist, args.fonts]):
        parser.error("--cfl, --nameslist, --fonts are required")

    start_cp = 0
    end_cp = 0
    if args.start:
        start_cp = int(args.start, 16) if args.start.startswith("0x") else int(args.start)
    if args.end:
        end_cp = int(args.end, 16) if args.end.startswith("0x") else int(args.end)

    build_pdf(
        cfl_path=args.cfl,
        nameslist_path=args.nameslist,
        font_dir=args.fonts,
        ucd_path=args.ucd or "",
        output_path=args.output or "output.pdf",
        structure_path=args.structure or "",
        version=args.version,
        short_version=args.short_version,
        year=args.year,
        column_count=args.columns,
        block_name=args.block or "",
        start_cp=start_cp,
        end_cp=end_cp,
        draft_mode=args.draft_mode,
    )


if __name__ == "__main__":
    main()
