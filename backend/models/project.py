"""Project model -- holds all data for one Unipage project."""

from __future__ import annotations

from json import dumps
from os import makedirs
from os.path import basename, exists, join, splitext
from re import sub as _sub
from typing import Optional

from backend.models.dataclasses import BlockInfo, BlockSetting, ProjectInfo, ResourceCollection, ResourceEntry


def sanitize_filename(name: str) -> str:
    """Remove characters invalid in filenames on Windows."""
    return _sub(r'[\\/:*?"<>|]', "", name)


# -- Resource record helpers -----------------------------------------

_RESOURCE_EXT_MAP = {
    ".json": "project",
    ".tsv": "data",
    ".ttf": "font",
    ".otf": "font",
}

VALID_IMPORT_EXTS = {".tsv", ".ttf", ".otf"}


def _ext_to_rsc_key(ext: str) -> Optional[str]:
    return _RESOURCE_EXT_MAP.get(ext)


def _resource_paths(resources: dict) -> list[str]:
    """Return all resource URLs from a resources dict as a flat list."""
    if isinstance(resources, ResourceCollection):
        return [r.url for r in resources.all()]
    return [r[2] for r in (resources.get("project", []) + resources.get("font", []) + resources.get("data", []))]


# ==================================================================
# Project class
# ==================================================================


class Project:
    """Represents a Unipage project with its resources, settings, and blocks.

    Schema
    ------
    project_info : ProjectInfo
        Project identification data.
    resources : ResourceCollection
        ``{"project": [...], "font": [...], "data": [...]}``
        Each entry: ``ResourceEntry``
    blocks : list[BlockInfo]
        Parsed block definitions.
    settings : list[BlockSetting]
        Per-block print settings.
    """

    def __init__(self, basic_info: Optional[dict | ProjectInfo] = None) -> None:
        if isinstance(basic_info, ProjectInfo):
            self.project_info: ProjectInfo = basic_info
        else:
            self.project_info: ProjectInfo = ProjectInfo.from_dict(basic_info or {})
        self.resources: ResourceCollection = ResourceCollection()
        self.blocks: list[BlockInfo] = []
        self.settings: list[BlockSetting] = []

    # -- Persistence ----------------------------------------------

    def to_dict(self) -> dict:
        return {
            "basic_info": self.project_info.to_dict(),
            "resources": self.resources.to_dict(),
            "blocks": [b.to_dict() for b in self.blocks],
            "settings": [s.to_dict() for s in self.settings],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        """Create from a dict, supporting both old and new key names."""
        proj = cls(basic_info=data.get("basic_info", {}))
        # Support old key names: rsc_info, blk_info, set_info
        proj.resources = ResourceCollection.from_dict(data.get("resources") or data.get("rsc_info", {}))
        proj.blocks = [BlockInfo.from_dict(b) for b in data.get("blocks") or data.get("blk_info", [])]
        proj.settings = [BlockSetting.from_dict(s) for s in data.get("settings") or data.get("set_info", [])]
        return proj

    def save(self) -> None:
        """Write project data to the .json project file."""

        path = self.project_info.project_file
        if not path:
            raise ValueError("project_file not set in project_info")
        # Ensure directory exists
        parent = join(path, "..") if "/" in path else None
        if parent and not exists(parent):
            makedirs(parent, exist_ok=True)
        raw = dumps(self.to_dict(), ensure_ascii=False, indent=2, separators=(",", ":"))
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(raw)

    @classmethod
    def load(cls, path: str) -> tuple[Project, list]:
        """Load a project from a .json project file.

        Returns (project, bugs) where bugs is a list of BugEntry.
        """
        from backend.file_management.parser import parse_project_file

        data, bugs = parse_project_file(path)
        if any(b.severity == 0 for b in bugs):
            return cls(), bugs
        return cls.from_dict(data), bugs

    # -- Resource management helpers ------------------------------

    def all_resource_paths(self) -> list[str]:
        return _resource_paths(self.resources)

    def add_resource(
        self,
        src_path: Optional[str],
        dest_path: str,
        check_status: int,
        parse_data: Optional[list] = None,
    ) -> str:
        """Register a resource. Returns the resource key ('project','font','data')."""
        from os import remove as os_remove
        from shutil import copyfile

        ext = splitext(dest_path)[1].lower()
        rsc_key = _ext_to_rsc_key(ext)
        if rsc_key is None:
            raise ValueError(f"Unsupported extension: {ext}")

        if dest_path in self.all_resource_paths():
            raise FileExistsError(f"Resource already exists: {dest_path}")

        if src_path and src_path != dest_path:
            if exists(dest_path):
                os_remove(dest_path)
            copyfile(src_path, dest_path)

        entry = ResourceEntry(basename(dest_path), check_status, dest_path, parse_data)
        getattr(self.resources, rsc_key).append(entry)
        return rsc_key

    _ALL_RSC_KEYS = ("project", "font", "data")

    def remove_resource_by_path(self, path: str) -> bool:
        """Remove a resource by its URL. Returns True if found."""
        for rsc_key in self._ALL_RSC_KEYS:
            rsc_list = getattr(self.resources, rsc_key, [])
            for rsc in list(rsc_list):
                if rsc.url == path:
                    rsc_list.remove(rsc)
                    return True
        return False

    def find_resource(self, path: str) -> Optional[ResourceEntry]:
        """Find a resource entry by URL."""
        for rsc_key in self._ALL_RSC_KEYS:
            for rsc in getattr(self.resources, rsc_key, []):
                if rsc.url == path:
                    return rsc
        return None

    def find_resources_by_type(self, rsc_key: str) -> list:
        """Return all resources of a given type key."""
        return list(getattr(self.resources, rsc_key, []))

    # -- Block / Setting lookup -----------------------------------

    def get_block(self, name: str) -> Optional[BlockInfo]:
        for blk in self.blocks:
            if blk.name == name:
                return blk
        return None

    def get_setting(self, name: str) -> Optional[BlockSetting]:
        for s in self.settings:
            if s.name == name:
                return s
        return None
