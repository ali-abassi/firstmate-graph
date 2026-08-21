"""Work items: durable JSON records under ~/.helm/work/<id>/ with an explicit state machine.

queued → running → ready | pr-open | needs-you | done | failed
needs-you --respond--> queued      failed --retry--> queued
ready/pr-open --promote--> merged
"""
from __future__ import annotations
import json
import os
import secrets
import shutil
import time
from pathlib import Path
from . import dispatch, graphs, registry, worktree, deliver
from .paths import work_root, home
from .util import read_json, write_json, locked, now, log, HelmError

ACTIVE = ("running",)
OPEN = ("queued", "running", "needs-you", "ready", "pr-open")


def item_dir(work_id: str) -> Path: return work_root() / work_id
def item_path(work_id: str) -> Path: return item_dir(work_id) / "item.json"


def load(work_id: str) -> dict:
    it = read_json(item_path(work_id))
    if not it:
        raise HelmError(f"unknown work item '{work_id}'")
    return it


def save(it: dict) -> None:
    it["updated"] = now()
    write_json(item_path(it["id"]), it)


def transition(it: dict, status: str, note: str = "") -> None:
    it.setdefault("history", []).append({"at": now(), "from": it["status"], "to": status, "note": note})
    it["status"] = status
    save(it)
    log(f"{it['id']}: {status}" + (f" — {note}" if note else ""))


def all_items() -> list[dict]:
    out = []
    if work_root().is_dir():
        for d in sorted(work_root().iterdir()):
            it = read_json(d / "item.json")
            if it:
                out.append(it)
    return sorted(out, key=lambda i: i["created"])


def create(project_id: str, text: str, kind: str = "ship", labels: list[str] | None = None,
           max_attempts: int = 3) -> dict:
    project = registry.get(project_id)
    if kind not in ("ship", "scout"):
        raise HelmError("kind must be ship or scout")
    if kind == "ship" and project["authority"] < 1:
        raise HelmError(f"project '{project_id}' has authority 0 (observe): only scout tasks allowed")
    wid = f"{project_id}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    it = {
        "id": wid, "project": project_id, "kind": kind, "text": text.strip(),
        "labels": sorted(set(labels or [])), "status": "queued", "attempts": 0,
        "max_attempts": max_attempts, "created": now(), "updated": now(),
        "guidance": [], "failure_notes": [], "runs": [], "history": [],
        "branch": worktree.branch_name(wid), "pr_url": None, "ask": None, "dispatch": None,
    }
    it["dispatch"] = dispatch.resolve(it, project)   # fail at intake, not at run time
    write_json(item_path(wid), it)
    log(f"{wid}: queued ({kind}, rule={it['dispatch']['rule']}, graph={it['dispatch']['graph']})")
    return it


def brief_text(it: dict, project: dict) -> str:
    lines = [f"# helm {it['kind']} brief — {it['id']}", "",
             f"Project: {project['id']} ({project['path']})",
             f"Mode: {project['mode']} · authority {project['authority']} · base {project['base']}",
             f"Attempt: {it['attempts'] + 1} of {it['max_attempts']}", "", "## Task", "", it["text"], ""]
    if it["guidance"]:
        lines += ["## Captain guidance (authoritative answers to earlier questions)", ""]
        lines += [f"- {g['at']}: {g['text']}" for g in it["guidance"]] + [""]
    if it["failure_notes"]:
        lines += ["## Earlier attempts failed — do not repeat these mistakes", ""]
        for n in it["failure_notes"][-2:]:
            lines += [f"### attempt {n['attempt']}", "", "```", n["notes"], "```", ""]
    return "\n".join(lines)


def claim_next(owner: str) -> dict | None:
    """Oldest queued item whose project has no running item. Lock-protected."""
    with locked(home() / "claim.lock"):
        items = all_items()
        busy = {i["project"] for i in items if i["status"] in ACTIVE}
        for it in items:
            if it["status"] == "queued" and it["project"] not in busy:
                it["lease"] = {"owner": owner, "started": now(), "pid": os.getpid()}
                transition(it, "running", f"leased by {owner}")
                return it
    return None


