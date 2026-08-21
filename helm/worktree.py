"""One disposable git worktree per attempt. Never touches the captain's checkout branch."""
from __future__ import annotations
import os
import shutil
import subprocess
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
    link_deps(repo, wt)
    return wt


def git_env(wt: Path, exclude_file: Path, base_env: dict | None = None) -> dict:
    """Environment for everything that runs git inside the worktree.

    Linked dependency trees are symlinks, and a `.gitignore` line like `node_modules/`
    matches directories only, so `git add -A` would commit the links. Rather than write
    into the project's `.git/info/exclude`, hand git an extra excludes file through the
    documented GIT_CONFIG_* environment for this run only.
    """
    env = dict(base_env if base_env is not None else os.environ)
    names = [n for n in DEP_DIRS if (wt / n).is_symlink()]
    exclude_file.write_text("".join(f"/{n}\n" for n in names) + "/.helm-ask.json\n")
    count = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    env[f"GIT_CONFIG_KEY_{count}"] = "core.excludesFile"
    env[f"GIT_CONFIG_VALUE_{count}"] = str(exclude_file)
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


DEP_DIRS = ("node_modules", ".venv", "venv", "vendor", ".tox", "target")


def link_deps(repo: Path, wt: Path) -> list[str]:
    """Symlink git-ignored dependency trees from the checkout into the worktree.

    A fresh worktree has only tracked files, so `.venv/bin/python -m pytest` or `npm test`
    would fail for want of installed packages. Linking keeps verification offline and fast.
    Only directories with no tracked files are linked (a venv ignores itself from inside, so
    `git check-ignore` is not a reliable test); `git_env` keeps the links out of commits.
    """
    linked = []
    for name in DEP_DIRS:
        src, dst = repo / name, wt / name
        if not src.is_dir() or dst.exists():
            continue
        tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--", name], capture_output=True, text=True).stdout
        if tracked.strip():          # tracked content comes from git, never from a link
            continue
        dst.symlink_to(src, target_is_directory=True)
        linked.append(name)
    return linked


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
