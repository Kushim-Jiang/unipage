"""FastAPI routes for the Unipage backend."""

from __future__ import annotations

import os
import threading
from os.path import abspath, basename, exists, splitext
from typing import Optional

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.cjk_generation.layout import make_proof
from backend.cjk_generation.pdf_builder import generate_pdf
from backend.file_management.parser import detect_tsv_type, parse_project_file
from backend.file_management.resource_manager import (
    build_blocks,
    build_settings,
    import_resource,
    parse_and_update,
    remove_resource,
)
from backend.file_management.validator import bug_summary
from backend.models.project import Project, sanitize_filename
from backend.models.state import STATE

# ==================================================================
# Pydantic schemas
# ==================================================================


class ProjectInfo(BaseModel):
    name: str
    directory: str
    file: str


class ResourceEntry(BaseModel):
    basename: str
    check_status: int
    url: str
    parse_data: Optional[list] = None


class BlockInfo(BaseModel):
    name: str
    type: str
    start_cp: int
    end_cp: int
    char_count: int = 0
    child_count: int = 0


class SettingInfo(BaseModel):
    name: str
    type: str
    content: dict


class CycleOptionRequest(BaseModel):
    name: str
    field: str
    forward: bool
    source_index: Optional[int] = None


class ColourToggleRequest(BaseModel):
    name: str
    codepoint: int
    colour: str  # "yellow" or "blue"


class BugReport(BaseModel):
    errors: list
    warnings: list
    infos: list
    counts: dict


# ==================================================================
# Router
# ==================================================================

router = APIRouter(prefix="/api")


def _require_project() -> None:
    """Ensure a project is open; raise 400 otherwise."""
    if not STATE.has_project:
        raise HTTPException(400, "B002: No project open.")


# -- Project CRUD ----------------------------------------------------


@router.post("/project/create")
def create_project(info: ProjectInfo):
    """Create a new project."""
    if STATE.has_project:
        raise HTTPException(400, "B001: A project is already open. Close it first.")

    from backend.models.dataclasses import ProjectInfo as ProjectInfoDC

    project_dir = info.directory or f"projects/{sanitize_filename(info.name)}"
    project_file = f"{project_dir}/{sanitize_filename(info.name)}.json"

    proj = Project()
    proj.project_info = ProjectInfoDC(
        project_name=info.name,
        project_dir=project_dir,
        project_file=project_file,
    )
    os.makedirs(project_dir, exist_ok=True)
    open(project_file, "w").close()

    import_resource(proj, project_file, project_file, 2)
    STATE.project = proj
    proj.save()
    return {"status": "ok", "project_file": project_file}


@router.post("/project/open")
def open_project(path: str):
    """Open an existing .json project file by path."""
    if STATE.has_project:
        raise HTTPException(400, "B001: A project is already open. Close it first.")
    if not exists(path):
        raise HTTPException(404, f"File not found: {path}")
    return _do_open(path)


@router.post("/project/load")
def load_project(data: dict):
    """Open a project from raw JSON content (no filesystem path needed)."""
    if STATE.has_project:
        raise HTTPException(400, "B001: A project is already open. Close it first.")
    if not data or "basic_info" not in data:
        raise HTTPException(400, "Invalid project file: missing 'basic_info'")
    try:
        proj = Project.from_dict(data)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse project file: {exc}")
    STATE.project = proj
    return {
        "status": "ok",
        "basic_info": proj.project_info.to_dict(),
        "bugs": {"errors": [], "warnings": [], "infos": [], "counts": {"errors": 0, "warnings": 0, "infos": 0}},
    }


def _do_open(path: str):
    """Shared logic: load a project from a .json file path."""
    proj, bugs = Project.load(path)
    if any(b.severity == 0 for b in bugs):
        STATE.project = None
        return {"status": "error", "bugs": bug_summary(bugs)}
    STATE.project = proj
    return {
        "status": "ok",
        "basic_info": proj.project_info.to_dict(),
        "bugs": bug_summary(bugs),
    }


