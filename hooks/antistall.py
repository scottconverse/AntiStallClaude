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
import pathlib
import sys
import time

CLAUDE = pathlib.Path(__file__).resolve().parents[1]
FLAG = CLAUDE / "sprint-gate.json"
TICKET = CLAUDE / "sprint-stop-ticket.json"


def _clear_counts() -> None:
    # Counters are per-session (.antistall-block-count-<sid>); clear them all.
    for p in CLAUDE.glob(".antistall-block-count*"):
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
        FLAG.write_text(json.dumps({"active": True, "note": detail}), encoding="utf-8")
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
        line = f"Sprint gate: {state}."
        if note:
            line += f" Note: {note}."
        line += f" Pending stop-ticket: {ticket}"
        print(line)
    else:
        print(f"unknown command: {cmd!r} (use arm|done|blocked|question|status)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
