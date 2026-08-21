# helm

**One neck to choke for a portfolio of repos.** A liaison agent talks to you; `helm`
(deterministic Python, no model in the control path) owns intake → dispatch → lease →
worktree → run → deliver → promote; [pi-graph](https://github.com/ali-abassi/pi-graph)'s
`piw` owns the ordered phases inside one attempt; models only work inside nodes and
cannot skip one. Inspired by [firstmate](https://github.com/kunchenguid/firstmate)'s
contract (project modes, authority, liaison hard rules, ask-don't-guess), with the
orchestration moved out of prose and into code.

```
captain ──chat──► liaison (any harness + AGENTS.md; read-only)
                     │ helm task / inbox / respond / promote --confirm
                     ▼
                  helm (this repo)  ~/.helm/{projects,dispatch}.json, work/<id>/
                     │ per item: lease → git worktree → render graph → piw run
                     ▼
                  piw  graphs/<mode>.yaml   plan → implement → protected → verify → reviews
                       model pins per phase: Codex sub · Claude · DeepSeek · … (pi --list-models)
```

## Install

```sh
git clone <this repo> ~/helm && ln -sf ~/helm/bin/helm ~/.local/bin/helm
helm doctor            # git, piw, pi, gh, every model in dispatch.json resolvable
```

Requires `piw` (pi-graph) and `pi` with providers logged in; `gh` for PR modes.

## Use

```sh
helm add ~/code/api --test "npm test" --mode direct-pr --authority 2
helm add ~/code/lib --test "pytest -q" --mode local-only --authority 3 --protected ".github/*,pyproject.toml"
helm task api "fix flaky login test" --labels cheap
helm task api "why does sync double-write?" --kind scout
helm daemon                        # or: helm run-once
helm inbox                         # asks, failures, ready branches / open PRs
helm respond ID "use oauth"        # answer → requeued with guidance
helm promote ID --confirm          # FF-merge (local-only) or gh pr merge (needs authority 3)
```

## Model

- **Modes** (per project): `local-only` → branch left for FF merge; `direct-pr` →
  implement+verify+one review, PR opened; `no-mistakes` → plan, implement, protected-path
  gate, verify, correctness **and** adversarial review, PR opened.
- **Authority** (per project, human-raised only): 0 observe (scouts only) · 1 build ·
  2 open PR · 3 merge via `promote --confirm`.
- **Dispatch** (`~/.helm/dispatch.json`): first matching rule by kind/labels/project regex
  fixes graph + `provider/model` + thinking per phase. Wrong/drifted model fails the
  node (pi-graph rule) rather than silently substituting.
- **Attempts**: gate failure → worktree discarded, failure evidence appended to the next
  brief, requeued up to `--max-attempts` (3). An agent that writes `.helm-ask.json`
  instead of guessing parks the item in `needs-you` without burning an attempt.
- **Evidence**: `~/.helm/work/<id>/` holds `item.json` (state + history), `brief.md`,
  the exact rendered `steps.yaml`, and `runs/` (pi-graph bundles: per-node output,
  trace, tokens, cost). `piw ui ~/.helm/work/<id>/steps.yaml` opens Studio on it.
- **Concurrency**: one running item per project; `helm daemon` in several terminals (or
  machines sharing `HELM_HOME`) share the lock-protected queue.

## Tests

```sh
python3 -m unittest discover -s tests      # drives the whole pipeline with tests/fake_piw.py
```
