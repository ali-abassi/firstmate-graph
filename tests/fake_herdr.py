#!/usr/bin/env python3
"""Stand-in for the `herdr` CLI: records every call to $FAKE_HERDR_LOG and answers like herdr."""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a") as fh:
    fh.write(json.dumps(args) + "\n")
n = sum(1 for _ in open(os.environ["FAKE_HERDR_LOG"]))
if args[:2] == ["tab", "create"]:
    print(json.dumps({"result": {"tab": {"tab_id": f"w1:t{n}", "label": args[args.index('--label') + 1]},
                                 "root_pane": {"pane_id": f"w1:p{n}"}, "type": "tab_created"}}))
elif args[:2] in (["tab", "close"], ["pane", "run"], ["notification", "show"]):
    print(json.dumps({"result": {"type": "ok"}}))
else:
    print(json.dumps({"result": {}}))
