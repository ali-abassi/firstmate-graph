#!/usr/bin/env bash
# firstmate graph installer: puts `helm` on PATH and registers the skill for pi / Claude Code / Codex.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bindir="${HELM_BIN:-$HOME/.local/bin}"
python_bin="${HELM_PYTHON:-python3}"

# The bundled pi-graph runner needs three Python packages; keep them in a repo-local venv.
if [ ! -x "$here/.venv/bin/python" ]; then
  "$python_bin" -m venv "$here/.venv"
fi
"$here/.venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$here/vendor/pi-graph/requirements.txt"
"$here/vendor/pi-graph/bin/piw" schema --json >/dev/null || { echo "bundled runner failed to start" >&2; exit 1; }
mkdir -p "$bindir" && ln -sf "$here/bin/helm" "$bindir/helm" && ln -sf "$here/bin/pi-firstmate" "$bindir/pi-firstmate"
for d in "$HOME/.pi/agent/skills" "$HOME/.claude/skills" "$HOME/.agents/skills"; do
  mkdir -p "$d" && ln -sfn "$here" "$d/firstmate-graph"
done
case ":$PATH:" in *":$bindir:"*) ;; *) echo "note: add $bindir to your PATH";; esac
echo "installed: $bindir/pi-firstmate"
cat <<MSG

next:  pi-firstmate
       (first run connects to your Codex subscription; then just talk — "add ~/code/my-repo")
MSG
