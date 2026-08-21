# firstmate graph

**One neck to choke for a portfolio of repos — firstmate's contract, run by a graph.**

[firstmate](https://github.com/kunchenguid/firstmate) (forked at
[ali-abassi/firstmate](https://github.com/ali-abassi/firstmate)) gives you one liaison agent
that runs a crew across your projects. Its contract is great — project modes, authority,
liaison hard rules, ask-don't-guess — but the orchestration lives in prose that a model
has to follow. **firstmate graph** keeps the contract and moves the orchestration into
code: `helm` (deterministic Python, no model in the control path) owns intake → dispatch
→ lease → worktree → run → deliver → promote, and
[pi-graph](https://github.com/ali-abassi/pi-graph)'s `piw` owns the ordered phases inside
one attempt. Models only work inside graph nodes and cannot skip one.

```
captain ──chat──► liaison (any harness launched in this repo; AGENTS.md; read-only)
                     │ helm task / inbox / respond / promote --confirm
                     ▼
                  helm   ~/.helm/{projects,dispatch}.json · work/<id>/ · worktrees/
                     │ per item: lease → git worktree → render graph → piw run
                     ▼
                  piw    graphs/<mode>.yaml
                         plan → implement → protected-path gate → verify → reviews
                         model pinned per phase via pi: Codex subscription · DeepSeek · any pi provider
```

## Install

```sh
git clone git@github.com:ali-abassi/firstmate-graph.git ~/firstmate-graph
ln -sf ~/firstmate-graph/bin/helm ~/.local/bin/helm
helm doctor --probe        # git, piw, pi, gh, and a live 1-word call per dispatch model
```

Requires [pi-graph](https://github.com/ali-abassi/pi-graph) (`piw`) and `pi` with providers
logged in (`pi` → `/login`); `gh` for PR modes. Python 3.10+, macOS/Linux.

> Models: defaults use the **Codex subscription** (`openai-codex/*`) and **DeepSeek via
> Baseten**. Anthropic through pi is not configured here; edit `~/.helm/dispatch.json` if
> your pi has a working provider for it. `helm doctor --probe` tells you what actually answers.

## Use

```sh
helm add ~/code/api --test "npm test" --mode direct-pr --authority 2
helm add ~/code/lib --test "pytest -q" --mode local-only --authority 3 --protected ".github/*,pyproject.toml"
helm task api "fix the flaky login test" --labels cheap
helm task api "why does sync double-write?" --kind scout
helm daemon                        # or: helm run-once
helm inbox                         # asks, failures, ready branches / open PRs
helm respond ID "use oauth"        # answer → requeued with guidance, attempts reset
helm promote ID --confirm          # FF-merge (local-only) or gh pr merge (needs authority 3)
```

To get the liaison, launch your harness (Claude Code, Pi, Codex…) inside this repo:
`AGENTS.md` is its contract — it reads projects, queues work with `helm`, relays questions,
and never merges without your word.

## Model

| Concept | Meaning |
|---|---|
| **Modes** (per project) | `local-only` → branch left for FF merge · `direct-pr` → implement, verify, one review, PR · `no-mistakes` → plan, implement, protected-path gate, verify, correctness **and** adversarial review, PR |
| **Authority** (per project, human-raised only) | 0 observe (scouts only) · 1 build · 2 open PR · 3 merge via `promote --confirm` |
| **Dispatch** (`~/.helm/dispatch.json`) | first matching rule by kind / labels / project regex fixes graph + `provider/model` + thinking per phase; a drifted model fails the node (pi-graph rule) |
| **Attempts** | gate failure → worktree discarded, failure evidence appended to the next brief, requeued up to `--max-attempts` (3) |
| **Ask, don't guess** | an agent that writes `.helm-ask.json` parks the item in `needs-you` without burning an attempt |
| **Evidence** | `~/.helm/work/<id>/`: `item.json` (state + history), `brief.md`, the exact rendered `steps.yaml`, `runs/` (pi-graph bundles: per-node output, trace, tokens, cost). `piw ui ~/.helm/work/<id>/steps.yaml` opens Studio |
| **Concurrency** | one running item per project; several `helm daemon`s sharing `HELM_HOME` share the lock-protected queue; dead owners' leases are reclaimed |

## What it borrows from firstmate, and what it changes

| firstmate | firstmate graph |
|---|---|
| Liaison hard rules in `AGENTS.md` | Same five rules, shorter (`AGENTS.md`) — and `helm` enforces them mechanically (authority, `--confirm`, unlanded-work refusal) |
| `no-mistakes` / `direct-PR` / `local-only` | Same three modes, each a pi-graph YAML you can read and `piw validate` |
| Judgment-based dispatch profiles | Data-only dispatch table; no model picks models |
| Bash watcher + harness Stop hooks for supervision | No supervision needed: `helm daemon` runs items; `helm inbox` is the only thing to read |
| Crewmates are harness sessions in tmux windows | Work items are `piw` runs with durable evidence bundles |
| Secondmates / Relay / backends | Not included |

## Tests

```sh
python3 -m unittest discover -s tests      # drives the whole pipeline with tests/fake_piw.py (no tokens)
```

Verified live on 2026-08-21: a `local-only` task through the real `piw` with
`openai-codex/gpt-5.4-mini` — 27 s, 26.9k tokens, $0.009, verify gate green, promoted by
fast-forward.

## License

MIT.