@router.post("/project/save")
def save_project():
    """Save the current project."""
    _require_project()
    STATE.project.save()
    return {"status": "ok"}


@router.post("/project/close")
def close_project():
    """Close the current project."""
    STATE.reset()
    return {"status": "ok"}


@router.get("/project/status")
def project_status():
    """Return whether a project is open and its basic info."""
    if not STATE.has_project:
        return {"open": False}
    return {
        "open": True,
        "basic_info": STATE.project.project_info.to_dict(),
    }


# -- Resources -------------------------------------------------------


@router.get("/resources")
def list_resources():
    """List all resources in the current project."""
    _require_project()
    return STATE.project.resources.to_dict()


@router.post("/resources/import")
def import_file(path: str):
    """Import a resource file (copy into project dir)."""
    _require_project()
    proj = STATE.project
    dest = f"{proj.project_info.project_dir}/{basename(path)}"
    try:
        import_resource(proj, path, dest, 0)
        proj.save()
        return {"status": "ok", "dest": dest}
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/resources/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a resource file via multipart."""
    _require_project()
    proj = STATE.project
    dest = f"{proj.project_info.project_dir}/{file.filename}"
    content = await file.read()
    with open(dest, "wb") as fp:
        fp.write(content)
    try:
        import_resource(proj, None, dest, 0)
        proj.save()
        return {"status": "ok", "dest": dest}
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/resources")
def delete_resource(path: str):
    """Remove a resource from the project."""
    _require_project()
    if remove_resource(STATE.project, path):
        STATE.project.save()
        return {"status": "ok"}
    raise HTTPException(404, f"Resource not found: {path}")


@router.post("/resources/parse")
def parse_resources():
    """Parse all compiled-but-unparsed block and attribute resources (background thread with progress)."""
    _require_project()

    proj = STATE.project
    targets = [
        rsc
        for rsc in (proj.find_resources_by_type("data") + proj.find_resources_by_type("font"))
        if rsc.check_status == 0
    ]
    total = len(targets)
    STATE.parse_progress = 0.0
    STATE.parse_done = False
    STATE.parse_bugs = None

    def run():
        all_bugs = []
        for i, rsc in enumerate(targets):
            bugs = parse_and_update(proj, rsc.url)
            all_bugs.extend(bugs)
            STATE.parse_progress = (i + 1) / total * 100
        # Rebuild blocks and settings
        build_blocks(proj)
        build_settings(proj)
        proj.save()
        STATE.parse_bugs = bug_summary(all_bugs)
        STATE.parse_progress = 100.0
        STATE.parse_done = True

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


@router.get("/resources/parse-progress")
def parse_progress():
    """Poll current parse progress."""
    return {
        "progress": int(STATE.parse_progress),
        "done": STATE.parse_done,
        "bugs": STATE.parse_bugs,
    }


@router.get("/resources/parse-one")
def parse_one_resource(path: str):
    """Parse a single resource file and return its content + bugs."""
    from backend.file_management.resource_manager import _get_parser_for_type

    ext = splitext(path)[1].lower()
    if ext == ".json":
        parsed, bugs = parse_project_file(path)
    elif ext == ".tsv":
        tsv_type = detect_tsv_type(path)
        parser_fn = _get_parser_for_type(tsv_type)
        if parser_fn is None:
            raise HTTPException(400, f"Cannot determine type of TSV file: {path}")
        parsed, bugs = parser_fn(path)
    else:
        raise HTTPException(400, f"Cannot parse: {path}")
    return {"parsed": parsed, "bugs": bug_summary(bugs)}


# -- Blocks ----------------------------------------------------------


@router.get("/blocks")
def list_blocks():
    """Return all parsed block information."""
    _require_project()
    return [b.to_dict() for b in STATE.project.blocks]


@router.get("/blocks/{name}")
def get_block(name: str):
    """Return a single block by name."""
    _require_project()
    blk = STATE.project.get_block(name)
    if blk is None:
        raise HTTPException(404, f"Block not found: {name}")
    return blk.to_dict()


# -- Settings --------------------------------------------------------


@router.get("/settings")
def list_settings():
    """Return all block print settings."""
    _require_project()
    return [s.to_dict() for s in STATE.project.settings]


@router.post("/settings/cycle")
def cycle_option(req: CycleOptionRequest):
    """Cycle a setting option (prev/next)."""
    _require_project()
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    _SETTING_KEYS = ["print", "column", "format", "title"]
    _SETTING_RANGES = [2, 4, 3, 2]

    delta = 1 if req.forward else -1
    cont = setting.content

    if req.field in _SETTING_KEYS:
        idx = _SETTING_KEYS.index(req.field)
        cont[req.field] = (cont[req.field] + delta) % _SETTING_RANGES[idx]

    proj.save()
    return {"status": "ok", "setting": setting.to_dict()}


@router.post("/settings/colour-toggle")
def toggle_colour(req: ColourToggleRequest):
    """Toggle yellow/blue marking on a codepoint."""
    _require_project()
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    cont = setting.content
    if req.codepoint in cont.get(req.colour, []):
        cont[req.colour].remove(req.codepoint)
    else:
        cont[req.colour].append(req.codepoint)

    proj.save()
    return {"status": "ok", "setting": setting.to_dict()}


# -- Proof / PDF -----------------------------------------------------


@router.post("/proof/check")
def check_proof(name: str):
    """Check a block and generate a proof. Returns bugs and proof status."""
    _require_project()

    proof, bugs = make_proof(name)
    has_err = any(b.severity == 0 for b in bugs)
    return {
        "status": "failed" if has_err else "passed",
        "bugs": bug_summary(bugs),
        "proof_ready": proof is not None and not has_err,
    }


@router.post("/proof/generate")
def generate_pdf_proof(name: str):
    """Generate the PDF for a block's proof."""
    _require_project()

    proof, bugs = make_proof(name)
    if any(b.severity == 0 for b in bugs):
        return {"status": "error", "bugs": bug_summary(bugs)}

    if proof is None:
        return {"status": "error", "bugs": {"counts": {"errors": 1, "warnings": 0, "infos": 0}}}

    proj = STATE.project
    pdf_dir = f"{proj.project_info.project_dir}/pdf/"
    pdf_path = generate_pdf(proof, pdf_dir)

    return {"status": "ok", "pdf_path": pdf_path}


