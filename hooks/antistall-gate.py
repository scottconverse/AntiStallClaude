#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# AntiStallClaude — anti-stall Stop hook.
#
# Blocks the agent from ending a turn while an autonomous sprint is ACTIVE
# unless a fresh, single-use stop-ticket declares why the stop is legitimate
# (DONE / BLOCKED / QUESTION). This is the harness-enforced cure for the
# "announce-then-halt" / silent drift-stop failure: a CLAUDE.md or memory note
# is advice the model can rationalize past; this hook is a separate process the
# harness runs on EVERY Stop event regardless of what the model "remembers".
#
# State files (all in <project>/.claude/):
#   sprint-gate.json          {"active": true, "note": "..."}   gate armed when active
#   sprint-stop-ticket.json   {"reason":"DONE|BLOCKED|QUESTION","detail":"...","ts":<epoch>}
#   .antistall-block-count    integer, consecutive blocks (anti-loop counter)
#
# Behavior:
#   - sprint NOT active            -> exit 0 (silent; normal conversation ungated)
#   - active + fresh valid ticket  -> consume ticket, reset counter, exit 0 (allow stop)
#   - active + no/stale ticket     -> {"decision":"block", reason:...}, exit 0 (forced to continue)
#   - anti-loop: after CAP consecutive blocks, allow the stop + log loudly so a
#     genuine dead-end can always escape (it must never trap the session forever).
#
# Stop hooks signal "keep going" via a JSON {"decision":"block"} on stdout,
# NOT via exit code 2 (that is the PreToolUse convention). Exit 0 either way.
#
# Env overrides (optional):
#   ANTISTALL_BLOCK_CAP            consecutive-block escape hatch (default 6)
#   ANTISTALL_TICKET_MAX_AGE_S     a stop-ticket older than this is stale (default 300)

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

TAG = "[ANTI-STALL]"
VALID_REASONS = {"DONE", "BLOCKED", "QUESTION"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


def _claude_dir() -> pathlib.Path:
    # Robust whether or not CLAUDE_PROJECT_DIR is set at hook runtime: this file
    # lives at <project>/.claude/hooks/antistall-gate.py, so parents[1] == .claude.
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        d = pathlib.Path(env) / ".claude"
        if d.is_dir():
            return d
    return pathlib.Path(__file__).resolve().parents[1]


def _read_json(p: pathlib.Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> None:
    try:
        json.load(sys.stdin)  # drain the payload; we gate on the flag, not its fields
    except Exception:
        pass  # fail-open on an unparseable Stop payload — never wedge on a framing change

    claude_dir = _claude_dir()
    flag = _read_json(claude_dir / "sprint-gate.json")
    if not (isinstance(flag, dict) and flag.get("active")):
        sys.exit(0)  # no active sprint -> the gate is silent

    cap = _int_env("ANTISTALL_BLOCK_CAP", 6)
    max_age = _int_env("ANTISTALL_TICKET_MAX_AGE_S", 300)
    count_path = claude_dir / ".antistall-block-count"

    ticket_path = claude_dir / "sprint-stop-ticket.json"
    ticket = _read_json(ticket_path)
    if isinstance(ticket, dict):
        try:
            ticket_path.unlink()  # single-use: consume whether or not it is valid
        except Exception:
            pass
        reason = str(ticket.get("reason", "")).upper()
        try:
            age = time.time() - float(ticket.get("ts", 0))
        except Exception:
            age = 1e9
        if reason in VALID_REASONS and age < max_age:
            try:
                count_path.unlink()
            except Exception:
                pass
            sys.stderr.write(f"{TAG} stop ALLOWED: {reason} — {ticket.get('detail', '')}\n")
            sys.exit(0)

    # No valid ticket: block, unless the anti-loop cap is hit.
    try:
        n = int(count_path.read_text(encoding="utf-8").strip())
    except Exception:
        n = 0
    n += 1
    if n >= cap:
        try:
            count_path.unlink()
        except Exception:
            pass
        sys.stderr.write(
            f"{TAG} anti-loop cap ({cap}) reached — allowing the stop. Investigate why no "
            f"DONE/BLOCKED/QUESTION ticket was written for {cap} turns; the sprint flag may be "
            f"stale (clear .claude/sprint-gate.json).\n"
        )
        sys.exit(0)
    try:
        count_path.write_text(str(n), encoding="utf-8")
    except Exception:
        pass

    reason_msg = (
        f"{TAG} A sprint is ACTIVE and you are ending the turn with no valid stop-ticket. "
        f"KEEP WORKING — finish the next concrete step. To stop legitimately, write "
        f'{claude_dir}/sprint-stop-ticket.json as '
        f'{{"reason":"DONE|BLOCKED|QUESTION","detail":"<why>","ts":<epoch seconds>}} and THEN '
        f"end the turn (DONE = whole queue done + clear sprint-gate.json; BLOCKED = a decision "
        f"only the human can make halts ALL remaining work; QUESTION = you asked the human and "
        f"need the answer). Block {n}/{cap}."
    )
    print(json.dumps({"decision": "block", "reason": reason_msg}))
    sys.exit(0)


if __name__ == "__main__":
    main()
