"""Dispatch is data, not prose: the first matching rule decides graph + model pins.

A rule matches on kind (ship|scout), project id regex, and required labels.
Nothing here asks a model anything.
"""
from __future__ import annotations
import re
from .paths import dispatch_file
from .util import read_json, write_json, HelmError

PHASES = ("plan", "implement", "review_correctness", "review_adversarial", "scout")

DEFAULT = {
    "version": 1,
    # Opinionated: everything runs on the Codex subscription. Add other providers
    # (log in with /login inside `pi-firstmate`) and point phases at them here.
    "models": {
        "plan": "openai-codex/gpt-5.6-sol",
        "implement": "openai-codex/gpt-5.6-sol",
        "review_correctness": "openai-codex/gpt-5.6-sol",
        "review_adversarial": "openai-codex/gpt-5.6-sol",
        "scout": "openai-codex/gpt-5.6-sol",
    },
    "thinking": {"plan": "high", "implement": "medium", "review_correctness": "medium",
                 "review_adversarial": "high", "scout": "medium"},
    "rules": [
        {"name": "scout", "kind": "scout", "graph": "scout"},
        {"name": "cheap", "kind": "ship", "labels": ["cheap"],
         "models": {"implement": "openai-codex/gpt-5.4-mini"}, "thinking": {"implement": "low"}},
        {"name": "hard", "kind": "ship", "labels": ["hard"],
         "thinking": {"plan": "high", "implement": "high", "review_adversarial": "high"}},
        {"name": "default-ship", "kind": "ship"},
    ],
}


def load() -> dict:
    data = read_json(dispatch_file())
    if data is None:
        write_json(dispatch_file(), DEFAULT)
        data = DEFAULT
    return data


def resolve(item: dict, project: dict) -> dict:
    """Return {rule, graph, models{phase:model}, thinking{phase:level}} deterministically."""
    cfg = load()
    labels = set(item.get("labels") or [])
    for rule in cfg.get("rules", []):
        if rule.get("kind") and rule["kind"] != item["kind"]:
            continue
        if rule.get("project") and not re.fullmatch(rule["project"], project["id"]):
            continue
        if not set(rule.get("labels") or []) <= labels:
            continue
        graph = rule.get("graph") or (project["mode"] if item["kind"] == "ship" else "scout")
        models = {**cfg.get("models", {}), **rule.get("models", {})}
        thinking = {**cfg.get("thinking", {}), **rule.get("thinking", {})}
        missing = [p for p in PHASES if p not in models]
        if missing:
            raise HelmError(f"dispatch rule '{rule.get('name')}' leaves phases without a model: {missing}")
        return {"rule": rule.get("name", "?"), "graph": graph, "models": models, "thinking": thinking}
    raise HelmError(f"no dispatch rule matches kind={item['kind']} labels={sorted(labels)}")
