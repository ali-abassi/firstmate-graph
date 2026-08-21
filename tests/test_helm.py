import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELM = [sys.executable, str(REPO / "bin" / "helm")]


class HelmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.proj = self.tmp / "proj"
        self.proj.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], check=True, capture_output=True, text=True)
        g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (self.proj / "README.md").write_text("hi\n"); g("add", "-A"); g("commit", "-qm", "init")
        self.env = {**os.environ, "HELM_HOME": str(self.home), "HELM_PIW": str(REPO / "tests" / "fake_piw.py")}

    def helm(self, *args, mode="ok", check=True):
        r = subprocess.run(HELM + list(args), env={**self.env, "FAKE_PIW_MODE": mode}, text=True, capture_output=True)
        if check and r.returncode != 0:
            self.fail(f"helm {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def add(self, **kw):
        args = ["add", str(self.proj), "--id", "p", "--test", "true"]
        for k, v in kw.items():
            args += [f"--{k}", str(v)]
        self.helm(*args)

    def task(self, text="add a file", **kw):
        args = ["task", "p", text, "--json"]
        for k, v in kw.items():
            args += [f"--{k}", str(v)]
        return json.loads(self.helm(*args).stdout)

    def show(self, wid):
        return json.loads(self.helm("show", wid, "--json").stdout)

    def test_local_only_ready_then_promote_ff(self):
        self.add(mode="local-only", authority=3)
        it = self.task()
        self.assertEqual(it["dispatch"]["graph"], "local-only")
        self.helm("run-once")
        it = self.show(it["id"])
        self.assertEqual(it["status"], "ready", it)
        self.assertTrue((self.home / "work" / it["id"] / "steps.yaml").exists())
        # promotion requires --confirm
        r = self.helm("promote", it["id"], check=False)
        self.assertEqual(r.returncode, 1)
        self.helm("promote", it["id"], "--confirm")
        log = subprocess.run(["git", "-C", str(self.proj), "log", "--oneline"], capture_output=True, text=True).stdout
        self.assertIn("helm: fake change", log)
        self.assertEqual(self.show(it["id"])["status"], "merged")
        self.assertFalse((self.home / "worktrees" / "p" / it["id"]).exists())

    def test_authority_gates_promotion(self):
        self.add(mode="local-only", authority=1)
        it = self.task(); self.helm("run-once")
        r = self.helm("promote", it["id"], "--confirm", check=False)
        self.assertEqual(r.returncode, 1); self.assertIn("authority 1 < 3", r.stderr)
        r = self.helm("task", "p", "x", "--kind", "ship", check=False)  # fine at authority 1
        self.assertEqual(r.returncode, 0)
        self.helm("set", "p", "--authority", "0")
        r = self.helm("task", "p", "x", check=False)
        self.assertEqual(r.returncode, 1); self.assertIn("authority 0", r.stderr)

    def test_ask_goes_to_inbox_and_respond_requeues_with_guidance(self):
        self.add(mode="local-only")
        it = self.task()
        self.helm("run-once", mode="ask")
        it = self.show(it["id"])
        self.assertEqual(it["status"], "needs-you"); self.assertEqual(it["attempts"], 0)
        self.assertEqual(it["ask"]["question"], "Which auth provider?")
        self.assertIn("helm respond", self.helm("inbox").stdout)
        self.helm("respond", it["id"], "use oauth")
        self.assertEqual(self.show(it["id"])["status"], "queued")
        self.helm("run-once", mode="ok")
        it = self.show(it["id"])
        self.assertEqual(it["status"], "ready")
        brief = (self.home / "work" / it["id"] / "brief.md").read_text()
        self.assertIn("use oauth", brief)
        wt = self.home / "worktrees" / "p" / it["id"]
        self.assertIn("guided", (wt / "helm-change.txt").read_text())

    def test_failures_requeue_with_notes_then_exhaust(self):
        self.add(mode="local-only")
        it = self.task(**{"max-attempts": 2})
        self.helm("run-once", mode="fail", check=False)
        it = self.show(it["id"])
        self.assertEqual(it["status"], "queued"); self.assertEqual(it["attempts"], 1)
        self.assertIn("expected 2 got 3", it["failure_notes"][0]["notes"])
        self.helm("run-once", mode="fail", check=False)
        it = self.show(it["id"])
        self.assertEqual(it["status"], "failed")
        brief = (self.home / "work" / it["id"] / "brief.md").read_text()
        self.assertIn("Earlier attempts failed", brief)
        self.helm("retry", it["id"]); self.helm("run-once", mode="ok")
        self.assertEqual(self.show(it["id"])["status"], "ready")

    def test_scout_writes_report_and_cleans_up(self):
        self.add(mode="no-mistakes", authority=0)
        it = self.task("why is login flaky?", kind="scout")
        self.assertEqual(it["dispatch"]["graph"], "scout")
        self.helm("run-once", mode="scout")
        it = self.show(it["id"])
        self.assertEqual(it["status"], "done")
        self.assertTrue((self.home / "work" / it["id"] / "report.md").exists())
        self.assertFalse((self.home / "worktrees" / "p" / it["id"]).exists())

    def test_dispatch_labels_pick_models_and_templates_render(self):
        self.add(mode="no-mistakes", authority=1)
        it = self.task("big refactor", labels="hard")
        self.assertEqual(it["dispatch"]["rule"], "hard")
        self.assertEqual(it["dispatch"]["thinking"]["implement"], "high")
        self.helm("run-once")
        steps = (self.home / "work" / it["id"] / "steps.yaml").read_text()
        self.assertNotIn("@{", steps)
        self.assertIn("thinking: high", steps)
        self.assertIn("review_adversarial", steps)
        # no-mistakes at authority 1 → ready, not PR
        self.assertEqual(self.show(it["id"])["status"], "ready")

    def test_per_project_concurrency_and_daemon_drain(self):
        self.add(mode="local-only")
        a = self.task("one"); b = self.task("two")
        self.helm("daemon", "--interval", "0", "--once-idle", "1")
        self.assertEqual({self.show(a["id"])["status"], self.show(b["id"])["status"]}, {"ready"})
        hist = self.show(b["id"])["history"]
        self.assertEqual(hist[0]["to"], "running")

    def test_stale_lease_is_reclaimed(self):
        self.add(mode="local-only")
        it = self.task()
        p = self.home / "work" / it["id"] / "item.json"
        d = json.loads(p.read_text()); d["status"] = "running"; d["lease"] = {"owner": "ghost", "pid": 999999}
        p.write_text(json.dumps(d))
        self.helm("run-once")                      # reclaims, then executes
        it = self.show(it["id"])
        self.assertEqual(it["status"], "ready")
        self.assertTrue(any("stale lease" in h["note"] for h in it["history"]))

    def test_add_autodetects_test_command(self):
        (self.proj / "package.json").write_text('{"scripts": {"test": "vitest"}}')
        r = self.helm("add", str(self.proj), "--id", "p", "--json")
        self.assertEqual(json.loads(r.stdout)["test_cmd"], "npm test")
        self.assertIn("detected", r.stderr)

    def test_up_status_down(self):
        self.add(mode="local-only")
        it = self.task()
        self.helm("up", "--interval", "1")
        self.assertIn("background (pid", self.helm("status").stdout)
        deadline = time.time() + 30
        while time.time() < deadline and self.show(it["id"])["status"] != "ready":
            time.sleep(0.5)
        self.assertEqual(self.show(it["id"])["status"], "ready")
        self.assertIn("stopped", self.helm("down").stdout)
        self.assertIn("stopped", self.helm("status").stdout)

    def test_ignored_dependency_dirs_are_linked_into_worktree_not_committed(self):
        (self.proj / ".gitignore").write_text("node_modules/\n")                       # root ignores node_modules only
        (self.proj / "node_modules").mkdir(); (self.proj / "node_modules" / "dep.js").write_text("x")
        (self.proj / ".venv").mkdir(); (self.proj / ".venv" / "marker").write_text("x")
        (self.proj / ".venv" / ".gitignore").write_text("*\n")                           # like `python -m venv`
        (self.proj / "vendor").mkdir(); (self.proj / "vendor" / "tracked.txt").write_text("x")   # NOT ignored
        subprocess.run(["git", "-C", str(self.proj), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.proj), "commit", "-qm", "deps"], check=True)
        self.add(mode="local-only")
        it = self.task(); self.helm("run-once")
        wt = self.home / "worktrees" / "p" / it["id"]
        self.assertTrue((wt / "node_modules").is_symlink() and (wt / "node_modules" / "dep.js").exists())
        self.assertTrue((wt / ".venv").is_symlink())
        self.assertFalse((wt / "vendor").is_symlink(), "tracked dirs come from git, not links")
        files = subprocess.run(["git", "-C", str(wt), "diff", "--name-only", "main...HEAD"], capture_output=True, text=True).stdout
        self.assertNotIn("node_modules", files); self.assertNotIn(".venv", files)


if __name__ == "__main__":
    unittest.main()
