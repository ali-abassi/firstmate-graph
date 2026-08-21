# firstmate graph

[![tests](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml/badge.svg)](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-11110f)](LICENSE)

**One agent to talk to. Many agents doing the work. One place to see results.**

```
you ──► liaison agent ──► helm queue ──► workers (one per repo at a time, many repos at once)
                                            │
you ◄── helm inbox ◄────────────────────────┘   questions · finished branches · failures
```

You describe work. The liaison queues it. Workers run each task in its own git worktree,
through a fixed sequence of steps (implement → verify → review) that a model cannot skip.
Everything comes back through one inbox. Nothing merges until you say so.

## Why

Coding agents are good at one task. Running ten of them across five repos turns you into
a tab-juggler. firstmate graph gives you a single thread: you talk to one agent, code
decides what runs and when, models only work inside the steps, and the evidence of every
run is kept on disk.

It borrows its operating contract from [firstmate](https://github.com/kunchenguid/firstmate)
([our fork](https://github.com/ali-abassi/firstmate)) and runs the steps with
[pi-graph](https://github.com/ali-abassi/pi-graph).

## Proof

**[`tests/test_one_thread.py`](tests/test_one_thread.py)** runs the whole idea on every push:
six tasks, three repos, two workers in parallel, one worker that stops to ask a question,
one inbox with everything in it, no repo touched until `promote --confirm`.

**[`docs/evidence/live-run.md`](docs/evidence/live-run.md)** is a dated record of the same
path against the real `piw` and a real model (`tests/test_live.py`, opt-in with `HELM_LIVE=1`).

```sh
python3 -m unittest discover -s tests -v     # 16 tests, no tokens spent
```

## Install

```sh
git clone https://github.com/ali-abassi/firstmate-graph ~/firstmate-graph
ln -sf ~/firstmate-graph/bin/helm ~/.local/bin/helm
helm doctor --probe
```

Needs [pi-graph](https://github.com/ali-abassi/pi-graph) (`piw`), `pi` logged in to a
provider, and `gh` for PR modes. Defaults use the Codex subscription and DeepSeek;
edit `~/.helm/dispatch.json` to change models.

## Use

```sh
helm add ~/code/api --test "npm test" --mode direct-pr --authority 2   # register a repo
helm task api "fix the flaky login test"                               # delegate
helm task api "why does sync double-write?" --kind scout               # or investigate
helm daemon                                                            # run workers
helm inbox                                                             # see what came back
helm respond ID "use the existing OAuth provider"                      # answer a question
helm promote ID --confirm                                              # merge, on your word
```

Start your coding agent inside this repo and it becomes the liaison;
[`AGENTS.md`](AGENTS.md) is its contract (`CLAUDE.md` links to it for Claude Code).

```sh
cd ~/firstmate-graph && claude --dangerously-skip-permissions   # or: codex · pi
```

## Rules

| | |
|---|---|
| **Mode** per repo | `local-only` leaves a branch · `direct-pr` opens a PR · `no-mistakes` adds a plan, a protected-path gate and two reviews first |
| **Authority** per repo | `0` investigate · `1` build · `2` open PRs · `3` merge on `--confirm` — only you raise it |
| **Dispatch** | a data file picks the graph and the model for each step; a wrong model fails the step |
| **Retries** | a failed gate discards the worktree, keeps the evidence, retries up to 3 times |
| **Questions** | a worker that needs a decision stops and asks; it does not guess |
| **Evidence** | `~/.helm/work/<id>/` — brief, exact graph, every step's output, tokens, cost |

MIT.
