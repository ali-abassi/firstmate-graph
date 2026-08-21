#!/usr/bin/env bash
# firstmate graph installer: puts `helm` on PATH and registers the skill for pi / Claude Code / Codex.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bindir="${HELM_BIN:-$HOME/.local/bin}"
mkdir -p "$bindir" && ln -sf "$here/bin/helm" "$bindir/helm" && ln -sf "$here/bin/pi-firstmate" "$bindir/pi-firstmate"
for d in "$HOME/.pi/agent/skills" "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$d" && ln -sfn "$here" "$d/firstmate-graph"
done
case ":$PATH:" in *":$bindir:"*) ;; *) echo "note: add $bindir to your PATH";; esac
echo "installed: $bindir/helm, $bindir/pi-firstmate"
"$bindir/helm" doctor || true
cat <<MSG

next:
  helm add ~/code/some-repo      # register a repo (test command auto-detected)
  pi-firstmate                   # start workers + open the first mate in pi (or: pi-firstmate claude)
MSG
