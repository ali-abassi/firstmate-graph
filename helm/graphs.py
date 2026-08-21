"""Render a graph template for one attempt and drive `piw` (the only runner)."""
from __future__ import annotations
import json
import os
import shlex
import subprocess
from pathlib import Path
from string import Template


class _T(Template):
    delimiter = "@"  # shell $VARS and $(...) pass through untouched

from .paths import GRAPHS, REPO
from .util import HelmError, log


def piw_bin() -> str:
    return os.environ.get("HELM_PIW", "piw")


def render(graph: str, dest_dir: Path, *, cwd: Path, branch: str, project: dict,
           models: dict, thinking: dict, timeout: int) -> Path:
    src = GRAPHS / f"{graph}.yaml"
    if not src.exists():
        raise HelmError(f"graph template not found: {src}")
    protected = project.get("protected_paths") or []
    vars_ = {
        "CWD": str(cwd), "BRANCH": branch, "BASE": project["base"],
        "TEST_CMD": project.get("test_cmd") or "true",
        "PROTECTED": ", ".join(protected) or "(none)",
        "PROTECTED_ARGS": " ".join(shlex.quote(p) for p in protected),
        "HELM_REPO": str(REPO), "TIMEOUT": str(timeout),
    }
    for phase, model in models.items():
        vars_[f"MODEL_{phase.upper()}"] = model
    for phase, level in thinking.items():
        vars_[f"THINKING_{phase.upper()}"] = level
    text = _T(src.read_text()).substitute(vars_)
    dest_dir.mkdir(parents=True, exist_ok=True)
    steps = dest_dir / "steps.yaml"
    steps.write_text(text)
    return steps


def validate(steps: Path) -> None:
    r = subprocess.run([piw_bin(), "validate", str(steps)], text=True, capture_output=True)
    if r.returncode != 0:
        raise HelmError(f"piw validate failed:\n{r.stdout}{r.stderr}")


def run(steps: Path, brief: Path, timeout: int) -> dict:
    cmd = [piw_bin(), "run", str(steps), "--input-file", str(brief), "--json",
           "--no-cache", "--timeout", str(timeout)]
    log(f"exec {' '.join(shlex.quote(c) for c in cmd)}")
    r = subprocess.run(cmd, text=True, capture_output=True, cwd=str(steps.parent))
    summary = None
    for line in reversed(r.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                summary = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if summary is None:
        summary = {"ok": False, "failed_ids": ["<piw>"], "run_dir": "",
                   "error": (r.stderr or r.stdout)[-4000:] or f"piw exit {r.returncode}"}
    summary["exit_code"] = r.returncode
    return summary


def failure_notes(summary: dict, limit: int = 3000) -> str:
    """Tail of evidence for each failed node, fed into the next attempt's brief."""
    parts = []
    if summary.get("error"):
        parts.append(f"runner error: {summary['error'][-limit:]}")
    run_dir = Path(summary.get("run_dir") or "")
    for sid in summary.get("failed_ids") or []:
        if sid.startswith("<"):
            continue
        chunk = []
        if run_dir.is_dir():
            for f in sorted(run_dir.glob(f"{sid}*")):
                if f.is_file():
                    try:
                        chunk.append(f"--- {f.name} ---\n{f.read_text()[-limit:]}")
                    except OSError:
                        pass
        parts.append(f"failed node `{sid}`:\n" + ("\n".join(chunk) or "(no evidence files)"))
    return "\n\n".join(parts)