def execute(it: dict, timeout: int = 3600) -> dict:
    project = registry.get(it["project"])
    d = item_dir(it["id"])
    wt = worktree.create(project, it["id"])
    brief = d / "brief.md"
    brief.write_text(brief_text(it, project))
    dp = it["dispatch"]
    steps = graphs.render(dp["graph"], d, cwd=wt, branch=it["branch"], project=project,
                          models=dp["models"], thinking=dp["thinking"], timeout=timeout)
    graphs.validate(steps)
    summary = graphs.run(steps, brief, timeout + 60)
    it["attempts"] += 1
    it["runs"].append({"attempt": it["attempts"], "at": now(), "ok": bool(summary.get("ok")),
                       "run_dir": summary.get("run_dir"), "failed_ids": summary.get("failed_ids"),
                       "tokens": summary.get("tokens"), "cost": summary.get("cost")})
    it.pop("lease", None)

    ask_file = wt / ".helm-ask.json"
    if ask_file.exists():
        try:
            it["ask"] = json.loads(ask_file.read_text())
        except json.JSONDecodeError:
            it["ask"] = {"question": ask_file.read_text()[:2000]}
        it["attempts"] -= 1                      # asking is not a failed attempt
        transition(it, "needs-you", it["ask"].get("question", "")[:120])
        return it

    if summary.get("ok"):
        if it["kind"] == "scout":
            src = Path(summary.get("run_dir") or "") / "report.md"
            if src.is_file():
                shutil.copy(src, d / "report.md")
            worktree.remove(project, it["id"], delete_branch=True)
            transition(it, "done", f"report at {d / 'report.md'}")
            return it
        if not worktree.has_commits(project, wt):
            transition(it, "failed", "graph passed but produced no commits")
            return it
        deliver.after_success(it, project, wt)
        return it

    notes = graphs.failure_notes(summary)
    it["failure_notes"].append({"attempt": it["attempts"], "notes": notes})
    worktree.remove(project, it["id"], delete_branch=True)
    if it["attempts"] < it["max_attempts"]:
        transition(it, "queued", f"attempt {it['attempts']} failed ({','.join(summary.get('failed_ids') or [])}); requeued")
    else:
        transition(it, "failed", f"exhausted {it['max_attempts']} attempts")
    return it


def respond(work_id: str, guidance: str) -> dict:
    it = load(work_id)
    if it["status"] not in ("needs-you", "failed"):
        raise HelmError(f"{work_id} is {it['status']}, not needs-you/failed")
    it["guidance"].append({"at": now(), "text": guidance.strip(), "question": (it.get("ask") or {}).get("question")})
    it["ask"] = None
    project = registry.get(it["project"])
    worktree.remove(project, it["id"], delete_branch=True)
    if it["status"] == "failed":
        it["attempts"] = 0
    transition(it, "queued", "captain responded; fresh attempt budget")
    return it


def retry(work_id: str) -> dict:
    it = load(work_id)
    if it["status"] != "failed":
        raise HelmError(f"{work_id} is {it['status']}, not failed")
    it["attempts"] = 0
    transition(it, "queued", "manual retry")
    return it


def cancel(work_id: str) -> dict:
    it = load(work_id)
    if it["status"] == "running":
        raise HelmError("cannot cancel a running item; wait for the attempt to end")
    project = registry.get(it["project"])
    wt = worktree.worktree_root() / project["id"] / it["id"]
    if wt.exists() and worktree.has_commits(project, wt) and it["status"] in ("ready", "pr-open"):
        raise HelmError(f"{work_id} has unlanded commits on {it['branch']}; use --discard to throw them away")
    worktree.remove(project, it["id"], delete_branch=True)
    transition(it, "cancelled", "")
    return it
