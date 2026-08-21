#!/usr/bin/env python3
"""Stand-in for `piw` so the pipeline is testable without spending tokens.

Behaviour is driven by FAKE_PIW_MODE: ok | ask | fail | scout.
Reads cwd/BASE/BRANCH out of the rendered steps.yaml, like the real runner would.
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

argv = sys.argv[1:]
if argv[:1] == ["validate"]:
    text = Path(argv[1]).read_text()
    if "@{" in text:
        print("unrendered placeholder"); sys.exit(1)
    sys.exit(0)
assert argv[:1] == ["run"], argv
steps = Path(argv[1])
text = steps.read_text()
cwd = re.search(r"^cwd: (.+)$", text, re.M).group(1).strip()
run_dir = steps.parent / "runs" / f"fake-{int(time.time()*1000)}"
run_dir.mkdir(parents=True)
brief = Path(argv[argv.index("--input-file") + 1]).read_text()
(run_dir / "input.txt").write_text(brief)
mode = os.environ.get("FAKE_PIW_MODE", "ok")
# Per-item behaviour can be requested from inside the brief, so one daemon can serve a mixed queue.
for marker in ("ask", "fail", "ok"):
    if f"[fake:{marker}]" in brief:
        mode = marker
if mode == "ask" and "Captain guidance" in brief:
    mode = "ok"          # the question was answered; a real worker would proceed too
if "workflow: helm-scout" in text:
    mode = "scout"
(run_dir / "mode.txt").write_text(mode)
# Evidence for concurrency assertions: when this "worker" started and finished, and where.
started = time.time()
work_seconds = float(os.environ.get("FAKE_PIW_SECONDS", "0"))
time.sleep(work_seconds)
(run_dir / "worker.json").write_text(json.dumps({"cwd": cwd, "started": started, "finished": time.time(), "pid": os.getpid()}))

def done(ok, failed):
    print(json.dumps({"ok": ok, "passed": 1, "failed": len(failed), "cached": 0, "skipped": 0,
                      "cost": 0.01, "tokens": 123, "run_dir": str(run_dir), "failed_ids": failed}))
    sys.exit(0 if ok else 1)

if mode == "ask":
    Path(cwd, ".helm-ask.json").write_text(json.dumps({"question": "Which auth provider?", "context": "two exist"}))
    (run_dir / "protected.stderr").write_text("ASKED")
    done(False, ["protected"])
if mode == "fail":
    (run_dir / "verify.stderr").write_text("FAIL test_thing: expected 2 got 3")
    done(False, ["verify"])
if mode == "scout":
    (run_dir / "report.md").write_text("# Report\n\nfindings…\n")
    done(True, [])
# ok: make a commit in the worktree, honouring guidance if present
Path(cwd, "helm-change.txt").write_text("changed\n" + ("guided\n" if "Captain guidance" in brief else ""))
subprocess.run(["git", "-C", cwd, "add", "-A"], check=True)
subprocess.run(["git", "-C", cwd, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "helm: fake change"], check=True)
done(True, [])