@router.post("/proof/check-all")
def check_all_proofs():
    """Check all printable blocks — CJK via make_proof, NL via check_nl_proof."""
    _require_project()

    proj = STATE.project
    cjk_targets = [s for s in proj.settings if s.content.get("print") == 1 and s.type != "NL"]
    nl_targets = [s for s in proj.settings if s.content.get("print") == 1 and s.type == "NL"]
    total = len(cjk_targets) + len(nl_targets)
    STATE.check_progress = 0.0
    STATE.check_done = False
    STATE.check_bugs = None
    STATE.proofs = []

    def run():
        from backend.models.dataclasses import BugEntry

        all_bugs: list[BugEntry] = []
        passing: list = []
        processed = 0

        # CJK proofs
        for setting in cjk_targets:
            proof, bugs = make_proof(setting.name)
            all_bugs.extend(bugs)
            if not any(b.severity == 0 for b in bugs) and proof is not None:
                passing.append(proof)
            processed += 1
            STATE.check_progress = processed / total * 100

        # NL proofs
        nl_results = _check_nl_proofs(nl_targets)
        all_bugs.extend(nl_results["bugs"])
        passing.extend(nl_results["proofs"])
        processed += len(nl_targets)
        STATE.check_progress = 100.0

        STATE.proofs = passing
        STATE.check_bugs = bug_summary(all_bugs)
        STATE.check_done = True

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


