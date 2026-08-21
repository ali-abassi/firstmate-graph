"""Herdr adapter: when the captain runs inside Herdr, the fleet becomes visible as tabs.

- `helm up` opens a fleet board tab and one tab per worker in the captain's workspace.
- Each running task gets its own tab that follows the run log, closed when the task ends.
- Inbox events surface as Herdr notifications.

Everything here is best-effort presentation: a Herdr failure never fails a task.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path
from .paths import home, REPO
from .util import read_json, write_json, log


def inside() -> bool:
    return os.environ.get("HERDR_ENV") == "1" and bool(os.environ.get("HERDR_WORKSPACE_ID")) and bool(shutil.which("herdr"))


def _cli(*args: str) -> dict | None:
    cmd = ["herdr", *args]
    session = os.environ.get("HERDR_SESSION")
    if session:
        cmd += ["--session", session]
    try:
        r = subprocess.run(cmd, text=True, capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"herdr: {' '.join(args[:2])} failed: {e!r}")
        return None
    if r.returncode != 0:
        log(f"herdr: {' '.join(args[:2])} exit {r.returncode}: {r.stderr.strip()[:200]}")
        return None
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        return {}


PASS_ENV = ("HELM_HOME", "HELM_PIW")


def open_tab(label: str, command: str, cwd: Path | None = None) -> dict | None:
    """Create a tab beside the captain and run `command` in it. Returns {tab_id, pane_id}."""
    env_args = []
    for k in PASS_ENV:
        v = os.environ.get(k) or (str(home()) if k == "HELM_HOME" else None)
        if v:
            env_args += ["--env", f"{k}={v}"]
    out = _cli("tab", "create", "--workspace", os.environ["HERDR_WORKSPACE_ID"],
               "--cwd", str(cwd or REPO), "--label", label, "--no-focus", *env_args)
    if not out:
        return None
    tab = (out.get("result") or {}).get("tab", {}).get("tab_id")
    pane = (out.get("result") or {}).get("root_pane", {}).get("pane_id")
    if not (tab and pane):
        return None
    _cli("pane", "run", pane, command)
    log(f"herdr: opened tab {tab} '{label}'")
    return {"tab_id": tab, "pane_id": pane, "label": label}


def close_tab(tab_id: str) -> None:
    _cli("tab", "close", tab_id)
    log(f"herdr: closed tab {tab_id}")


def notify(title: str, body: str = "") -> None:
    if shutil.which("herdr") and os.environ.get("HERDR_ENV") == "1":
        _cli("notification", "show", title, *(["--body", body] if body else []))


# ------------------------------------------------------------------ durable tab registry

def _state_path() -> Path: return home() / "herdr.json"


def remember(kind: str, rec: dict) -> None:
    st = read_json(_state_path(), {"tabs": []})
    st["tabs"].append({"kind": kind, **rec})
    write_json(_state_path(), st)


def forget(tab_id: str) -> None:
    st = read_json(_state_path(), {"tabs": []})
    st["tabs"] = [t for t in st["tabs"] if t.get("tab_id") != tab_id]
    write_json(_state_path(), st)


def close_all(kind: str | None = None) -> int:
    st = read_json(_state_path(), {"tabs": []})
    keep, n = [], 0
    for t in st["tabs"]:
        if kind and t.get("kind") != kind:
            keep.append(t); continue
        close_tab(t["tab_id"]); n += 1
    st["tabs"] = keep
    write_json(_state_path(), st)
    return n
