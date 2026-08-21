# firstmate graph

[![tests](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml/badge.svg)](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-11110f)](LICENSE)

**You talk to one agent. It runs a crew across your repos and comes back only when it needs you.**

```
you ──► first mate ──► crew: one agent per task, each in its own copy of the repo
                          implement → test → review, steps it cannot skip
you ◄── first mate ◄── questions · finished branches · failures
```

You describe the outcome. The first mate hands it to a worker, watches the crew in the
background, and reports when something is ready or needs a decision. Nothing merges until
you say so. Runs on your Codex subscription.

## Why

One coding agent is easy. Five of them across five repos means five terminals, five
half-remembered contexts, and you as the scheduler. firstmate graph gives you one
conversation instead: the first mate keeps the thread, code decides what runs and in what
order, and every run leaves evidence on disk.

It keeps the operating contract of [firstmate](https://github.com/kunchenguid/firstmate)
([fork](https://github.com/ali-abassi/firstmate)) and runs each task as a
[pi-graph](https://github.com/ali-abassi/pi-graph) workflow.

## Proof

**[`tests/test_one_thread.py`](tests/test_one_thread.py)** runs the whole idea on every push:
six tasks, three repos, two workers in parallel, one worker that stops to ask a question,
one inbox with everything in it, no repo touched until the captain says merge.

**[`docs/evidence/interactive-session.md`](docs/evidence/interactive-session.md)** is a
transcript of `pi-firstmate` used for real: delegate, get told the truth when it failed,
retry, merge on the captain's word. **[`live-run.md`](docs/evidence/live-run.md)** is the
same path as an opt-in test (`HELM_LIVE=1 python3 -m unittest tests.test_live`).

```sh
python3 -m unittest discover -s tests -v     # 30 tests, no tokens spent
```

## Install

```sh
git clone https://github.com/ali-abassi/firstmate-graph ~/firstmate-graph && ~/firstmate-graph/install.sh
pi-firstmate
```

Requires [Pi](https://github.com/earendil-works/pi) and [pi-graph](https://github.com/ali-abassi/pi-graph)
on your PATH, git, and a Codex subscription (`gh` only if you want PRs). The first run
reuses the Codex login from your Pi, in a config home of its own — nothing from your
personal Pi setup is inherited. macOS and Linux.

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

The first mate wakes itself when the crew has news, and `/wake 20m` schedules a check-in.
Inside Pi: `/fleet` shows the board, `/inbox` what needs you. In [Herdr](https://herdr.dev)
you also get a `⚓ fleet` tab, a tab per worker, a tab per running task, and notifications.

`pi-firstmate stop` stops the crew. `pi-firstmate claude` opens the same first mate in
Claude Code. That's the whole surface; the machinery underneath is in
[`docs/cli.md`](docs/cli.md) for the curious.

## Rules

| | |
|---|---|
| **Delivery** per repo | a branch for you to merge (default) · a pull request · or the careful mode: plan, protected-path gate, two independent reviews, then a PR. You pick by saying so ("open PRs for api") |
| **Authority** per repo | investigate only · build · open PRs · merge on your word. Starts at build; raised only when you ask |
| **Models** | GPT-5.6 Sol by default; every model your login offers is available (`/model`), and each step's model changes when you ask ("use luna for implementation"). A drifted model fails the step instead of silently swapping |
| **Retries** | a failed gate discards the worktree, keeps the evidence, retries up to 3 times |
| **Questions** | a worker that needs a decision stops and asks; it does not guess |
| **Evidence** | every task keeps its brief, exact graph, every step's output, tokens and cost on disk; the first mate quotes it |

## Status

Early and opinionated, used daily by one person. Issues and PRs welcome.

MIT.
