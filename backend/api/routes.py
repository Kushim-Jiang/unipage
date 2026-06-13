"""FastAPI routes for the Unipage backend."""

from __future__ import annotations

import os
import threading
from os.path import basename, exists, splitext
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.chart_generation.layout import make_proof
from backend.chart_generation.pdf_builder import generate_pdf
from backend.file_management.parser import parse_project_file, parse_block_file, parse_attribute_file, detect_tsv_type
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

# ══════════════════════════════════════════════════════════════════
# Pydantic schemas
# ══════════════════════════════════════════════════════════════════


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


class ColourToggleRequest(BaseModel):
    name: str
    codepoint: int
    colour: str  # "yellow" or "blue"


class BugReport(BaseModel):
    errors: list
    warnings: list
    infos: list
    counts: dict


# ══════════════════════════════════════════════════════════════════
# Router
# ══════════════════════════════════════════════════════════════════

router = APIRouter(prefix="/api")


# ── Project CRUD ────────────────────────────────────────────────────


@router.post("/project/create")
def create_project(info: ProjectInfo):
    """Create a new project."""
    if STATE.has_project:
        raise HTTPException(400, "A project is already open. Close it first.")

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
        raise HTTPException(400, "A project is already open. Close it first.")
    if not exists(path):
        raise HTTPException(404, f"File not found: {path}")
    return _do_open(path)


@router.post("/project/load")
def load_project(data: dict):
    """Open a project from raw JSON content (no filesystem path needed)."""
    if STATE.has_project:
        raise HTTPException(400, "A project is already open. Close it first.")
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
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
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


# ── Resources ───────────────────────────────────────────────────────


