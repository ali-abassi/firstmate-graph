"""Guess a repo's test command and base branch so `helm add PATH` needs nothing else."""
from __future__ import annotations
import json
import re
from pathlib import Path
from .util import git


def test_command(repo: Path) -> str | None:
    pkg = repo / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text()).get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
        if "test" in scripts and "no test specified" not in scripts["test"]:
            for lock, tool in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun")):
                if (repo / lock).exists():
                    return f"{tool} test"
            return "npm test"
    if (repo / "Cargo.toml").exists():
        return "cargo test"
    if (repo / "go.mod").exists():
        return "go test ./..."
    if (repo / "pyproject.toml").exists() or (repo / "pytest.ini").exists() or (repo / "setup.cfg").exists() \
            or list(repo.glob("test_*.py")) or (repo / "tests").is_dir():
        if (repo / "uv.lock").exists():
            return "uv run pytest -q"
        if (repo / "poetry.lock").exists():
            return "poetry run pytest -q"
        if (repo / ".venv" / "bin" / "python").exists():
            return ".venv/bin/python -m pytest -q"
        return "python3 -m pytest -q"
    if (repo / "Gemfile").exists():
        return "bundle exec rspec" if (repo / "spec").is_dir() else "bundle exec rake test"
    if (repo / "mix.exs").exists():
        return "mix test"
    mk = repo / "Makefile"
    if mk.exists() and re.search(r"^test:", mk.read_text(), re.M):
        return "make test"
    return None


def base_branch(repo: Path) -> str:
    for ref in ("refs/remotes/origin/HEAD",):
        out = git(repo, "symbolic-ref", "--short", ref, check=False)
        if out:
            return out.split("/", 1)[-1]
    head = git(repo, "symbolic-ref", "--short", "HEAD", check=False)
    if head:
        return head
    for cand in ("main", "master"):
        if git(repo, "rev-parse", "--verify", "--quiet", cand, check=False):
            return cand
    return "main"