def _check_nl_proofs(nl_settings: list) -> dict:
    """Validate all NL blocks.

    Returns ``{"bugs": [...], "proofs": [...]}``.
    """
    from backend.models.dataclasses import BugEntry
    from backend.non_cjk_generation.parsers import parse_cfl, parse_nameslist

    bugs: list[BugEntry] = []
    proofs: list = []
    proj = STATE.project
    _ensure_non_cjk_resources(proj)
    nameslist_path, cfl_path, ucd_path = _find_data_paths(proj)

    for setting in nl_settings:
        name = setting.name
        block_bugs: list[BugEntry] = []

        # -- Check NamesList availability ------------------
        if not nameslist_path:
            block_bugs.append(BugEntry(1, "N002", name, "No NamesList data resource found."))
        else:
            try:
                nl_entries = parse_nameslist(nameslist_path)
                from backend.non_cjk_generation.parsers import extract_block_entries

                block_entries = extract_block_entries(nl_entries, setting.start_cp, setting.end_cp)
                name_count = sum(1 for e in block_entries if e.type == "name")
                if name_count == 0:
                    block_bugs.append(
                        BugEntry(
                            1,
                            "N008",
                            name,
                            f"No named characters found in range U+{setting.start_cp:04X}–U+{setting.end_cp:04X}.",
                        )
                    )
            except Exception as exc:
                block_bugs.append(BugEntry(0, "N003", name, f"NamesList parse error: {exc}"))

        # -- Check CFL / font availability -----------------
        if not cfl_path:
            block_bugs.append(BugEntry(1, "N010", name, "No font table (CFL) data resource found."))
        else:
            try:
                chart_fonts, _common_fonts = parse_cfl(cfl_path)
                available = {r.basename for r in proj.resources.font}
                available_stems = {splitext(b)[0] for b in available}
                missing = [
                    fc.font_name
                    for fc in chart_fonts
                    if fc.font_name not in available and fc.font_name not in available_stems
                ]
                if missing:
                    block_bugs.append(
                        BugEntry(1, "N011", name, f"Fonts not found in project: {', '.join(sorted(missing))}")
                    )
            except Exception as exc:
                block_bugs.append(BugEntry(0, "N001", name, f"CFL parse error: {exc}"))

        bugs.extend(block_bugs)
        has_errors = any(b.severity == 0 for b in block_bugs)
        if not has_errors:
            proofs.append({"name": name, "type": "NL", "start_cp": setting.start_cp, "end_cp": setting.end_cp})

    return {"bugs": bugs, "proofs": proofs}


@router.get("/proof/check-progress")
def check_progress():
    """Poll current check-all progress."""
    return {
        "progress": int(STATE.check_progress),
        "done": STATE.check_done,
        "bugs": STATE.check_bugs,
        "passing_count": len(STATE.proofs),
    }


@router.post("/proof/generate-all")
def generate_all_pdf():
    """Generate PDF for all cached proofs (stores progress in STATE for polling)."""
    _require_project()

    proj = STATE.project
    pdf_dir = f"{proj.project_info.project_dir}/pdf/"
    proofs = list(STATE.proofs)
    total = len(proofs)
    STATE.pdf_progress = 0.0
    STATE.pdf_results = None

    def run():
        results = []
        cjk_proofs = [p for p in proofs if not (isinstance(p, dict) and p.get("type") == "NL")]
        nl_proofs = [p for p in proofs if isinstance(p, dict) and p.get("type") == "NL"]
        # Generate Non-CJK PDFs using the shared pipeline
        if nl_proofs:
            nl_names = {p["name"] for p in nl_proofs}
            nl_targets = [
                s for s in proj.settings if s.type == "NL" and s.content.get("print") == 1 and s.name in nl_names
            ]
            if nl_targets:
                nl_results = _run_generate_all_non_cjk(proj, nl_targets, len(nl_targets), use_state=False)
                results.extend(nl_results)
        # Generate CJK PDFs
        for i, proof in enumerate(cjk_proofs):

            def cb(p: float):
                STATE.pdf_progress = (i + p) / total * 100

            pdf_path = generate_pdf(proof, pdf_dir, progress_callback=cb)
            results.append({"block": proof.name, "pdf_path": pdf_path})
            STATE.pdf_progress = (i + 1) / total * 100
        STATE.pdf_results = results
        STATE.pdf_progress = 100.0

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