@router.get("/resources")
def list_resources():
    """List all resources in the current project."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    return STATE.project.resources.to_dict()


@router.post("/resources/import")
def import_file(path: str):
    """Import a resource file (copy into project dir)."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    proj = STATE.project
    dest = f"{proj.project_info.project_dir}/{basename(path)}"
    try:
        import_resource(proj, path, dest, 0)
        return {"status": "ok", "dest": dest}
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/resources/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a resource file via multipart."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    proj = STATE.project
    dest = f"{proj.project_info.project_dir}/{file.filename}"
    content = await file.read()
    with open(dest, "wb") as fp:
        fp.write(content)
    try:
        import_resource(proj, None, dest, 0)
        return {"status": "ok", "dest": dest}
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/resources")
def delete_resource(path: str):
    """Remove a resource from the project."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    if remove_resource(STATE.project, path):
        return {"status": "ok"}
    raise HTTPException(404, f"Resource not found: {path}")


@router.post("/resources/parse")
def parse_resources():
    """Parse all compiled-but-unparsed block and attribute resources (background thread with progress)."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")

    proj = STATE.project
    targets = [
        rsc
        for rsc in (
            proj.find_resources_by_type("block")
            + proj.find_resources_by_type("attribute")
            + proj.find_resources_by_type("font")
        )
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

    STATE.parse_progress = 0.0
    STATE.parse_done = False
    STATE.parse_bugs = None
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


@router.get("/resources/parse-progress")
def parse_progress():
    """Poll current parse progress."""
    return {
        "progress": int(getattr(STATE, "parse_progress", 0)),
        "done": getattr(STATE, "parse_done", False),
        "bugs": getattr(STATE, "parse_bugs", None),
    }


@router.get("/resources/parse-one")
def parse_one_resource(path: str):
    """Parse a single resource file and return its content + bugs."""
    ext = splitext(path)[1].lower()
    if ext == ".json":
        parsed, bugs = parse_project_file(path)
    elif ext == ".tsv":
        tsv_type = detect_tsv_type(path)
        if tsv_type == "block":
            parsed, bugs = parse_block_file(path)
        elif tsv_type == "attribute":
            parsed, bugs = parse_attribute_file(path)
        else:
            raise HTTPException(400, f"Cannot determine type of TSV file: {path}")
    else:
        raise HTTPException(400, f"Cannot parse: {path}")
    return {"parsed": parsed, "bugs": bug_summary(bugs)}


# ── Blocks ──────────────────────────────────────────────────────────


@router.get("/blocks")
def list_blocks():
    """Return all parsed block information."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    return [b.to_dict() for b in STATE.project.blocks]


@router.get("/blocks/{name}")
def get_block(name: str):
    """Return a single block by name."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    blk = STATE.project.get_block(name)
    if blk is None:
        raise HTTPException(404, f"Block not found: {name}")
    return blk.to_dict()


# ── Settings ────────────────────────────────────────────────────────


@router.get("/settings")
def list_settings():
    """Return all block print settings."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    return [s.to_dict() for s in STATE.project.settings]


@router.post("/settings/cycle")
def cycle_option(req: CycleOptionRequest):
    """Cycle a setting option (prev/next)."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    _SETTING_KEYS = ["print", "column", "format", "title"]
    _SETTING_RANGES = [2, 4, 3, 2]
    _FONT_KEYS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

    delta = 1 if req.forward else -1
    cont = setting.content
    bt = setting.type

    if req.field in _SETTING_KEYS:
        idx = _SETTING_KEYS.index(req.field)
        cont[req.field] = (cont[req.field] + delta) % _SETTING_RANGES[idx]
    elif req.field == "font":
        n_fonts = len(proj.resources.font) + 1
        if bt in ("V", "C"):
            cont["font"][0] = (cont["font"][0] + delta) % n_fonts
        else:
            for i in range(12):
                cont["font"][i][0] = (cont["font"][i][0] + delta) % n_fonts

    return {"status": "ok", "setting": setting.to_dict()}


@router.post("/settings/colour-toggle")
def toggle_colour(req: ColourToggleRequest):
    """Toggle yellow/blue marking on a codepoint."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")
    proj = STATE.project
    setting = proj.get_setting(req.name)
    if setting is None:
        raise HTTPException(404, f"Setting not found: {req.name}")

    cont = setting.content
    if req.codepoint in cont.get(req.colour, []):
        cont[req.colour].remove(req.codepoint)
    else:
        cont[req.colour].append(req.codepoint)

    return {"status": "ok", "setting": setting.to_dict()}


# ── Proof / PDF ─────────────────────────────────────────────────────


@router.post("/proof/check")
def check_proof(name: str):
    """Check a block and generate a proof. Returns bugs and proof status."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")

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
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")

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
    """Check all printable blocks (background thread with progress)."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")

    proj = STATE.project
    targets = [s for s in proj.settings if s.content.get("print") == 1]
    total = len(targets)
    STATE.check_progress = 0.0
    STATE.check_done = False
    STATE.check_bugs = None
    STATE.proofs = []

    def run():
        all_bugs = []
        passing = []
        for i, setting in enumerate(targets):
            proof, bugs = make_proof(setting.name)
            all_bugs.extend(bugs)
            if not any(b.severity == 0 for b in bugs) and proof is not None:
                passing.append(proof)
            STATE.check_progress = (i + 1) / total * 100
        STATE.proofs = passing
        STATE.check_bugs = bug_summary(all_bugs)
        STATE.check_progress = 100.0
        STATE.check_done = True

    STATE.check_progress = 0.0
    STATE.check_done = False
    STATE.check_bugs = None
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


@router.get("/proof/check-progress")
def check_progress():
    """Poll current check-all progress."""
    return {
        "progress": int(getattr(STATE, "check_progress", 0)),
        "done": getattr(STATE, "check_done", False),
        "bugs": getattr(STATE, "check_bugs", None),
        "passing_count": len(getattr(STATE, "proofs", [])),
    }


@router.post("/proof/generate-all")
def generate_all_pdf():
    """Generate PDF for all cached proofs (stores progress in STATE for polling)."""
    if not STATE.has_project:
        raise HTTPException(400, "No project open.")

    proj = STATE.project
    pdf_dir = f"{proj.project_info.project_dir}/pdf/"
    proofs = list(STATE.proofs)
    total = len(proofs)
    STATE.pdf_progress = 0.0

    def run():
        results = []
        for i, proof in enumerate(proofs):

            def cb(p: float):
                STATE.pdf_progress = (i + p) / total * 100

            pdf_path = generate_pdf(proof, pdf_dir, progress_callback=cb)
            results.append({"block": proof.name, "pdf_path": pdf_path})
            STATE.pdf_progress = (i + 1) / total * 100
        STATE.pdf_results = results
        STATE.pdf_progress = 100.0

    STATE.pdf_results = None
    STATE.pdf_progress = 0.0
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"status": "started", "total": total}


@router.get("/proof/generate-progress")
def generate_progress():
    """Poll current PDF generation progress."""
    return {
        "progress": int(getattr(STATE, "pdf_progress", 0)),
        "done": getattr(STATE, "pdf_results", None) is not None,
        "results": getattr(STATE, "pdf_results", []),
    }
