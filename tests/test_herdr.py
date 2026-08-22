"""Inside Herdr the fleet is visible: a board tab, worker tabs, one tab per running task, notifications."""
import _gitenv  # noqa: F401  (git hygiene for temp repos)
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELM = [sys.executable, str(REPO / "bin" / "helm")]


class HerdrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.home = self.tmp / "home"; self.bin = self.tmp / "bin"; self.bin.mkdir()
        (self.bin / "herdr").symlink_to(REPO / "tests" / "fake_herdr.py")
        self.log = self.tmp / "herdr-calls.jsonl"; self.log.touch()
        self.proj = self.tmp / "proj"; self.proj.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], check=True, capture_output=True)
        g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (self.proj / "README.md").write_text("x"); g("add", "-A"); g("commit", "-qm", "init")
        self.env = {**os.environ, "HELM_HOME": str(self.home), "HELM_PIW": str(REPO / "tests" / "fake_piw.py"),
                    "PATH": f"{self.bin}:{os.environ['PATH']}", "FAKE_HERDR_LOG": str(self.log),
                    "HERDR_ENV": "1", "HERDR_WORKSPACE_ID": "w1", "HERDR_SESSION": "pi-x", "HERDR_PANE_ID": "w1:p1"}

    def helm(self, *args, check=True):
        r = subprocess.run(HELM + list(args), env=self.env, text=True, capture_output=True)
        if check and r.returncode != 0:
            self.fail(f"helm {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]

    def test_up_opens_board_and_worker_tabs_beside_the_captain_and_down_closes_them(self):
        out = self.helm("up", "--workers", "3").stdout
        self.assertIn("opened 4 herdr tabs", out)
        creates = [c for c in self.calls() if c[:2] == ["tab", "create"]]
        self.assertEqual(len(creates), 4)
        for c in creates:
            self.assertIn("--workspace", c); self.assertEqual(c[c.index("--workspace") + 1], "w1")
            self.assertIn("--no-focus", c)                                   # never steal the captain's focus
            self.assertEqual(c[-2:], ["--session", "pi-x"])                    # always the captain's session
            self.assertIn(f"HELM_HOME={self.home}", c)                          # tabs share the captain's home
        labels = [c[c.index("--label") + 1] for c in creates]
        self.assertEqual(labels, ["⚓ fleet", "worker 1", "worker 2", "worker 3"])
        runs = [c for c in self.calls() if c[:2] == ["pane", "run"]]
        self.assertIn("watch", runs[0][3]); self.assertIn("daemon --owner worker-1", runs[1][3])
        self.assertIn("workers already open", self.helm("up").stdout)        # idempotent
        self.assertIn("herdr tabs", self.helm("status").stdout)
        self.helm("down")
        closes = [c for c in self.calls() if c[:2] == ["tab", "close"]]
        self.assertEqual(sorted(c[2] for c in closes), sorted(c for c in ["w1:t1", "w1:t3", "w1:t5", "w1:t7"]))
        self.assertEqual(json.loads((self.home / "herdr.json").read_text())["tabs"], [])

    def test_each_running_task_gets_a_tab_then_it_closes_and_captain_is_notified(self):
        self.helm("add", str(self.proj), "--id", "p", "--test", "true", "--mode", "local-only")
        it = json.loads(self.helm("task", "p", "add a thing", "--json").stdout)
        self.helm("run-once")
        calls = self.calls()
        creates = [c for c in calls if c[:2] == ["tab", "create"]]
        self.assertEqual(len(creates), 1)
        self.assertTrue(creates[0][creates[0].index("--label") + 1].startswith("⚙ p: add a thing"))
        run = [c for c in calls if c[:2] == ["pane", "run"]][0]
        self.assertIn(f"tail {it['id']}", run[3])
        self.assertTrue(any(c[:2] == ["tab", "close"] for c in calls), "task tab must close when the task ends")
        notes = [c for c in calls if c[:2] == ["notification", "show"]]
        self.assertEqual(notes[0][2], "p: ready")
        self.assertEqual(json.loads((self.home / "herdr.json").read_text())["tabs"], [])

    def test_ask_notifies_captain(self):
        self.helm("add", str(self.proj), "--id", "p", "--test", "true", "--mode", "local-only")
        self.helm("task", "p", "thing [fake:ask]")
        self.helm("run-once")
        notes = [c for c in self.calls() if c[:2] == ["notification", "show"]]
        self.assertEqual(notes[0][2], "p needs you"); self.assertIn("Which auth provider?", notes[0][4])

    def test_herdr_failure_never_fails_the_task(self):
        (self.bin / "herdr").unlink(); (self.bin / "herdr").write_text("#!/bin/sh\nexit 3\n"); (self.bin / "herdr").chmod(0o755)
        self.helm("add", str(self.proj), "--id", "p", "--test", "true", "--mode", "local-only")
        it = json.loads(self.helm("task", "p", "thing", "--json").stdout)
        self.helm("run-once")
        self.assertEqual(json.loads(self.helm("show", it["id"], "--json").stdout)["status"], "ready")

    def test_banner_and_watch_once(self):
        out = self.helm("watch", "--once").stdout
        self.assertIn("F I R S T   M A T E", out); self.assertIn("workers   in herdr tabs", out); self.assertIn("none yet", out)


if __name__ == "__main__":
    unittest.main()
