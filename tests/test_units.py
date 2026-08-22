"""Unit tests for the decisions helm makes without a model: dispatch, rendering, authority."""
try:
    import _gitenv  # noqa: F401  (git hygiene for temp repos)
except ImportError:
    from tests import _gitenv  # noqa: F401
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


class Isolated(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        os.environ["HELM_HOME"] = str(self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)


class DispatchTests(Isolated):
    def test_first_matching_rule_wins_and_merges_models(self):
        from helm import dispatch
        proj = {"id": "api", "mode": "no-mistakes"}
        d = dispatch.resolve({"kind": "ship", "labels": ["cheap"]}, proj)
        self.assertEqual(d["rule"], "cheap")
        self.assertEqual(d["graph"], "no-mistakes")                       # graph falls back to project mode
        self.assertEqual(d["models"]["implement"], "openai-codex/gpt-5.4-mini")
        self.assertEqual(d["models"]["review_correctness"], "openai-codex/gpt-5.6-sol")  # default kept

    def test_scout_ignores_mode(self):
        from helm import dispatch
        d = dispatch.resolve({"kind": "scout", "labels": []}, {"id": "x", "mode": "direct-pr"})
        self.assertEqual(d["graph"], "scout")

    def test_project_regex_and_missing_model_fail_closed(self):
        from helm import dispatch
        from helm.util import write_json
        from helm.paths import dispatch_file
        write_json(dispatch_file(), {"models": {"implement": "a/b"}, "thinking": {},
                                     "rules": [{"name": "only-web", "project": "web-.*"}]})
        with self.assertRaises(SystemExit):                                # no rule for api
            dispatch.resolve({"kind": "ship", "labels": []}, {"id": "api", "mode": "local-only"})
        with self.assertRaises(SystemExit):                                # rule matches but phases lack models
            dispatch.resolve({"kind": "ship", "labels": []}, {"id": "web-1", "mode": "local-only"})


class RenderTests(Isolated):
    def test_every_graph_renders_with_no_placeholders_and_shell_intact(self):
        from helm import graphs, dispatch
        cfg = dispatch.load()
        proj = {"id": "p", "path": "/tmp/p", "base": "main", "test_cmd": "npm test", "protected_paths": [".github/*", "a b.txt"]}
        for g in ("local-only", "direct-pr", "no-mistakes", "scout"):
            steps = graphs.render(g, self.home / g, cwd=Path("/tmp/wt"), branch="helm/x", project=proj,
                                  models=cfg["models"], thinking=cfg["thinking"], timeout=42)
            text = steps.read_text()
            self.assertNotIn("@{", text, g)
            self.assertIn("cwd: /tmp/wt", text)
            if g != "scout":
                self.assertIn("$(git", text)                                     # shell survives rendering
            if g in ("direct-pr", "no-mistakes"):
                self.assertIn("$OUT", text)
                self.assertIn("'a b.txt'", text)                                 # protected globs are shell-quoted
                self.assertIn("npm test", text)

    def test_rendered_graphs_pass_the_bundled_runner_validate(self):
        from helm import graphs, dispatch
        os.environ.pop("HELM_PIW", None)
        cfg = dispatch.load()
        repo = self.home / "repo"; repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        proj = {"id": "p", "path": str(repo), "base": "main", "test_cmd": "true", "protected_paths": []}
        for g in ("local-only", "direct-pr", "no-mistakes", "scout"):
            steps = graphs.render(g, self.home / g, cwd=repo, branch="helm/x", project=proj,
                                  models=cfg["models"], thinking=cfg["thinking"], timeout=42)
            r = subprocess.run([graphs.piw_bin(), "validate", str(steps)], text=True, capture_output=True)
            self.assertEqual(r.returncode, 0, f"{g}: {r.stdout}{r.stderr}")


class ProtectedPathTests(unittest.TestCase):
    def check(self, files, globs):
        return subprocess.run([sys.executable, str(REPO / "helm" / "check_protected.py"), *globs],
                              input="\n".join(files), text=True, capture_output=True).returncode

    def test_blocks_protected_and_allows_others(self):
        self.assertEqual(self.check(["src/a.py"], [".github/workflows/*"]), 0)
        self.assertEqual(self.check(["src/a.py", ".github/workflows/ci.yml"], [".github/workflows/*"]), 1)
        self.assertEqual(self.check([], [".github/*"]), 0)


if __name__ == "__main__":
    unittest.main()


class DetectTests(unittest.TestCase):
    def repo(self, files):
        d = Path(tempfile.mkdtemp())
        for name, body in files.items():
            (d / name).parent.mkdir(parents=True, exist_ok=True); (d / name).write_text(body)
        return d

    def test_detects_common_stacks(self):
        from helm import detect
        cases = [
            ({"package.json": '{"scripts": {"test": "vitest"}}'}, "npm test"),
            ({"package.json": '{"scripts": {"test": "vitest"}}', "pnpm-lock.yaml": ""}, "pnpm test"),
            ({"package.json": '{"scripts": {"test": "echo \\"Error: no test specified\\""}}'}, None),
            ({"Cargo.toml": ""}, "cargo test"),
            ({"go.mod": ""}, "go test ./..."),
            ({"pyproject.toml": ""}, "python3 -m pytest -q"),
            ({"pyproject.toml": "", "uv.lock": ""}, "uv run pytest -q"),
            ({"Makefile": "build:\n\techo\ntest:\n\tpytest\n"}, "make test"),
            ({"README.md": ""}, None),
        ]
        for files, want in cases:
            self.assertEqual(detect.test_command(self.repo(files)), want, files)


class PiExtensionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bun"), "bun not installed")
    def test_extension_self_test_passes(self):
        r = subprocess.run(["bun", str(REPO / ".pi" / "extensions" / "firstmate.ts")], text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("checks passed", r.stdout)

    def test_voice_contract_is_in_agents_md_too(self):
        agents = (REPO / "AGENTS.md").read_text()
        self.assertIn('"captain"', agents)
        self.assertIn("promote", agents)


class OwnPiHomeTests(Isolated):
    def test_first_mate_has_its_own_pi_home_and_inherits_nothing(self):
        src = self.home / "captain-pi"; src.mkdir()
        (src / "auth.json").write_text(json.dumps({"openai-codex": {"access": "tok"}, "anthropic": {"x": 1}}))
        (src / "AGENTS.md").write_text("# personal agent"); (src / "extensions").mkdir()
        os.environ["PI_CODING_AGENT_DIR"] = str(src); os.environ["HELM_IMPORT_PI_DIR"] = str(src)
        from helm.cli import _isolated_pi_home
        dst = _isolated_pi_home()
        self.assertFalse((dst / "AGENTS.md").exists()); self.assertFalse((dst / "extensions").exists())
        self.assertFalse((dst / "auth.json").exists(), "no login is inherited silently")
        settings = json.loads((dst / "settings.json").read_text())
        self.assertEqual((settings["defaultProvider"], settings["defaultModel"]), ("openai-codex", "gpt-5.6-sol"))
        self.assertNotIn("enabledModels", settings, "no model cage: the captain decides")
        (dst / "settings.json").write_text(json.dumps({"defaultModel": "mine", "defaultProvider": "x"}))
        _isolated_pi_home()                                   # second run keeps the captain's choice
        self.assertEqual(json.loads((dst / "settings.json").read_text())["defaultModel"], "mine")
        # --import-login copies only the Codex credential
        r = subprocess.run([sys.executable, str(REPO / "bin" / "helm"), "setup", "--import-login", "--json"],
                           env={**os.environ}, text=True, capture_output=True)
        auth = json.loads((dst / "auth.json").read_text())
        self.assertEqual(list(auth), ["openai-codex"])
        del os.environ["PI_CODING_AGENT_DIR"]; del os.environ["HELM_IMPORT_PI_DIR"]

    def test_every_helm_command_runs_in_the_first_mates_pi_home(self):
        r = subprocess.run([sys.executable, "-c", "import os,sys; sys.argv=['helm','status','--json']; sys.path.insert(0, sys.argv[0]); "
                            "from helm import cli; cli.main(['status','--json']); print('DIR='+os.environ['PI_CODING_AGENT_DIR'])"],
                           cwd=str(REPO), env={**os.environ, "HELM_HOME": str(self.home)}, text=True, capture_output=True)
        self.assertIn(f"DIR={self.home.resolve()}/pi", r.stdout)


class DispatchSetTests(Isolated):
    def test_captain_can_change_a_steps_model(self):
        r = subprocess.run([sys.executable, str(REPO / "bin" / "helm"), "dispatch", "--set", "implement=openai-codex/gpt-5.6-luna"],
                           env={**os.environ, "HELM_HOME": str(self.home)}, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("implement=openai-codex/gpt-5.6-luna", r.stdout)
        from helm import dispatch
        self.assertEqual(dispatch.load()["models"]["implement"], "openai-codex/gpt-5.6-luna")
        r = subprocess.run([sys.executable, str(REPO / "bin" / "helm"), "dispatch", "--set", "bogus=x"],
                           env={**os.environ, "HELM_HOME": str(self.home)}, text=True, capture_output=True)
        self.assertEqual(r.returncode, 1)
