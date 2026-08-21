"""One disposable git worktree per attempt. Never touches the captain's checkout branch."""
from __future__ import annotations
import shutil
from pathlib import Path
from .paths import worktree_root
from .util import git, HelmError


def branch_name(work_id: str) -> str:
    return f"helm/{work_id}"


def create(project: dict, work_id: str) -> Path:
    repo = Path(project["path"])
    wt = worktree_root() / project["id"] / work_id
    if wt.exists():
        remove(project, work_id)
    wt.parent.mkdir(parents=True, exist_ok=True)
    base = project["base"]
    if git(repo, "rev-parse", "--verify", "--quiet", base, check=False) == "":
        raise HelmError(f"base ref '{base}' not found in {repo}")
    br = branch_name(work_id)
    git(repo, "branch", "-f", br, base)
    git(repo, "worktree", "add", "--quiet", str(wt), br)
    return wt


def remove(project: dict, work_id: str, delete_branch: bool = False) -> None:
    repo = Path(project["path"])
    wt = worktree_root() / project["id"] / work_id
    git(repo, "worktree", "remove", "--force", str(wt), check=False)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    git(repo, "worktree", "prune", check=False)
    if delete_branch:
        git(repo, "branch", "-D", branch_name(work_id), check=False)


def has_commits(project: dict, wt: Path) -> bool:
    return git(wt, "rev-list", "--count", f"{project['base']}..HEAD") not in ("", "0")


def is_clean(wt: Path) -> bool:
    return git(wt, "status", "--porcelain", "--untracked-files=no") == ""


def changed_files(project: dict, wt: Path) -> list[str]:
    out = git(wt, "diff", "--name-only", f"{project['base']}...HEAD")
    return [l for l in out.splitlines() if l]
