from __future__ import annotations
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GRAPHS = REPO / "graphs"


def home() -> Path:
    return Path(os.environ.get("HELM_HOME", "~/.helm")).expanduser().resolve()


def projects_file() -> Path: return home() / "projects.json"
def dispatch_file() -> Path: return home() / "dispatch.json"
def work_root() -> Path: return home() / "work"
def worktree_root() -> Path: return home() / "worktrees"
def log_file() -> Path: return home() / "helm.log"
