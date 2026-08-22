# Under the hood: `helm`

The first mate drives a small CLI, `helm`, so the captain never has to. Everything below
is what the agent (or a curious developer) uses; `pi-firstmate` is the only user command.

```
helm setup [--import-login]        own Pi home + Codex login (pi-firstmate does this on first run)
helm add PATH [--id ID] [--mode M] [--authority N] [--test CMD] [--protected GLOBS] [--base BRANCH]
helm set ID [--mode M] [--authority N] [--test CMD]
helm projects
helm task PROJECT "request" [--kind ship|scout] [--labels cheap,hard] [--max-attempts N]
helm work [--all] · helm show ID · helm inbox [--hints]
helm respond ID "captain's answer" · helm retry ID · helm cancel ID [--discard]
helm promote ID --confirm
helm up [--workers N] · helm down · helm status · helm watch [--once] · helm tail ID
helm daemon · helm run-once
helm dispatch · helm doctor [--probe] · helm captain [pi|claude|codex]
```

State lives in `$HELM_HOME` (default `~/.helm`): `projects.json`, `dispatch.json`,
`work/<id>/` (item state, brief, rendered graph, pi-graph run bundles), `worktrees/`,
`pi/` (the first mate's own Pi config and login), `helm.log`.

Graphs are pi-graph workflows in `graphs/`; the bundled runner `vendor/pi-graph/bin/piw` is the only runner. Tests drive the
whole pipeline against `tests/fake_piw.py` and `tests/fake_herdr.py` without spending tokens.
