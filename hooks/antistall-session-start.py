#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# AntiStallClaude — SessionStart context injection.
# Reminds the agent the gate exists, reports whether a sprint is currently armed,
# and states the stop-ticket protocol so the agent knows the legitimate exits.
#
# NOTE: some Cowork builds do not surface project SessionStart additionalContext
# (the project Stop hook still fires). This injection is the soft-reminder layer;
# enforcement does not depend on it. See docs/MANUAL.md "Cowork notes".

from __future__ import annotations

import json
import os
import pathlib
import re


def _claude_dir() -> pathlib.Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (pathlib.Path(env) / ".claude").is_dir():
        return pathlib.Path(env) / ".claude"
    return pathlib.Path(__file__).resolve().parents[1]


def _read_gate(claude_dir: pathlib.Path):
    # Mirror the Stop hook's resolution so the reminder reflects THIS session:
    # session-scoped gate first, then a legacy project-wide gate honored only if
    # unowned or owned by this session.
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    sid = sid if sid and sid.strip() else None
    if sid:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:80]
        try:
            g = json.loads((claude_dir / f"sprint-gate-{safe}.json").read_text(encoding="utf-8"))
            if g.get("active"):
                return True, str(g.get("note", ""))
        except Exception:
            pass
    try:
        g = json.loads((claude_dir / "sprint-gate.json").read_text(encoding="utf-8"))
        if g.get("active") and g.get("owner") in (None, sid):
            return True, str(g.get("note", ""))
    except Exception:
        pass
    return False, ""


def main() -> None:
    claude_dir = _claude_dir()
    active, note = _read_gate(claude_dir)

    state = (
        f"A SPRINT IS CURRENTLY ARMED ({note}). The Stop hook WILL block you from ending a turn "
        "until you keep working to completion or write a valid stop-ticket."
        if active
        else "No sprint is currently armed (the gate is silent on normal turns)."
    )
    msg = (
        "[AntiStallClaude — anti-stall gate INSTALLED] A project Stop hook "
        "(.claude/hooks/antistall-gate.py) physically blocks the 'announce-then-halt' / silent "
        "drift-stop failure. While a sprint is armed (.claude/sprint-gate.json {\"active\":true}), "
        "every attempt to end a turn is blocked unless .claude/sprint-stop-ticket.json declares a "
        "fresh reason: DONE (whole queue finished — also clear sprint-gate.json), BLOCKED (a "
        "human-only decision halts ALL remaining work), or QUESTION (you asked the human and need "
        "the answer). Helper: python3 .claude/hooks/antistall.py {arm|done|blocked|question|status}. "
        "A status summary is NOT a stop: if work remains and nothing blocks you, KEEP WORKING in "
        "the same turn. CURRENT STATE: " + state
    )
    print(json.dumps({"additionalContext": msg}))


if __name__ == "__main__":
    main()
