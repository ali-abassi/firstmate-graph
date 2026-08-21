# Interactive session — 2026-08-21

`pi-firstmate` driven in a tmux pane, with background workers, a real model
(`openai-codex/gpt-5.5`) and a scratch repo registered as `fizz` (local-only, authority 3).

| Captain said | First mate did |
|---|---|
| *hi, who are you and what can you do for me here?* | Introduced itself as the liaison: queues work through helm, never edits registered projects, promotes only on the captain's explicit word. |
| *in the fizz project, implement fizzbuzz(n) … queue it and tell me when it's done.* | `helm task fizz "…"`, checked `helm inbox` / `helm show`, reported **queued — "It hasn't run yet, so I'm not claiming completion."** |
| *what happened with the fizz task? give it to me straight.* | Read the evidence and reported plainly: **"It failed."** All 3 attempts failed at `verify` because the worktree lacked the repo's `.venv`. No promotion. |
| *(bug fixed on the helm side; workers restarted)* *retry once more and report with evidence.* | `helm retry`, waited for the worker, reported: implement + verify passed, `1 passed`, commit `f8aa99b`, branch ready — **"It is ready but not promoted or merged."** |
| *looks good. merge it.* | `helm promote … --confirm` → **main fast-forwarded to f8aa99b.** |

Verified outside the session: `git log` on the repo shows the commit on `main`, working tree
clean, `pytest` green, item state `merged`.

## What the failure taught (fixed in the same session)

A fresh git worktree holds tracked files only. The repo's `.venv` (untracked — a venv
ignores itself from the inside) was missing, so the auto-detected test command could not
run. helm now symlinks untracked dependency trees (`node_modules`, `.venv`, `venv`,
`vendor`, `.tox`, `target`) from the checkout into each worktree, and hands the worker an
excludes file via `GIT_CONFIG_*` so `git add -A` can never commit the links
(`node_modules/` in `.gitignore` matches directories, not symlinks). Covered by
`test_ignored_dependency_dirs_are_linked_into_worktree_not_committed`.
