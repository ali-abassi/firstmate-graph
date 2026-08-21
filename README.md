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

**[`docs/evidence/interactive-session.md`](docs/evidence/interactive-session.md)** is a
transcript of `pi-firstmate` used for real: delegate, get told the truth when it failed,
retry, merge on the captain's word. **[`live-run.md`](docs/evidence/live-run.md)** is the
same path as an opt-in test (`HELM_LIVE=1 python3 -m unittest tests.test_live`).

```sh
python3 -m unittest discover -s tests -v     # 16 tests, no tokens spent
```

## Install

```sh
git clone https://github.com/ali-abassi/firstmate-graph ~/firstmate-graph && ~/firstmate-graph/install.sh
pi-firstmate
```

The first run connects to your **Codex subscription** (GPT-5.6 Sol by default) in the
first mate's own Pi home — nothing from your personal Pi setup is inherited. Needs
[pi-graph](https://github.com/ali-abassi/pi-graph) (`piw`) and `pi`; `gh` only if you
want PRs.

## Use

There is one command, and then you talk.

```sh
pi-firstmate
```

> **you:** add ~/code/api and ~/code/web
> **first mate:** Registered both, captain — `api` runs `npm test`, `web` runs `pnpm test`. Local-only for now; say the word for PRs.
>
> **you:** fix the flaky login test in api, and find out why the web bundle is 4 MB
> **first mate:** Two items under way. I'll report when they land or need a decision.
>
> *(later)* **first mate:** Captain — the login fix is ready on a branch, tests green. The bundle scout wants to know: is the analytics SDK required in production?
> **you:** no, drop it. merge the login fix.
> **first mate:** Merged `api` to main. Guidance passed to the scout; it's back under way.

Inside Pi: `/fleet` shows the board, `/inbox` what needs you. In [Herdr](https://herdr.dev)
you also get a `⚓ fleet` tab, a tab per worker, a tab per running task, and notifications.

`pi-firstmate stop` stops the crew. `pi-firstmate claude` opens the same first mate in
Claude Code. That's the whole surface; the machinery underneath is in
[`docs/cli.md`](docs/cli.md) for the curious.

## Rules

| | |
|---|---|
| **Mode** per repo | `local-only` leaves a branch · `direct-pr` opens a PR · `no-mistakes` adds a plan, a protected-path gate and two reviews first |
| **Authority** per repo | `0` investigate · `1` build · `2` open PRs · `3` merge on your word — raised only when you ask |
| **Models** | GPT-5.6 Sol by default; every model your login offers is available (`/model`), and each step's model changes when you ask ("use luna for implementation"). A drifted model fails the step instead of silently swapping |
| **Retries** | a failed gate discards the worktree, keeps the evidence, retries up to 3 times |
| **Questions** | a worker that needs a decision stops and asks; it does not guess |
| **Evidence** | every task keeps its brief, exact graph, every step's output, tokens and cost on disk; the first mate quotes it |

MIT.