@router.get("/proof/generate-progress")
def generate_progress():
    """Poll current PDF generation progress."""
    return {
        "progress": int(STATE.pdf_progress),
        "done": STATE.pdf_results is not None,
        "results": STATE.pdf_results or [],
    }


# ==================================================================
#  Non-CJK PDF generation
# ==================================================================


class NonCjkPdfRequest(BaseModel):
    block_name: str
    start_cp: int
    end_cp: int
    title_page: bool = True
    yellow: list[int] = []
    purple: list[int] = []
    draft_mode: bool = False


class NonCjkCycleRequest(BaseModel):
    name: str
    field: str
    forward: bool


class NonCjkColourToggleRequest(BaseModel):
    name: str
    codepoint: int
    colour: str  # "yellow" or "purple"


class SetPageStartRequest(BaseModel):
    name: str
    page_start: int


@router.post("/non-cjk/settings/page-start")
def set_non_cjk_page_start(req: SetPageStartRequest):
    """Set the starting page number (after title page) for a non-CJK block."""
    _require_project()
    if req.page_start < 1:
        raise HTTPException(400, "Page start must be a positive integer.")

    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    setting.content["chart_page_base"] = req.page_start
    proj.save()
    return {"status": "ok", "setting": setting.to_dict()}


@router.post("/non-cjk/generate-pdf")
def generate_non_cjk_pdf(req: NonCjkPdfRequest):
    """Generate a non-CJK PDF for a block using the nameslist/cfl pipeline."""
    _require_project()

    proj = STATE.project
    _ensure_non_cjk_resources(proj)

    pdf_dir = f"{proj.project_info.project_dir}/pdf/"
    os.makedirs(pdf_dir, exist_ok=True)
    safe_name = sanitize_filename(req.block_name)
    output_path = f"{pdf_dir}{safe_name}.pdf"

    # Collect resource paths from parsed data
    nameslist_path, cfl_path, ucd_path = _find_data_paths(proj)
    font_dir = proj.project_info.project_dir
    combining_cps = _extract_combining_cps(ucd_path)

    # Parse NamesList and CFL into objects — non_cjk_generation works with objects
    from backend.non_cjk_generation.parsers import parse_cfl, parse_nameslist, extract_block_entries

    if not nameslist_path:
        raise HTTPException(400, "N005: No NamesList resource found.")
    if not cfl_path:
        raise HTTPException(400, "N006: No CFL resource found.")

    chart_fonts, _ = parse_cfl(cfl_path)
    all_entries = parse_nameslist(nameslist_path)
    block_entries = extract_block_entries(all_entries, req.start_cp, req.end_cp)
    assigned_cps = {int(e.codepoint, 16) for e in block_entries if e.codepoint and e.type == "name"}

    # Auto-compute column count: ceil(char_count / 16)
    char_count = req.end_cp - req.start_cp + 1
    column_count = (char_count + 15) // 16

    # Get chart_page_base from settings if available
    setting = proj.get_setting(req.block_name)
    chart_page_base = setting.content.get("chart_page_base", 1) if setting else 1

    try:
        from backend.non_cjk_generation.layout import generate_page_structure
        from backend.non_cjk_generation.renderer import render_pdf

        # Build extra font registrations for block-specific fonts
        extra_fonts = _build_nl_extra_fonts(proj, cfl_path)
        extra_font_dirs = [
            f"{font_dir}/data/fonts",
            f"{font_dir}/data",
            f"{os.path.dirname(os.path.dirname(os.path.dirname(__file__)))}/data/fonts",
            f"{os.path.dirname(os.path.dirname(os.path.dirname(__file__)))}/data",
        ]

        pages_data = generate_page_structure(
            block_name=req.block_name,
            start_cp=req.start_cp,
            end_cp=req.end_cp,
            column_count=column_count,
            font_dir=font_dir,
            title_md_path=_find_title_md(proj),
            chart_page_base=chart_page_base,
            extra_font_dirs=extra_font_dirs,
            chart_fonts=chart_fonts,
            nameslist_entries=all_entries,
            assigned_cps=assigned_cps,
            combining_cps=combining_cps,
            draft_mode=req.draft_mode,
        )

        render_pdf(
            pages_data=pages_data,
            output_path=output_path,
            font_dir=font_dir,
            block_start_cp=req.start_cp,
            block_end_cp=req.end_cp,
            extra_fonts=extra_fonts,
            extra_font_dirs=extra_font_dirs,
            assigned_cps=assigned_cps,
        )

        return {
            "status": "ok",
            "pdf_path": output_path,
            "pages": len(pages_data),
        }
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        traceback.print_exc()
        raise HTTPException(500, f"N007: PDF generation failed: {exc}\n{tb}")


