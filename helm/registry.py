"""Project registry: ~/.helm/projects.json. Mode + authority are the captain's standing posture."""
from __future__ import annotations
import re
from pathlib import Path
from .paths import projects_file
from .util import read_json, write_json, git, HelmError

MODES = ("no-mistakes", "direct-pr", "local-only")
# Authority: what helm may do on its own for this project. Only a human raises it.
AUTHORITY = {
    0: "observe      — scout tasks only",
    1: "build        — ship tasks build+verify in a worktree; nothing leaves the machine",
    2: "open-pr      — may push a branch and open a PR",
    3: "merge        — `helm promote --confirm` may merge/fast-forward",
}
MIN_AUTHORITY = {"scout": 0, "build": 1, "open-pr": 2, "merge": 3}


def load() -> dict:
    return read_json(projects_file(), {"projects": {}})


def save(data: dict) -> None:
    write_json(projects_file(), data)


def get(project_id: str) -> dict:
    p = load()["projects"].get(project_id)
    if not p:
        raise HelmError(f"unknown project '{project_id}' (see `helm projects`)")
    return p


def add(path: str, project_id: str | None, mode: str, authority: int, test_cmd: str | None,
        protected: list[str], base: str | None) -> dict:
    repo = Path(path).expanduser().resolve()
    if not (repo / ".git").exists():
        raise HelmError(f"{repo} is not a git repository")
    if mode not in MODES:
        raise HelmError(f"mode must be one of {MODES}")
    if authority not in AUTHORITY:
        raise HelmError(f"authority must be 0-3")
    pid = project_id or re.sub(r"[^a-z0-9-]+", "-", repo.name.lower()).strip("-")
    if not base:
        head = git(repo, "symbolic-ref", "--short", "HEAD", check=False) or "main"
        base = head
    entry = {
        "id": pid, "path": str(repo), "mode": mode, "authority": authority,
        "base": base, "test_cmd": test_cmd or "",
        "protected_paths": protected or [".github/workflows/*", ".helm/*", "helm.json"],
    }
    data = load()
    data["projects"][pid] = entry
    save(data)
    return entry


def set_fields(project_id: str, **fields) -> dict:
    data = load()
    p = data["projects"].get(project_id) or {}
    if not p:
        raise HelmError(f"unknown project '{project_id}'")
    for k, v in fields.items():
        if v is None:
            continue
        if k == "mode" and v not in MODES:
            raise HelmError(f"mode must be one of {MODES}")
        if k == "authority" and v not in AUTHORITY:
            raise HelmError("authority must be 0-3")
        p[k] = v
    save(data)
    return p
