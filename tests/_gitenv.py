"""Test-side git hygiene: a global `core.fsmonitor=true` can hang plain git calls on fresh
temp repos (seen on macOS). helm disables it for its own calls; this does the same for the
tests' setup git and for every child process they spawn."""
import os

_keys = [("core.fsmonitor", "false"), ("core.untrackedCache", "false")]
_n = int(os.environ.get("GIT_CONFIG_COUNT", "0") or 0)
for key, value in _keys:
    os.environ[f"GIT_CONFIG_KEY_{_n}"] = key
    os.environ[f"GIT_CONFIG_VALUE_{_n}"] = value
    _n += 1
os.environ["GIT_CONFIG_COUNT"] = str(_n)