def _ensure_non_cjk_resources(proj) -> None:
    """Auto-parse unparsed data resources if needed."""
    from backend.file_management.resource_manager import COMPILED_OK, parse_and_update

    for rsc in proj.resources.data:
        if rsc.check_status != COMPILED_OK and rsc.url:
            parse_and_update(proj, rsc.url)


def _find_data_paths(proj) -> tuple[str, str, str]:
    """Scan parsed data resources for NL, FT, CD paths.

    Unified parse_data may be a dict or list.  Returns
    (nameslist_path, cfl_path, ucd_path).
    """
    nameslist_path = ""
    cfl_path = ""
    ucd_path = ""

    for entry in proj.resources.data:
        if entry.check_status != 2 or not entry.url:
            continue
        data = entry.parse_data
        if not data:
            continue

        # Unified format: dict with block_name / chart_fonts / categories
        if isinstance(data, dict):
            if not nameslist_path and data.get("block_name"):
                nameslist_path = entry.url
            if not cfl_path and data.get("chart_fonts"):
                cfl_path = entry.url
            if not ucd_path and (data.get("categories") or data.get("assigned_codepoints")):
                ucd_path = entry.url
        # List of dicts (e.g. blocks)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if not nameslist_path and item.get("block_name"):
                        nameslist_path = entry.url
                    if not cfl_path and item.get("chart_fonts"):
                        cfl_path = entry.url

    return nameslist_path, cfl_path, ucd_path


