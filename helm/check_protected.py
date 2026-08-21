"""stdin: changed file list; argv: glob patterns. Exit 1 if any changed path is protected."""
import sys
from fnmatch import fnmatch
patterns = sys.argv[1:]
bad = [p for p in (l.strip() for l in sys.stdin) if p and any(fnmatch(p, g) for g in patterns)]
if bad:
    print("protected paths changed: " + ", ".join(bad))
    sys.exit(1)
print("protected paths untouched")
