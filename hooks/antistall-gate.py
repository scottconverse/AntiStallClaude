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
#   - stop_hook_active == true     -> exit 0 (LOOP GUARD; see below) — ALWAYS allow
#   - active + fresh valid ticket  -> consume ticket, reset counter, exit 0 (allow stop)
#   - active + no/stale ticket     -> {"decision":"block", reason:...}, exit 0 (forced to continue)
#   - any counter anomaly          -> exit 0 (FAIL OPEN — a loop guard must never loop)
#
# ---------------------------------------------------------------------------
# TERMINATION SAFETY (why this hook can NEVER burn tokens in an endless loop)
# ---------------------------------------------------------------------------
# A Stop hook that emits {"decision":"block"} to force the agent to keep going
# can, if it re-blocks while the agent is ALREADY continuing because of a prior
# block, create an unbounded `block -> continue -> block` loop: the session
# never goes idle and tokens burn without limit. This is the single most
# dangerous failure mode of any blocking Stop hook, and earlier versions of this
# file had it (the only brake was a consecutive-block counter that reset to 0 on
# any read error, so two agents sharing the counter file — or any mid-write race
# — pinned it near 1 and the cap was never reached).
#
# Two INDEPENDENT guarantees now prevent it:
#   (1) PRIMARY — honor `stop_hook_active`. The agent harness sets this field to
#       true on a Stop that is itself the result of a previous Stop-hook block.
#       When true, ALWAYS allow the stop. This bound depends on NO shared mutable
#       file, so it is immune to the cross-agent counter race. It caps the gate
#       at one nudge per continuation chain — the gate still stops a drift-stop,
#       it just cannot loop on it.
#   (2) SECONDARY — the consecutive-block counter now FAILS OPEN. For any harness
#       that does not surface `stop_hook_active`, the counter still caps the
#       loop; and crucially, ANY uncertainty about the counter (unreadable,
#       unparseable, or unwritable) ALLOWS the stop instead of blocking again. A
#       loop guard that can itself loop is worse than no guard.
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


def _safe_unlink(p: pathlib.Path) -> None:
    try:
        p.unlink()
    except Exception:
        pass


def _allow(msg: str) -> None:
    """Permit the stop: write a one-line stderr note and exit 0 (no block)."""
    sys.stderr.write(f"{TAG} {msg}\n")
    sys.exit(0)


def main() -> None:
    # Drain stdin and parse the Stop payload. We need `stop_hook_active` from it,
    # but a framing change must never wedge the session: an unparseable payload
    # yields {} and we fall through to the flag check (fail-open).
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    claude_dir = _claude_dir()
    flag = _read_json(claude_dir / "sprint-gate.json")
    if not (isinstance(flag, dict) and flag.get("active")):
        sys.exit(0)  # no active sprint -> the gate is silent

    cap = _int_env("ANTISTALL_BLOCK_CAP", 6)
    max_age = _int_env("ANTISTALL_TICKET_MAX_AGE_S", 300)
    count_path = claude_dir / ".antistall-block-count"

    # (1) PRIMARY LOOP GUARD — never block a stop that is itself the product of a
    # prior Stop-hook block. Race-proof: depends on no shared mutable state.
    if payload.get("stop_hook_active"):
        _safe_unlink(count_path)
        _allow(
            "stop ALLOWED (loop guard: stop_hook_active). The gate nudges a "
            "drift-stop at most once per continuation chain; it never loops."
        )

    # Single-use ticket: consume whether or not it is valid; honor it if fresh.
    ticket_path = claude_dir / "sprint-stop-ticket.json"
    ticket = _read_json(ticket_path)
    if isinstance(ticket, dict):
        _safe_unlink(ticket_path)
        reason = str(ticket.get("reason", "")).upper()
        try:
            age = time.time() - float(ticket.get("ts", 0))
        except Exception:
            age = 1e9
        if reason in VALID_REASONS and age < max_age:
            _safe_unlink(count_path)
            _allow(f"stop ALLOWED: {reason} — {ticket.get('detail', '')}")

    # (2) SECONDARY LOOP GUARD — consecutive-block counter that FAILS OPEN. Any
    # uncertainty about the counter allows the stop; it must never cause a loop.
    try:
        current = count_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        current = "0"
    except Exception:
        # Can't read it -> can't prove we haven't already looped -> allow.
        _allow("stop ALLOWED (loop guard: block-counter unreadable; failing open).")
        return
    try:
        n = int(current) + 1
    except Exception:
        # Corrupt counter (e.g. a partial concurrent write) -> allow + reset.
        _safe_unlink(count_path)
        _allow("stop ALLOWED (loop guard: block-counter corrupt; failing open).")
        return
    if n >= cap:
        _safe_unlink(count_path)
        _allow(
            f"anti-loop cap ({cap}) reached — allowing the stop. Investigate why no "
            f"DONE/BLOCKED/QUESTION ticket was written for {cap} turns; the sprint flag "
            f"may be stale (clear .claude/sprint-gate.json)."
        )
        return
    try:
        count_path.write_text(str(n), encoding="utf-8")
    except Exception:
        # Can't persist progress -> the next read can't advance -> would loop. Allow.
        _allow("stop ALLOWED (loop guard: cannot persist block-counter; failing open).")
        return

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