def _extract_combining_cps(ucd_path: str) -> set[int]:
    """Extract combining-mark codepoints (General Category M*) from a UCD file."""
    cps: set[int] = set()
    if not ucd_path or not os.path.exists(ucd_path):
        return cps
    try:
        with open(ucd_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                parts = line.split(";")
                if len(parts) >= 3 and parts[2].startswith("M"):
                    try:
                        cps.add(int(parts[0], 16))
                    except ValueError:
                        pass
    except Exception:
        pass
    return cps


def _build_nl_extra_fonts(proj, cfl_path: str) -> list[tuple[str, str, str]]:
    """Build (family, style, filename) tuples for block-specific CFL fonts."""
    if not cfl_path:
        return []
    from backend.non_cjk_generation.parsers import parse_cfl

    try:
        chart_fonts, _common_fonts = parse_cfl(cfl_path)
    except Exception:
        return []

    available = {r.basename: r.url for r in proj.resources.font}
    available_stems = {splitext(b)[0]: b for b in available}

    extra: list[tuple[str, str, str]] = []
    for fc in chart_fonts:
        fn = fc.font_name
        filename = available.get(fn) or available.get(available_stems.get(fn, ""))
        if filename:
            extra.append((fn, "", filename))
    return extra


def _find_title_md(proj) -> str:
    """Locate a title.md template for the non‑CJK title page.

    Checks (in order):
      1. ``{project_dir}/title.md``
      2. ``{workspace}/data/title.md``
    """
    import backend

    project_title = os.path.join(proj.project_info.project_dir, "title.md")
    if os.path.exists(project_title):
        return project_title

    workspace_title = os.path.join(
        os.path.dirname(os.path.dirname(backend.__file__)),
        "data",
        "title.md",
    )
    if os.path.exists(workspace_title):
        return workspace_title

    return ""


@router.get("/non-cjk/blocks")
def list_non_cjk_blocks():
    """Return only NL blocks."""
    _require_project()
    return [b.to_dict() for b in STATE.project.blocks if b.type == "NL"]


@router.get("/non-cjk/blocks/{name:path}")
def get_non_cjk_block(name: str):
    """Return a single NL block with its parsed NamesList entries."""
    _require_project()
    blk = STATE.project.get_block(name)
    if blk is None:
        raise HTTPException(404, f"Block not found: {name}")
    if blk.type != "NL":
        # Return basic block info — frontend may still display it
        return {**blk.to_dict(), "entries": []}

    # Find the data resource with NamesList content for this block
    proj = STATE.project
    _ensure_non_cjk_resources(proj)
    nameslist_path, _, _ = _find_data_paths(proj)

    entries_data = []
    if nameslist_path:
        from backend.non_cjk_generation.parsers import parse_nameslist, extract_block_entries

        try:
            all_entries = parse_nameslist(nameslist_path)
            block_entries = extract_block_entries(all_entries, blk.start_cp, blk.end_cp)
            entries_data = [
                {
                    "codepoint": e.codepoint,
                    "name": e.name,
                    "type": e.type,
                    "annotations": [
                        {
                            "type": a.type,
                            "text": a.text or a.name or "",
                            "target_cp": a.target_cp,
                            "target_name": a.target_name,
                        }
                        for a in e.annotations
                    ],
                }
                for e in block_entries
                if e.type in ("name", "reserved")
            ]
        except Exception:
            pass

    return {
        **blk.to_dict(),
        "entries": entries_data,
    }


@router.get("/non-cjk/settings")
def list_non_cjk_settings():
    """Return settings for NL blocks."""
    _require_project()
    return [s.to_dict() for s in STATE.project.settings if s.type == "NL"]


@router.post("/non-cjk/settings/cycle")
def cycle_non_cjk_option(req: NonCjkCycleRequest):
    """Cycle a non-CJK setting option (prev/next)."""
    _require_project()
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    delta = 1 if req.forward else -1

    if req.field == "print":
        setting.content["print"] = (setting.content.get("print", 1) + delta) % 2
    elif req.field == "title_page":
        setting.content["title_page"] = (setting.content.get("title_page", 1) + delta) % 2
    elif req.field == "draft_mode":
        current = bool(setting.content.get("draft_mode", False))
        setting.content["draft_mode"] = int(not current)

    proj.save()
    return {"status": "ok", "setting": setting.to_dict()}


@router.post("/non-cjk/settings/colour-toggle")
def toggle_non_cjk_colour(req: NonCjkColourToggleRequest):
    """Toggle yellow/purple marking on a codepoint for non-CJK blocks."""
    _require_project()
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    cont = setting.content
    colour = req.colour
    if colour not in ("yellow", "purple"):
        raise HTTPException(400, f"Invalid colour: {colour}. Use 'yellow' or 'purple'.")

    if req.codepoint in cont.get(colour, []):
        cont[colour].remove(req.codepoint)
    else:
        cont[colour].append(req.codepoint)

    proj.save()
    return {"status": "ok", "setting": setting.to_dict()}


@router.post("/non-cjk/generate-all")
def generate_all_non_cjk_pdf():
    """Generate PDF for all printable non-CJK blocks (background thread with progress)."""
    _require_project()

    proj = STATE.project
    targets = [s for s in proj.settings if s.type == "NL" and s.content.get("print") == 1]
    total = len(targets)
    STATE.pdf_progress = 0.0
    STATE.pdf_results = None

    def run():
        try:
            results = _run_generate_all_non_cjk(proj, targets, total)
            STATE.pdf_results = results
            STATE.pdf_progress = 100.0
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            traceback.print_exc()
            STATE.pdf_results = [
                {"block": "FATAL", "status": "error", "error": str(exc), "code": "N014", "traceback": tb}
            ]
            STATE.pdf_progress = 100.0

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


def _run_generate_all_non_cjk(proj, targets, total, use_state=True):
    print(f"[non-cjk] generate-all: {total} targets: {[s.name for s in targets]}")
    results = []
    _ensure_non_cjk_resources(proj)
    pdf_dir = f"{proj.project_info.project_dir}/pdf/"
    os.makedirs(pdf_dir, exist_ok=True)

    # Collect resource paths once (all data is .tsv)
    nameslist_path, cfl_path, ucd_path = _find_data_paths(proj)
    combining_cps = _extract_combining_cps(ucd_path)

    # Derive assigned codepoints from NamesList
    try:
        from backend.non_cjk_generation.parsers import parse_cfl, parse_nameslist, extract_block_entries

        chart_fonts, _ = parse_cfl(cfl_path)
        all_entries = parse_nameslist(nameslist_path)
        assigned_cps: set[int] = set()
        for setting in targets:
            block_entries = extract_block_entries(all_entries, setting.start_cp, setting.end_cp)
            for e in block_entries:
                if e.codepoint and e.type == "name":
                    assigned_cps.add(int(e.codepoint, 16))
    except Exception:
        import traceback as _tb

        _tb.print_exc()
        chart_fonts = None
        all_entries = None
        assigned_cps = None

    if not nameslist_path or not cfl_path:
        print(f"[non-cjk] Missing data: NL={bool(nameslist_path)} FT={bool(cfl_path)}")
        return results

    font_dir = proj.project_info.project_dir
    extra_fonts = _build_nl_extra_fonts(proj, cfl_path)
    title_md = _find_title_md(proj)
    extra_font_dirs = [
        f"{font_dir}/data/fonts",
        f"{font_dir}/data",
        f"{os.path.dirname(os.path.dirname(os.path.dirname(__file__)))}/data/fonts",
        f"{os.path.dirname(os.path.dirname(os.path.dirname(__file__)))}/data",
    ]

    from backend.non_cjk_generation.layout import generate_page_structure
    from backend.non_cjk_generation.renderer import render_pdf

    for i, setting in enumerate(targets):
        safe_name = sanitize_filename(setting.name)
        output_path = f"{pdf_dir}{safe_name}.pdf"

        try:
            char_count = setting.end_cp - setting.start_cp + 1
            col_count = (char_count + 15) // 16

            pages_data = generate_page_structure(
                block_name=setting.name,
                start_cp=setting.start_cp,
                end_cp=setting.end_cp,
                column_count=col_count,
                font_dir=font_dir,
                title_md_path=title_md,
                chart_page_base=setting.content.get("chart_page_base", 1),
                extra_font_dirs=extra_font_dirs,
                chart_fonts=chart_fonts,
                nameslist_entries=all_entries,
                assigned_cps=assigned_cps,
                combining_cps=combining_cps,
                draft_mode=setting.content.get("draft_mode", False),
            )

            render_pdf(
                pages_data=pages_data,
                output_path=output_path,
                font_dir=font_dir,
                block_start_cp=setting.start_cp,
                block_end_cp=setting.end_cp,
                extra_fonts=extra_fonts,
                extra_font_dirs=extra_font_dirs,
                assigned_cps=assigned_cps,
            )

            results.append({"block": setting.name, "pdf_path": output_path, "pages": len(pages_data), "status": "ok"})
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            traceback.print_exc()
            results.append(
                {
                    "block": setting.name,
                    "pdf_path": "",
                    "status": "error",
                    "error": f"N014: {exc}",
                    "code": "N014",
                    "traceback": tb,
                }
            )

        if use_state:
            STATE.pdf_progress = (i + 1) / total * 100

    return results


# ==================================================================
# Utils
# ==================================================================


@router.post("/utils/resolve-folder")
def resolve_folder(name: str = Body(..., embed=True)):
    """Resolve a folder name to an absolute path on the server."""
    return {"path": abspath(name)}


@router.post("/utils/list-dirs")
def list_dirs(path: str = Body(..., embed=True)):
    """List subdirectories under *path*. Returns parent and child dirs."""
    import os

    try:
        dirs = sorted(e.name for e in os.scandir(path) if e.is_dir() and not e.name.startswith("."))
    except (PermissionError, FileNotFoundError, NotADirectoryError):
        dirs = []
    parent = os.path.dirname(os.path.abspath(path))
    return {"current": os.path.abspath(path), "parent": parent, "dirs": dirs}
