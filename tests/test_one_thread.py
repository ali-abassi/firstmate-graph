"""The point of the project, as a test.

One liaison. Many workers, in parallel, across several repos. Exactly one channel back.

Scenario: the liaison queues six pieces of work across three projects. Two independent
daemon processes pick them up concurrently. One worker needs a human decision; it does not
guess. The liaison sees that — and everything else — in a single inbox, answers once, and
the work completes. Nobody touches the captain's checkouts until the captain says so.
"""
import _gitenv  # noqa: F401  (git hygiene for temp repos)
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELM = [sys.executable, str(REPO / "bin" / "helm")]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class OneThreadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.env = {**os.environ, "HELM_HOME": str(self.home),
                    "HELM_PIW": str(REPO / "tests" / "fake_piw.py"), "FAKE_PIW_SECONDS": "0.6"}
        self.projects = {}
        for name in ("api", "web", "docs"):
            repo = self.tmp / name
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
            (repo / "README.md").write_text(f"# {name}\n"); git(repo, "add", "-A"); git(repo, "commit", "-qm", "init")
            self.projects[name] = repo
            self.helm("add", str(repo), "--id", name, "--test", "true", "--mode", "local-only", "--authority", "3")

    def helm(self, *args, check=True):
        r = subprocess.run(HELM + list(args), env=self.env, text=True, capture_output=True)
        if check and r.returncode != 0:
            self.fail(f"helm {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    def items(self):
        return json.loads(self.helm("work", "--all", "--json").stdout)

    def run_two_daemons_until_drained(self):
        procs = [subprocess.Popen(HELM + ["daemon", "--owner", f"worker-{i}", "--interval", "0", "--once-idle", "3"],
                                  env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in (1, 2)]
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err)

    def test_one_liaison_many_workers_one_channel(self):
        # 1. The liaison delegates: six items, three repos, two kinds. One command each, no babysitting.
        queued = [
            self.helm("task", "api", "add rate limiting to /login", "--json"),
            self.helm("task", "api", "fix flaky session test [fake:ask]", "--json"),     # this one will need a human
            self.helm("task", "web", "dark mode toggle", "--json"),
            self.helm("task", "web", "why is the bundle 4MB?", "--kind", "scout", "--json"),
            self.helm("task", "docs", "document the new auth flow", "--json"),
            self.helm("task", "docs", "audit broken links", "--kind", "scout", "--json"),
        ]
        ids = [json.loads(r.stdout)["id"] for r in queued]
        heads_before = {n: git(r, "rev-parse", "HEAD") for n, r in self.projects.items()}

        # 2. Two workers run the queue concurrently.
        self.run_two_daemons_until_drained()
        by_id = {i["id"]: i for i in self.items()}

        # Five finished on their own; one stopped to ask instead of guessing.
        statuses = sorted(by_id[i]["status"] for i in ids)
        self.assertEqual(statuses, ["done", "done", "needs-you", "ready", "ready", "ready"], by_id)
        asker = next(i for i in ids if by_id[i]["status"] == "needs-you")
        self.assertEqual(by_id[asker]["ask"]["question"], "Which auth provider?")
        self.assertEqual(by_id[asker]["attempts"], 0, "asking must not burn an attempt")

        # 3. Work really ran in parallel across repos — and never in parallel within one repo.
        windows = []
        for it in by_id.values():
            for run in it["runs"]:
                w = json.loads((Path(run["run_dir"]) / "worker.json").read_text())
                windows.append((it["project"], w["started"], w["finished"], w["pid"]))
        overlaps_across = sum(1 for a in windows for b in windows
                              if a is not b and a[0] != b[0] and a[1] < b[2] and b[1] < a[2])
        overlaps_within = sum(1 for a in windows for b in windows
                              if a is not b and a[0] == b[0] and a[1] < b[2] and b[1] < a[2])
        self.assertGreater(overlaps_across, 0, "two daemons should have worked different repos at the same time")
        self.assertEqual(overlaps_within, 0, "one running item per repo, always")
        self.assertGreaterEqual(len({w[3] for w in windows}), 2, "both workers took work")
        owners = {h["note"] for it in by_id.values() for h in it["history"] if h["to"] == "running"}
        self.assertEqual(owners, {"leased by worker-1", "leased by worker-2"})

        # 4. One channel back. Everything the captain needs is in the single inbox — nowhere else.
        inbox = self.helm("inbox", "--hints").stdout   # the first mate reads it with ids
        self.assertIn("Which auth provider?", inbox)
        for i in ids:
            if by_id[i]["status"] in ("ready", "needs-you"):
                self.assertIn(i, inbox)
        self.assertEqual(inbox.count("[question]"), 1)
        self.assertEqual(inbox.count("[ready]"), 3)
        # Scout reports land as files the liaison can read back; they are not chat.
        for i in ids:
            if by_id[i]["kind"] == "scout":
                self.assertTrue((self.home / "work" / i / "report.md").is_file())

        # 5. Workers never wrote to the captain's checkouts. Only the captain's word moves main.
        for name, repo in self.projects.items():
            self.assertEqual(git(repo, "rev-parse", "HEAD"), heads_before[name], f"{name}/main moved without promotion")
            self.assertEqual(git(repo, "status", "--porcelain"), "")

        # 6. The liaison relays the captain's answer; the same worker pool finishes the job.
        self.helm("respond", asker, "use the existing OAuth provider")
        self.run_two_daemons_until_drained()
        it = json.loads(self.helm("show", asker, "--json").stdout)
        self.assertEqual(it["status"], "ready")
        self.assertIn("use the existing OAuth provider", (self.home / "work" / asker / "brief.md").read_text())

        # 7. Promotion is explicit, per item, and refuses without the word.
        self.assertEqual(self.helm("promote", asker, check=False).returncode, 1)
        self.helm("promote", asker, "--confirm")
        self.assertNotEqual(git(self.projects["api"], "rev-parse", "HEAD"), heads_before["api"])
        self.assertEqual(json.loads(self.helm("show", asker, "--json").stdout)["status"], "merged")

        # 8. Every delegation is auditable: who ran it, which graph, which model, what it cost.
        for i in ids:
            it = by_id[i]
            self.assertIn(it["dispatch"]["graph"], ("local-only", "scout"))
            self.assertTrue(it["dispatch"]["models"]["implement"])
            self.assertTrue((self.home / "work" / i / "steps.yaml").is_file())
            self.assertTrue(all(r["run_dir"] and Path(r["run_dir"]).is_dir() for r in it["runs"]))


if __name__ == "__main__":
    unittest.main()
