from __future__ import annotations
import datetime as _dt
import fcntl
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic: temp file + rename, so a crash never leaves a half-written record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


@contextmanager
def locked(path: Path):
    """Exclusive advisory lock; released on process death."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def sh(args: list[str], cwd: Path | str | None = None, check: bool = True,
       env: dict | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, check=check, text=True,
                          capture_output=True, env=env, timeout=timeout)


def git(repo: Path | str, *args: str, check: bool = True) -> str:
    return sh(["git", "-C", str(repo), *args], check=check).stdout.strip()


def log(msg: str) -> None:
    from .paths import log_file
    line = f"{now()} {msg}"
    try:
        log_file().parent.mkdir(parents=True, exist_ok=True)
        with log_file().open("a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, file=sys.stderr)


class HelmError(SystemExit):
    def __init__(self, msg: str, code: int = 1):
        super().__init__(code)
        self.msg = msg
        print(f"helm: {msg}", file=sys.stderr)
