# firstmate graph

[![tests](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml/badge.svg)](https://github.com/ali-abassi/firstmate-graph/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-MIT-11110f)](LICENSE)

**Talk to one agent. It delegates to many. Everything comes back through one channel.**

You have many repos. You have a Codex subscription, some API keys, and coding agents that
are each good at one task at a time. What you don't have is a single place to say "do
these six things across these three projects" and then see, in one place, what got done,
what failed, and what needs your decision.

firstmate graph is that place.

```
you ──chat──► one liaison agent            (reads your repos; never writes to them)
                 │ queues work
                 ▼
              helm                          (plain Python; no model in the control path)
              queue · leases · one git worktree per attempt · delivery · promotion
                 │ one item at a time per repo, many repos at once
                 ▼
              piw (pi-graph)               (runs the steps of one attempt, in order, with proof)
              implement → verify → review   — each step pinned to a model you choose
                 │
                 ▼
              helm inbox                    (the one channel back: asks · failures · ready branches · PRs)
```

## Why this shape

- **One thread of communication.** You talk to the liaison. The liaison talks to `helm`.
  Workers never talk to you; they write evidence, and `helm inbox` is the only thing
  anyone needs to read.
- **Code decides, models work.** Which steps run, in which order, what counts as passing,
  how many retries, who may merge — all of that is code and data you can read. Models
  only work *inside* a step and cannot skip one.
- **Nothing leaves your machine without your word.** Every attempt runs in its own git
  worktree. Your checkouts are untouched until you run `helm promote --confirm`.
- **Ask, don't guess.** A worker that hits a real decision writes a question and stops.
  You answer once; the work continues with your answer in hand.

It keeps the operating contract of [firstmate](https://github.com/kunchenguid/firstmate)
(project modes, authority levels, the liaison's hard rules) and replaces its prose-driven
orchestration with [pi-graph](https://github.com/ali-abassi/pi-graph) workflows.
Our fork of the original lives at [ali-abassi/firstmate](https://github.com/ali-abassi/firstmate).

## The proof, as a test

[`tests/test_one_thread.py`](tests/test_one_thread.py) is the whole idea in one scenario,
and it runs on every push (see the badge):

1. The liaison queues **six tasks across three repos** — builds and investigations.
2. **Two worker processes** drain the queue concurrently. The test asserts they worked
   *different* repos at the same time and *never* the same repo at the same time.
3. One worker needs a human decision. It **asks instead of guessing**, and it costs no
   retry.
4. **Everything** the captain needs — the question, three finished branches, two
   investigation reports — shows up in **one inbox**, nowhere else.
5. No repo's `main` moved. No checkout is dirty.
6. The liaison relays the answer; the same worker pool finishes the job.
7. Promotion without `--confirm` is refused; with it, `main` fast-forwards.
8. Every delegation is auditable: who ran it, which graph, which model, what it cost.

The suite drives the real CLI end-to-end against a stand-in `piw` so it spends no tokens.
The same path was verified live with the real `piw` and `openai-codex/gpt-5.4-mini`:
27 s, $0.009, green tests, fast-forwarded.

```sh
python3 -m unittest discover -s tests -v
```

## Install

```sh
git clone https://github.com/ali-abassi/firstmate-graph ~/firstmate-graph
ln -sf ~/firstmate-graph/bin/helm ~/.local/bin/helm
helm doctor --probe      # checks git, piw, pi, gh, and makes a live 1-word call per model
```

You need [pi-graph](https://github.com/ali-abassi/pi-graph) (`piw`) and `pi` logged in to
at least one provider (`pi` → `/login`). `gh` is needed only for PR modes. Python 3.10+.
Defaults use the Codex subscription (`openai-codex/*`) and DeepSeek via Baseten; change
them in `~/.helm/dispatch.json`.

## Use

```sh
# register repos: the test command is the gate every change must pass
helm add ~/code/api  --test "npm test"  --mode direct-pr  --authority 2
helm add ~/code/lib  --test "pytest -q" --mode local-only --authority 3

# delegate
helm task api "fix the flaky login test"
helm task api "why does sync double-write?" --kind scout
helm task lib "add retry with backoff to the client" --labels hard

# run workers (as many terminals as you like)
helm daemon

# the one channel back
helm inbox
helm respond ID "use the existing OAuth provider"
helm promote ID --confirm
```

To get the liaison, start your coding agent (Claude Code, Codex, Pi, …) inside this repo.
[`AGENTS.md`](AGENTS.md) is its contract: read the repos, queue work with `helm`, relay
questions verbatim, never merge without your word.

## The rules, in one table

| | |
|---|---|
| **Mode** (per repo) | `local-only`: branch left for you to fast-forward · `direct-pr`: implement, verify, one review, open PR · `no-mistakes`: plan, implement, protected-path gate, verify, correctness **and** adversarial review, open PR |
| **Authority** (per repo, raised only by you) | `0` investigate only · `1` build in a worktree · `2` may open a PR · `3` may merge on `promote --confirm` |
| **Dispatch** | `~/.helm/dispatch.json`: the first rule matching kind / labels / repo fixes the graph and the `provider/model` per step. A drifted model fails the step; it is never silently swapped |
| **Attempts** | a failed gate discards the worktree, appends the evidence to the next brief, and requeues — up to 3 times |
| **Asking** | a worker writes `.helm-ask.json` and stops; the item waits in the inbox and keeps its retry budget |
| **Evidence** | `~/.helm/work/<id>/`: state and history, the brief, the exact rendered graph, and pi-graph's per-step outputs, trace, tokens and cost. `piw ui ~/.helm/work/<id>/steps.yaml` opens it in Studio |
| **Concurrency** | one running item per repo; any number of `helm daemon`s share the queue; a dead worker's lease is reclaimed |

## Layout

```
bin/helm          the CLI
helm/             registry · dispatch · work (state machine) · worktree · graphs · deliver
graphs/           local-only.yaml · direct-pr.yaml · no-mistakes.yaml · scout.yaml  (pi-graph workflows)
tests/            test_one_thread.py · test_helm.py · fake_piw.py
AGENTS.md         the liaison's contract
```

## License

MIT.
