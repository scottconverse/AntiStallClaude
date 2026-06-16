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
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "antistall-gate.py"


def run_gate(project_dir: pathlib.Path, payload: str = "{}", env_extra: dict | None = None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [sys.executable, str(GATE)], input=payload, text=True, capture_output=True, env=env,
    )
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        proj = pathlib.Path(td)
        claude = proj / ".claude"
        claude.mkdir()
        flag = claude / "sprint-gate.json"
        ticket = claude / "sprint-stop-ticket.json"
        count = claude / ".antistall-block-count"

        # A — sprint NOT armed -> silent allow
        rc, out, _ = run_gate(proj)
        if not (rc == 0 and out.strip() == ""):
            failures.append(f"A (not armed, silent): rc={rc} out={out!r}")

        # B — armed + no ticket -> block, count -> 1
        flag.write_text(json.dumps({"active": True, "note": "test"}), encoding="utf-8")
        rc, out, _ = run_gate(proj)
        if not (rc == 0 and '"decision": "block"' in out):
            failures.append(f"B (armed, no ticket -> block): rc={rc} out={out!r}")
        if count.exists() and count.read_text().strip() != "1":
            failures.append(f"B (block count): {count.read_text()!r}")

        # C — armed + fresh DONE ticket -> allow + consume the ticket + reset count
        ticket.write_text(json.dumps({"reason": "DONE", "detail": "x", "ts": time.time()}), encoding="utf-8")
        rc, out, err = run_gate(proj)
        if not (rc == 0 and out.strip() == "" and not ticket.exists() and "ALLOWED" in err):
            failures.append(f"C (DONE ticket allow+consume): rc={rc} out={out!r} err={err!r} ticket={ticket.exists()}")

        # C2 — a STALE ticket is ignored (still blocks)
        ticket.write_text(json.dumps({"reason": "DONE", "detail": "x", "ts": time.time() - 9999}), encoding="utf-8")
        _, out, _ = run_gate(proj, env_extra={"ANTISTALL_TICKET_MAX_AGE_S": "300"})
        if '"decision": "block"' not in out:
            failures.append(f"C2 (stale ticket ignored -> block): out={out!r}")

        # D — anti-loop cap escapes after CAP consecutive blocks
        if count.exists():
            count.unlink()
        last_err = ""
        for _ in range(3):
            _, _, last_err = run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "3"})
        if "anti-loop cap" not in last_err:
            failures.append(f"D (anti-loop escape at cap): err={last_err!r}")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("OK: anti-stall gate — silent / block / allow+consume / stale-ignored / anti-loop all pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
