#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Self-contained test of the anti-stall Stop hook — no harness needed.

Spawns the real hooks/antistall-gate.py as a subprocess (exactly as the harness
would) against a throwaway project dir, and asserts each behavior.

Run: python3 tests/test_gate.py   (exit 0 = pass)
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "antistall-gate.py"
SKILL_GATE = ROOT / "skill" / "antistall" / "hooks" / "antistall-gate.py"
WRAPPER = ROOT / "hooks" / "antistall-gate.sh"


def run_gate(project_dir: pathlib.Path, payload: str = "{}", env_extra: dict | None = None,
             gate: pathlib.Path | None = None, set_project_dir: bool = True):
    env = dict(os.environ)
    if set_project_dir:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [sys.executable, str(gate or GATE)], input=payload, text=True, capture_output=True, env=env,
    )
    return p.returncode, p.stdout, p.stderr


def is_block(stdout: str) -> bool:
    return '"decision": "block"' in stdout


def main() -> int:
    failures: list[str] = []

    def expect(name: str, cond: bool, detail: str = ""):
        if not cond:
            failures.append(f"{name}: {detail}")

    with tempfile.TemporaryDirectory() as td:
        proj = pathlib.Path(td)
        claude = proj / ".claude"
        claude.mkdir()
        flag = claude / "sprint-gate.json"
        ticket = claude / "sprint-stop-ticket.json"
        count = claude / ".antistall-block-count"  # base name (payload has no session_id)

        # A — sprint NOT armed -> silent allow
        rc, out, _ = run_gate(proj)
        expect("A (not armed, silent)", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")

        # B — armed + no ticket -> block, and the counter is persisted to exactly 1
        flag.write_text(json.dumps({"active": True, "note": "test"}), encoding="utf-8")
        rc, out, _ = run_gate(proj)
        expect("B (armed, no ticket -> block)", rc == 0 and is_block(out), f"rc={rc} out={out!r}")
        expect("B (counter written)", count.exists(), "counter file missing after a block")
        if count.exists():
            expect("B (counter == 1)", count.read_text().strip() == "1", f"{count.read_text()!r}")
        count.unlink(missing_ok=True)

        # C / C3 / C4 — fresh DONE/BLOCKED/QUESTION ticket -> allow + consume + reset
        for reason in ("DONE", "BLOCKED", "QUESTION"):
            count.write_text("2", encoding="utf-8")
            ticket.write_text(json.dumps({"reason": reason, "detail": "x", "ts": time.time()}), encoding="utf-8")
            rc, out, err = run_gate(proj)
            expect(f"C-{reason} (allow+consume)",
                   rc == 0 and out.strip() == "" and not ticket.exists() and "ALLOWED" in err,
                   f"rc={rc} out={out!r} err={err!r} ticket={ticket.exists()}")
            expect(f"C-{reason} (counter reset)", not count.exists(), "counter not reset on valid ticket")

        # C2 — a STALE ticket is ignored (still blocks) and is consumed on sight
        ticket.write_text(json.dumps({"reason": "DONE", "detail": "x", "ts": time.time() - 9999}), encoding="utf-8")
        _, out, _ = run_gate(proj, env_extra={"ANTISTALL_TICKET_MAX_AGE_S": "300"})
        expect("C2 (stale ticket -> block)", is_block(out), f"out={out!r}")
        expect("C2 (stale ticket consumed)", not ticket.exists(), "stale ticket not consumed")
        count.unlink(missing_ok=True)

        # C5 — a FUTURE-dated ticket (negative age) is treated as stale, not fresh
        ticket.write_text(json.dumps({"reason": "DONE", "detail": "x", "ts": time.time() + 9999}), encoding="utf-8")
        _, out, _ = run_gate(proj)
        expect("C5 (future-dated ticket -> block)", is_block(out), f"out={out!r}")
        count.unlink(missing_ok=True)

        # D — anti-loop cap escapes after CAP consecutive blocks
        count.unlink(missing_ok=True)
        last_err = ""
        for _ in range(3):
            _, _, last_err = run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "3"})
        expect("D (anti-loop escape at cap)", "anti-loop cap" in last_err, f"err={last_err!r}")

        # E — LOOP GUARD: stop_hook_active=true ALWAYS allows, even armed + no
        # ticket + a stuck non-zero counter (the exact state that looped before),
        # and it consumes any lingering ticket.
        count.write_text("1", encoding="utf-8")
        ticket.write_text(json.dumps({"reason": "DONE", "detail": "x", "ts": time.time()}), encoding="utf-8")
        rc, out, err = run_gate(proj, payload=json.dumps({"stop_hook_active": True}))
        expect("E (stop_hook_active -> allow)",
               rc == 0 and out.strip() == "" and "loop guard" in err.lower(), f"rc={rc} out={out!r} err={err!r}")
        expect("E (lingering ticket consumed)", not ticket.exists(), "ticket survived loop-guard allow")
        count.unlink(missing_ok=True)

        # F — FAIL OPEN: a corrupt counter allows the stop, never blocks.
        count.write_text("not-a-number", encoding="utf-8")
        rc, out, _ = run_gate(proj, payload=json.dumps({"stop_hook_active": False}))
        expect("F (corrupt counter -> fail open)", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
        count.unlink(missing_ok=True)

        # F2 — FAIL OPEN: an EMPTY counter file also allows (strips to "" -> int raises).
        count.write_text("   ", encoding="utf-8")
        rc, out, _ = run_gate(proj, payload=json.dumps({"stop_hook_active": False}))
        expect("F2 (empty counter -> fail open)", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")
        count.unlink(missing_ok=True)

        # F3 — FAIL OPEN: an UNREADABLE counter (a directory in its place) allows.
        count.mkdir()
        rc, out, err = run_gate(proj, payload=json.dumps({"stop_hook_active": False}))
        expect("F3 (unreadable counter -> fail open)",
               rc == 0 and out.strip() == "" and "failing open" in err.lower(), f"rc={rc} out={out!r} err={err!r}")
        count.rmdir()

        # F4 — FAIL OPEN: an UNWRITABLE counter (read-only file) allows. The read
        # returns "0", n becomes 1, the write fails, and the gate must still allow.
        count.write_text("0", encoding="utf-8")
        os.chmod(count, stat.S_IREAD)
        rc, out, err = run_gate(proj, payload=json.dumps({"stop_hook_active": False}))
        expect("F4 (unwritable counter -> fail open)",
               rc == 0 and out.strip() == "" and "failing open" in err.lower(), f"rc={rc} out={out!r} err={err!r}")
        os.chmod(count, stat.S_IWRITE | stat.S_IREAD)
        count.unlink(missing_ok=True)

        # G — BOUNDEDNESS: simulate the real harness auto-continue loop. The first
        # stop is blocked; the harness then continues *because of* that block, so the
        # next Stop carries stop_hook_active=true and MUST be allowed. Terminates in
        # at most one block. If this ever blocks twice, the token loop has regressed.
        count.unlink(missing_ok=True)
        ticket.unlink(missing_ok=True)
        blocks, sha = 0, False
        for _ in range(50):
            _, out, _ = run_gate(proj, payload=json.dumps({"stop_hook_active": sha}))
            if is_block(out):
                blocks += 1
                sha = True
            else:
                break
        expect("G (autonomous loop <=1 block)", blocks <= 1, f"blocked {blocks}x")

        # H — CAP BOUNDARY pinned exactly: with CAP=3, count 1->block(n=2), count 2->allow(n=3).
        count.write_text("1", encoding="utf-8")
        _, out, _ = run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "3"})
        expect("H (below cap -> block)", is_block(out), f"out={out!r}")
        count.write_text("2", encoding="utf-8")
        _, out, _ = run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "3"})
        expect("H (at cap -> allow)", out.strip() == "", f"out={out!r}")
        count.unlink(missing_ok=True)

        # I — PER-SESSION ISOLATION: two distinct session_ids get distinct counter
        # files, so the cross-agent race is structurally impossible (no shared file).
        run_gate(proj, payload=json.dumps({"session_id": "sessAAA"}))
        run_gate(proj, payload=json.dumps({"session_id": "sessBBB"}))
        ca = claude / ".antistall-block-count-sessAAA"
        cb = claude / ".antistall-block-count-sessBBB"
        expect("I (per-session counter A)", ca.exists() and ca.read_text().strip() == "1", "A counter wrong")
        expect("I (per-session counter B)", cb.exists() and cb.read_text().strip() == "1", "B counter wrong")
        expect("I (no shared base file)", not count.exists(), "base counter unexpectedly written")
        ca.unlink(missing_ok=True)
        cb.unlink(missing_ok=True)

    # M — CLAUDE_PROJECT_DIR UNSET: the self-locating fallback (parents[1]) must
    # still find the sprint flag and BLOCK when the gate sits at <proj>/.claude/hooks/.
    with tempfile.TemporaryDirectory() as td2:
        proj2 = pathlib.Path(td2)
        hooks2 = proj2 / ".claude" / "hooks"
        hooks2.mkdir(parents=True)
        gate2 = hooks2 / "antistall-gate.py"
        shutil.copyfile(GATE, gate2)
        (proj2 / ".claude" / "sprint-gate.json").write_text(json.dumps({"active": True}), encoding="utf-8")
        rc, out, _ = run_gate(proj2, gate=gate2, set_project_dir=False)
        expect("M (env-unset fallback still blocks)", rc == 0 and is_block(out), f"rc={rc} out={out!r}")

    # N — the two shipped repo copies must be byte-identical.
    expect("N (repo copies byte-identical)", GATE.read_bytes() == SKILL_GATE.read_bytes(),
           "hooks/ and skill/antistall/hooks/ copies differ")

    # O — .sh wrapper smoke (skips cleanly when bash or python3 are unavailable).
    bash = shutil.which("bash")
    py3 = shutil.which("python3")
    if bash and py3 and WRAPPER.exists():
        with tempfile.TemporaryDirectory() as td3:
            proj3 = pathlib.Path(td3)
            (proj3 / ".claude").mkdir()
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj3))
            p = subprocess.run([bash, str(WRAPPER)], input="{}", text=True, capture_output=True, env=env)
            expect("O (.sh wrapper not-armed -> silent allow)",
                   p.returncode == 0 and p.stdout.strip() == "", f"rc={p.returncode} out={p.stdout!r}")
    else:
        print("  (skipped O: bash/python3 wrapper smoke — not available here)")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print(
        "OK: anti-stall gate — silent / block / allow+consume / stale / future-dated / anti-loop cap / "
        "cap-boundary / stop_hook_active loop-guard / fail-open (corrupt/empty/unreadable/unwritable) / "
        "bounded-loop / per-session isolation / env-unset fallback / copy-identity / wrapper-smoke all pass"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
