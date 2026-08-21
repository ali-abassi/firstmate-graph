"""The fleet board: what the captain sees at a glance (banner, `helm watch`)."""
from __future__ import annotations
import os
import shutil
import time
from . import registry, work
from .paths import home

BANNER = "\n  ⚓  F I R S T   M A T E   ·  graph\n  ─────────────────────────────────\n"

STATUS_ICON = {"queued": "·", "running": "▶", "needs-you": "?", "ready": "✓", "pr-open": "⇡",
               "failed": "✗", "merged": "⇣", "done": "✓", "cancelled": "–"}


def render(workers_pid: int | None, width: int | None = None) -> str:
    width = width or shutil.get_terminal_size((100, 30)).columns
    projects = registry.load()["projects"]
    items = work.all_items()
    open_items = [i for i in items if i["status"] in work.OPEN]
    lines = []
    where = "herdr tabs" if os.environ.get("HERDR_ENV") == "1" else f"background (pid {workers_pid})" if workers_pid else "stopped — helm up"
    lines.append(f"  workers   {where}")
    lines.append(f"  projects  {len(projects)}" + ("   " + " · ".join(f"{p['id']} [{p['mode']}/a{p['authority']}]" for p in list(projects.values())[:6]) if projects else "   → helm add PATH"))
    needs = [i for i in items if i["status"] in ("needs-you", "failed", "ready", "pr-open")]
    lines.append(f"  inbox     {len(needs)} need you" if needs else "  inbox     clear")
    if open_items:
        lines.append("")
        for i in open_items[-12:]:
            icon = STATUS_ICON.get(i["status"], " ")
            text = i["text"].splitlines()[0]
            extra = (i.get("ask") or {}).get("question") or i.get("pr_url") or ""
            row = f"  {icon} {i['status']:<9} {i['project']:<12} {text}"
            if extra:
                row += f"  — {extra}"
            lines.append(row[: width - 1])
    return "\n".join(lines)


def banner(workers_pid: int | None) -> str:
    return BANNER + render(workers_pid) + "\n\n  home " + str(home()) + "\n"


def watch(interval: float, once: bool = False) -> None:
    from .cli import daemon_pid
    while True:
        out = BANNER + render(daemon_pid()) + f"\n\n  {time.strftime('%H:%M:%S')} · refreshing every {interval:g}s · ctrl-c to stop\n"
        if not once:
            print("\033[2J\033[H", end="")
        print(out)
        if once:
            return
        time.sleep(interval)
