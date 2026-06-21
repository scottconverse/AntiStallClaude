#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# AntiStallClaude — operator helper.
#
# Usage (run from the project root; resolves <project>/.claude/ from this file):
#   python3 .claude/hooks/antistall.py arm  "<short note, e.g. the sprint goal>"
#   python3 .claude/hooks/antistall.py done "<why the whole queue is finished>"
#   python3 .claude/hooks/antistall.py blocked  "<the human-only decision needed>"
#   python3 .claude/hooks/antistall.py question "<what was asked of the human>"
#   python3 .claude/hooks/antistall.py status
#
# arm        -> writes sprint-gate.json {"active":true} (gate now blocks drift-stops)
# done       -> writes a DONE stop-ticket AND clears sprint-gate.json (sprint over)
# blocked    -> writes a BLOCKED stop-ticket (sprint stays armed; resume on the human's call)
# question   -> writes a QUESTION stop-ticket (sprint stays armed)
# status     -> prints whether a sprint is armed + any pending ticket
#
# A ticket authorizes exactly ONE turn-end; the Stop hook consumes it.

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time


def _resolve_claude() -> pathlib.Path:
    # Match the gate/session-start resolution so this CLI targets the SAME state
    # the Stop hook reads — important for a global (~/.claude) install, where this
    # script lives outside the project. Priority: CLAUDE_PROJECT_DIR (set by the
    # harness, incl. Cowork) -> cwd/.claude -> this file's parent (project copy).
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (pathlib.Path(env) / ".claude").is_dir():
        return pathlib.Path(env) / ".claude"
    cwd_claude = pathlib.Path.cwd() / ".claude"
    if cwd_claude.is_dir():
        return cwd_claude
    return pathlib.Path(__file__).resolve().parents[1]


CLAUDE = _resolve_claude()


def _safe_sid(sid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:80]


def _session_id():
    # The gate keys off the Stop payload's session_id; the harness exposes the SAME
    # id to commands as CLAUDE_CODE_SESSION_ID, so arming/ticketing here targets the
    # exact per-session state the gate reads. Falls back to legacy project-wide files
    # when no session id is available (older runtimes / manual use outside a session).
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    return sid if sid and sid.strip() else None


SID = _session_id()
FLAG = CLAUDE / (f"sprint-gate-{_safe_sid(SID)}.json" if SID else "sprint-gate.json")
TICKET = CLAUDE / (
    f"sprint-stop-ticket-{_safe_sid(SID)}.json" if SID else "sprint-stop-ticket.json"
)


def _clear_counts() -> None:
    # Clear only THIS session's consecutive-block counter(s); never touch another
    # session's loop-guard state.
    pat = f".antistall-block-count-{_safe_sid(SID)}*" if SID else ".antistall-block-count*"
    for p in CLAUDE.glob(pat):
        try:
            p.unlink()
        except Exception:
            pass


def _write_ticket(reason: str, detail: str) -> None:
    TICKET.write_text(
        json.dumps({"reason": reason, "detail": detail, "ts": time.time()}),
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    cmd = argv[1].lower() if len(argv) > 1 else "status"
    detail = " ".join(argv[2:]) if len(argv) > 2 else ""

    if cmd == "arm":
        FLAG.write_text(
            json.dumps({"active": True, "note": detail, "owner": SID}), encoding="utf-8"
        )
        try:
            TICKET.unlink()
        except Exception:
            pass
        _clear_counts()
        print(
            f"armed: sprint gate ACTIVE — {detail or '(no note)'}\n"
            "  (enforced only if the Stop hook is installed and you've restarted the "
            "session — prove it with the MANUAL §7 behavioral test)"
        )
    elif cmd == "done":
        _write_ticket("DONE", detail)
        try:
            FLAG.unlink()
        except Exception:
            pass
        print(f"DONE ticket written + sprint disarmed — {detail}")
    elif cmd in ("blocked", "question"):
        _write_ticket(cmd.upper(), detail)
        print(f"{cmd.upper()} ticket written (sprint stays armed) — {detail}")
    elif cmd == "status":
        try:
            flag = json.loads(FLAG.read_text(encoding="utf-8"))
            armed, note = bool(flag.get("active")), flag.get("note", "")
        except Exception:
            armed, note = False, ""
        try:
            t = json.loads(TICKET.read_text(encoding="utf-8"))
            age = max(0, int(time.time() - float(t.get("ts", 0))))
            ticket = f"{t.get('reason', '?')} ({age}s ago) — {t.get('detail', '')}"
        except Exception:
            ticket = "none"
        state = "ARMED" if armed else "disarmed"
        scope = f"session {SID[:8]}…" if SID else "project-wide (no session id)"
        line = f"Sprint gate [{scope}]: {state}."
        if note:
            line += f" Note: {note}."
        line += f" Pending stop-ticket: {ticket}"
        # Surface a legacy/other-owner project-wide gate so cross-session state is visible.
        if not armed:
            legacy = CLAUDE / "sprint-gate.json"
            try:
                lg = json.loads(legacy.read_text(encoding="utf-8"))
                if lg.get("active"):
                    owner = lg.get("owner")
                    who = "unowned/all sessions" if owner is None else (
                        "this session" if owner == SID else f"another session ({str(owner)[:8]}…)"
                    )
                    line += f" [legacy {legacy.name} ARMED, owner: {who}]"
            except Exception:
                pass
        print(line)
    else:
        print(f"unknown command: {cmd!r} (use arm|done|blocked|question|status)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
