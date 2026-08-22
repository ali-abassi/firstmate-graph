from __future__ import annotations
import argparse
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from . import registry, dispatch, work, deliver, worktree, herdr, board, __version__
from .paths import home, projects_file, dispatch_file, GRAPHS
from .util import HelmError, log


def out(obj, as_json: bool, text: str | None = None):
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    elif text is not None:
        print(text)


def cmd_add(a):
    p = registry.add(a.path, a.id, a.mode, a.authority, a.test, a.protected.split(",") if a.protected else [], a.base)
    out(p, a.json, f"registered {p['id']}  mode {p['mode']} · authority {p['authority']} · base {p['base']}\n"
                   f"  test: {p['test_cmd'] or '(none found)'}")
    if not p["test_cmd"]:
        print(f"  no test command detected — changes will not be verified. Set one: helm set {p['id']} --test \"…\"", file=sys.stderr)
    elif a.test is None:
        print(f"  (detected; override with: helm set {p['id']} --test \"…\")", file=sys.stderr)


# ---------------------------------------------------------------- daemon lifecycle

def _pid_file(): return home() / "daemon.pid"

def daemon_pid():
    try:
        pid = int(_pid_file().read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


HELM_BIN = str(Path(__file__).resolve().parents[1] / "bin" / "helm")


def cmd_up(a):
    home().mkdir(parents=True, exist_ok=True)
    if herdr.inside():
        return _up_herdr(a)
    if daemon_pid():
        out({"pid": daemon_pid()}, a.json, f"workers already running (pid {daemon_pid()})")
        return
    logf = open(home() / "daemon.log", "ab")
    p = subprocess.Popen([sys.executable, HELM_BIN, "daemon", "--owner", f"worker-{os.getpid()}", "--interval", str(a.interval)],
                         stdin=subprocess.DEVNULL, stdout=logf, stderr=logf, start_new_session=True, env=os.environ)
    _pid_file().write_text(str(p.pid))
    out({"pid": p.pid}, a.json, f"workers running (pid {p.pid}) · log {home() / 'daemon.log'}")


def _up_herdr(a):
    """Inside Herdr: a fleet board tab plus one tab per worker, beside the captain."""
    from .util import read_json
    existing = read_json(home() / "herdr.json", {"tabs": []})["tabs"]
    if any(t["kind"] == "worker" for t in existing):
        out({"tabs": existing}, a.json, f"workers already open in herdr ({sum(t['kind']=='worker' for t in existing)} tabs)")
        return
    opened = []
    t = herdr.open_tab("⚓ fleet", f"{shlex.quote(HELM_BIN)} watch")
    if t:
        herdr.remember("board", t); opened.append(t)
    for n in range(1, a.workers + 1):
        t = herdr.open_tab(f"worker {n}", f"{shlex.quote(HELM_BIN)} daemon --owner worker-{n} --interval {min(a.interval, 5)}")
        if t:
            herdr.remember("worker", t); opened.append(t)
    if not opened:
        raise HelmError("could not open herdr tabs (see ~/.helm/helm.log)")
    out({"tabs": opened}, a.json, f"opened {len(opened)} herdr tabs: " + ", ".join(t["label"] for t in opened))


def cmd_down(a):
    closed = herdr.close_all() if (home() / "herdr.json").exists() else 0
    pid = daemon_pid()
    if not pid:
        out({"stopped": False, "tabs_closed": closed}, a.json, f"closed {closed} herdr tabs" if closed else "workers not running")
        return
    os.killpg(os.getpgid(pid), signal.SIGTERM)
    _pid_file().unlink(missing_ok=True)
    out({"stopped": True, "pid": pid}, a.json, f"stopped workers (pid {pid}); a running attempt will be reclaimed next start")


def cmd_status(a):
    items = work.all_items()
    counts = {}
    for i in items:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    pid = daemon_pid()
    from .util import read_json
    tabs = read_json(home() / "herdr.json", {"tabs": []})["tabs"]
    data = {"workers": pid, "herdr_tabs": tabs, "projects": len(registry.load()["projects"]), "items": counts}
    if a.json:
        return out(data, True)
    print(board.render(pid))


HARNESS = {
    "pi": ["pi", "--approve"],
    "claude": ["claude", "--dangerously-skip-permissions"],
    "codex": ["codex", "--full-auto"],
}


# A default, not a cage: every model the login provides stays selectable (/model), and the
# crew's per-step models live in dispatch.json, which the captain can change by asking.
PI_HOME_SETTINGS = {"defaultProvider": "openai-codex", "defaultModel": "gpt-5.6-sol",
                    "defaultThinkingLevel": "medium", "quietStartup": True}


def pi_home() -> Path:
    """The first mate's own Pi config dir. Nothing from the captain's Pi is inherited."""
    return home() / "pi"


def _isolated_pi_home() -> Path:
    dst = pi_home()
    dst.mkdir(parents=True, exist_ok=True)
    settings = dst / "settings.json"
    current = json.loads(settings.read_text()) if settings.exists() else {}
    if "defaultModel" not in current:                      # seed once; the captain's later choices stick
        current.update(PI_HOME_SETTINGS)
        settings.write_text(json.dumps(current, indent=2) + "\n")
    (dst / "README").write_text("first mate's private Pi home — managed by helm. Log in here with `helm setup`.\n")
    return dst


def codex_ready() -> bool:
    if not shutil.which("pi"):
        return False
    r = subprocess.run(["pi", "auth", "check", "--provider", "openai-codex"], text=True, capture_output=True,
                       env={**os.environ, "PI_CODING_AGENT_DIR": str(_isolated_pi_home())}, stdin=subprocess.DEVNULL)
    return r.stdout.strip() == "ready"


def cmd_setup(a):
    """Own config, own login: connect the first mate to the Codex subscription."""
    dst = _isolated_pi_home()
    dispatch.load()
    if not codex_ready() and not getattr(a, "fresh", False):
        # The captain has very likely logged Pi into Codex already: reuse that, don't ask twice.
        src = Path(os.environ.get("HELM_IMPORT_PI_DIR", "~/.pi/agent")).expanduser() / "auth.json"
        try:
            creds = json.loads(src.read_text()).get("openai-codex")
        except (OSError, json.JSONDecodeError):
            creds = None
        if creds:
            auth = dst / "auth.json"
            current = json.loads(auth.read_text()) if auth.exists() else {}
            current["openai-codex"] = creds
            auth.write_text(json.dumps(current, indent=2) + "\n"); auth.chmod(0o600)
            print(f"  ⚓ reusing your Codex login from {src.parent}", file=sys.stderr)
        elif a.import_login:
            raise HelmError(f"no openai-codex login found in {src}")
    if codex_ready():
        out({"ready": True, "pi_home": str(dst)}, a.json, f"✓ connected to the Codex subscription · pi home {dst}")
        return
    if a.json or not sys.stdin.isatty():
        raise HelmError("not connected to Codex yet — run `pi-firstmate setup` in a terminal")
    print("\n  ⚓ one-time setup — connect the first mate to your Codex subscription\n"
          "     Pi will open. Type  /login  and choose  OpenAI Codex , finish in the browser, then  /exit\n", file=sys.stderr)
    subprocess.run(["pi"], env={**os.environ, "PI_CODING_AGENT_DIR": str(dst)}, cwd=str(dst))
    if codex_ready():
        out({"ready": True, "pi_home": str(dst)}, False, f"✓ connected to the Codex subscription · pi home {dst}")
    else:
        raise HelmError("still not connected to Codex — run `pi-firstmate setup` again")


def cmd_captain(a):
    """One command: workers up, banner, then the liaison in front of you."""
    cmd = HARNESS.get(a.harness) or [a.harness]
    if not shutil.which(cmd[0]):
        raise HelmError(f"{cmd[0]} is not on PATH")
    from .util import read_json
    have_tabs = any(t["kind"] == "worker" for t in read_json(home() / "herdr.json", {"tabs": []})["tabs"])
    if not daemon_pid() and not (herdr.inside() and have_tabs):
        cmd_up(argparse.Namespace(json=False, interval=20, workers=a.workers))
    if a.harness == "pi":
        if not codex_ready():
            cmd_setup(argparse.Namespace(json=False, import_login=False))
        print("  ⚓ crew ready · first mate coming on deck…", file=sys.stderr)
    else:
        print(board.banner(daemon_pid()))
        print(f"  first mate: {' '.join(cmd)}\n", file=sys.stderr)
    repo = Path(__file__).resolve().parents[1]
    os.chdir(repo)
    os.execvp(cmd[0], cmd)


def cmd_watch(a):
    board.watch(a.interval, once=a.once)


def cmd_tail(a):
    """Follow a work item's live run log (used by per-task herdr tabs)."""
    d = work.item_dir(a.id)
    print(f"{a.id} — waiting for the run to start…")
    deadline = time.time() + 120
    logf = None
    while time.time() < deadline and not logf:
        runs = sorted((d / "runs").glob("*/log.md")) if (d / "runs").exists() else []
        logf = runs[-1] if runs else None
        if not logf:
            time.sleep(1)
    if not logf:
        print("no run started within 120s"); return
    print(f"following {logf}\n")
    os.execvp("tail", ["tail", "-n", "+1", "-F", str(logf)])


def cmd_set(a):
    p = registry.set_fields(a.id, mode=a.mode, authority=a.authority, test_cmd=a.test, base=a.base,
                            protected_paths=a.protected.split(",") if a.protected else None)
    out(p, a.json, f"{p['id']}: {p['mode']} authority {p['authority']} base {p['base']}")


def cmd_projects(a):
    ps = registry.load()["projects"]
    if a.json:
        return out(ps, True)
    items = work.all_items()
    for p in ps.values():
        open_ = [i for i in items if i["project"] == p["id"] and i["status"] in work.OPEN]
        print(f"{p['id']:<20} {p['mode']:<12} auth {p['authority']}  open {len(open_):<3} {p['path']}")


def cmd_task(a):
    text = Path(a.file).read_text() if a.file else " ".join(a.text)
    if not text.strip():
        raise HelmError("empty task")
    it = work.create(a.project, text, a.kind, a.labels.split(",") if a.labels else [], a.max_attempts)
    out(it, a.json, f"{it['id']} queued → graph {it['dispatch']['graph']} (rule {it['dispatch']['rule']})")


def cmd_work(a):
    items = work.all_items()
    if not a.all:
        items = [i for i in items if i["status"] in work.OPEN]
    if a.json:
        return out(items, True)
    for i in items:
        extra = i.get("pr_url") or (i.get("ask") or {}).get("question", "")[:60] or ""
        print(f"{i['id']:<44} {i['status']:<10} {i['kind']:<5} a{i['attempts']}/{i['max_attempts']} {extra}")


def cmd_show(a):
    it = work.load(a.id)
    if a.json:
        return out(it, True)
    print(json.dumps({k: v for k, v in it.items() if k not in ("history",)}, indent=2))
    for h in it.get("history", []):
        print(f"  {h['at']} {h['from']} → {h['to']}  {h['note']}")
    rep = work.item_dir(it["id"]) / "report.md"
    if rep.exists():
        print(f"\nreport: {rep}")


def cmd_inbox(a):
    items = [i for i in work.all_items() if i["status"] in ("needs-you", "failed", "ready", "pr-open")]
    if a.json:
        return out(items, True)
    if not items:
        print("nothing needs you")
    for i in items:
        title = i["text"].splitlines()[0][:60]
        if i["status"] == "needs-you":
            print(f"[question]  {i['project']}: {title}\n            {(i.get('ask') or {}).get('question')}")
            if a.hints: print(f"            → helm respond {i['id']} \"…\"")
        elif i["status"] == "failed":
            last = (i["failure_notes"] or [{}])[-1].get("notes", "")[:300].replace("\n", " ")
            print(f"[failed]    {i['project']}: {title}\n            {last}")
            if a.hints: print(f"            → helm respond {i['id']} \"guidance\"  |  helm retry {i['id']}")
        else:
            what = i.get("pr_url") or f"branch {i['branch']}"
            print(f"[{i['status']}]{' ' * max(1, 11 - len(i['status']) - 2)}{i['project']}: {title}\n            {what} — say \"merge it\" to promote")
            if a.hints: print(f"            → helm promote {i['id']} --confirm")


def cmd_respond(a):
    it = work.respond(a.id, " ".join(a.guidance))
    out(it, a.json, f"{it['id']} requeued with guidance")


def cmd_retry(a):
    it = work.retry(a.id)
    out(it, a.json, f"{it['id']} requeued")


def cmd_cancel(a):
    it = work.load(a.id)
    if a.discard:
        registry_p = registry.get(it["project"])
        worktree.remove(registry_p, it["id"], delete_branch=True)
    it = work.cancel(a.id)
    out(it, a.json, f"{it['id']} cancelled")


def cmd_promote(a):
    it = work.load(a.id)
    p = registry.get(it["project"])
    ref = deliver.promote(it, p, a.confirm)
    out(work.load(a.id), a.json, f"{it['id']} merged: {ref}")


def cmd_run_once(a):
    it = work.claim_next(a.owner)
    if not it:
        out({"claimed": None}, a.json, "nothing queued")
        return
    it = work.execute(it, timeout=a.timeout)
    out(it, a.json, f"{it['id']}: {it['status']}")


def cmd_daemon(a):
    log(f"daemon start interval={a.interval}s")
    idle = 0
    while True:
        it = work.claim_next(a.owner)
        if it:
            idle = 0
            try:
                work.execute(it, timeout=a.timeout)
            except KeyboardInterrupt:
                raise
            except BaseException as e:  # execute() already marked the item failed; keep the loop alive
                log(f"{it['id']}: executor error {e!r}")
            continue
        idle += 1
        if a.once_idle and idle >= a.once_idle:
            log("daemon: queue drained, exiting")
            return
        time.sleep(a.interval)


def cmd_dispatch(a):
    cfg = dispatch.load()
    if a.set:
        from .util import write_json
        from .paths import dispatch_file
        for spec in a.set:
            phase, _, model = spec.partition("=")
            if phase not in dispatch.PHASES or "/" not in model:
                raise HelmError(f"use --set PHASE=provider/model with PHASE in {dispatch.PHASES}")
            cfg["models"][phase] = model
        write_json(dispatch_file(), cfg)
        print("models now: " + ", ".join(f"{k}={v}" for k, v in cfg["models"].items()))
        return
    if a.json:
        return out(cfg, True)
    print(f"dispatch file: {dispatch_file()}")
    print("defaults:", json.dumps(cfg["models"], indent=2))
    for r in cfg["rules"]:
        print(f"  rule {r.get('name'):<14} kind={r.get('kind','*'):<5} labels={r.get('labels',[])} graph={r.get('graph','<mode>')} models={r.get('models',{})}")


def cmd_doctor(a):
    ok = True
    def chk(name, good, detail=""):
        nonlocal ok
        ok &= bool(good)
        print(f"{'ok  ' if good else 'FAIL'} {name} {detail}")
    for b in ("git", "piw", "pi", "gh"):
        chk(b, shutil.which(b), shutil.which(b) or "not on PATH")
    chk("HELM_HOME", True, str(home()))
    chk("codex login", codex_ready(), str(pi_home()) if codex_ready() else "run `helm setup`")
    chk("projects", projects_file().exists(), str(projects_file()))
    cfg = dispatch.load()
    wanted = set(cfg["models"].values()) | {m for r in cfg["rules"] for m in r.get("models", {}).values()}
    have = set()
    if shutil.which("pi"):
        r = subprocess.run(["pi", "--list-models"], text=True, capture_output=True)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                have.add(f"{parts[0]}/{parts[1]}")
    from . import graphs as _g
    for m in sorted(wanted):
        listed = m in have
        if listed and a.probe:
            good, detail = _g.probe_model(m)
            chk(f"model {m}", good, detail)
        else:
            chk(f"model {m}", listed, "(listed; add --probe for a live call)" if listed else "not in `pi --list-models` — fix dispatch.json or /login")
    for g in ("no-mistakes", "direct-pr", "local-only", "scout"):
        chk(f"graph {g}", (GRAPHS / f"{g}.yaml").exists())
    sys.exit(0 if ok else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="helm", description="one neck to choke for many repos")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def S(name, fn, help_):
        p = sub.add_parser(name, help=help_); p.set_defaults(fn=fn); p.add_argument("--json", action="store_true"); return p

    p = S("add", cmd_add, "register a repo"); p.add_argument("path"); p.add_argument("--id")
    p.add_argument("--mode", default="local-only", choices=registry.MODES); p.add_argument("--authority", type=int, default=1)
    p.add_argument("--test", help="test command (the verify gate); auto-detected when omitted")
    p.add_argument("--protected", help="comma-separated globs the agent may not change"); p.add_argument("--base")
    p = S("set", cmd_set, "change a project's posture"); p.add_argument("id"); p.add_argument("--mode", choices=registry.MODES)
    p.add_argument("--authority", type=int); p.add_argument("--test"); p.add_argument("--protected"); p.add_argument("--base")
    S("projects", cmd_projects, "list projects")
    p = S("task", cmd_task, "queue a ship or scout task"); p.add_argument("project"); p.add_argument("text", nargs="*")
    p.add_argument("--file"); p.add_argument("--kind", default="ship", choices=("ship", "scout"))
    p.add_argument("--labels", help="comma-separated dispatch labels, e.g. cheap,hard"); p.add_argument("--max-attempts", type=int, default=3)
    p = S("work", cmd_work, "list work items"); p.add_argument("--all", action="store_true")
    p = S("show", cmd_show, "show one item with history"); p.add_argument("id")
    p = S("inbox", cmd_inbox, "what needs the captain"); p.add_argument("--hints", action="store_true", help="show the helm commands (for the first mate)")
    p = S("respond", cmd_respond, "answer a question / give guidance, requeue"); p.add_argument("id"); p.add_argument("guidance", nargs="+")
    p = S("retry", cmd_retry, "requeue a failed item"); p.add_argument("id")
    p = S("cancel", cmd_cancel, "cancel an item"); p.add_argument("id"); p.add_argument("--discard", action="store_true")
    p = S("promote", cmd_promote, "merge a ready/pr-open item (captain's word)"); p.add_argument("id"); p.add_argument("--confirm", action="store_true")
    p = S("run-once", cmd_run_once, "claim and execute one queued item"); p.add_argument("--owner", default="cli"); p.add_argument("--timeout", type=int, default=3600)
    p = S("daemon", cmd_daemon, "execute forever"); p.add_argument("--owner", default="daemon"); p.add_argument("--interval", type=int, default=20)
    p.add_argument("--timeout", type=int, default=3600); p.add_argument("--once-idle", type=int, default=0, help="exit after N idle polls (tests)")
    p = S("dispatch", cmd_dispatch, "show dispatch table"); p.add_argument("--set", action="append", metavar="PHASE=provider/model", help="change a step's default model")
    p = S("setup", cmd_setup, "connect the first mate to the Codex subscription (own config, own login)")
    p.add_argument("--import-login", action="store_true", help="(default behaviour) reuse the Codex login from your Pi")
    p.add_argument("--fresh", action="store_true", help="ignore any existing Pi login and log in interactively")
    p = S("up", cmd_up, "start workers (herdr tabs when inside herdr, else background)"); p.add_argument("--interval", type=int, default=20)
    p.add_argument("--workers", type=int, default=2, help="worker tabs to open inside herdr")
    p = S("watch", cmd_watch, "live fleet board"); p.add_argument("--interval", type=float, default=2.0); p.add_argument("--once", action="store_true")
    p = S("tail", cmd_tail, "follow one item's run log"); p.add_argument("id")
    S("down", cmd_down, "stop background workers")
    S("status", cmd_status, "workers, projects, queue at a glance")
    p = S("captain", cmd_captain, "start workers and open the liaison (pi by default)")
    p.add_argument("harness", nargs="?", default="pi", help="pi | claude | codex | any command")
    p.add_argument("--workers", type=int, default=2)
    p = S("doctor", cmd_doctor, "check tools, models, graphs"); p.add_argument("--probe", action="store_true", help="live 1-word call per model (costs a few tokens)")
    a = ap.parse_args(argv)
    os.environ["PI_CODING_AGENT_DIR"] = str(pi_home())
    try:
        return a.fn(a)
    except HelmError as e:
        return e.code
    except subprocess.CalledProcessError as e:
        print(f"helm: command failed: {' '.join(e.cmd)}\n{e.stderr}", file=sys.stderr)
        return 1
