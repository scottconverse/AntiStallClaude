#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Self-contained test of the anti-stall gate + CLI authority model (v0.3.0).

Spawns the real hooks/antistall-gate.py and hooks/antistall.py as subprocesses
(exactly as the harness / a human would) against throwaway dirs, and asserts the
v0.3.0 guarantees — most importantly that the AGENT can never stop or disarm a
sprint, and only a human passphrase (`release`) turns it off.

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

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "antistall-gate.py"
CLI = ROOT / "hooks" / "antistall.py"
SKILL_GATE = ROOT / "skill" / "antistall" / "hooks" / "antistall-gate.py"
SKILL_CLI = ROOT / "skill" / "antistall" / "hooks" / "antistall.py"
WRAPPER = ROOT / "hooks" / "antistall-gate.sh"


def run_gate(project_dir, payload="{}", env_extra=None, gate=None, set_project_dir=True):
    env = dict(os.environ)
    if set_project_dir:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    else:
        env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([sys.executable, str(gate or GATE)], input=payload,
                       text=True, capture_output=True, env=env)
    return p.returncode, p.stdout, p.stderr


def run_cli(args, project_dir, cfg_dir, sid=None, env_extra=None):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    env["CLAUDE_CONFIG_DIR"] = str(cfg_dir)
    if sid:
        env["CLAUDE_CODE_SESSION_ID"] = sid
    else:
        env.pop("CLAUDE_CODE_SESSION_ID", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([sys.executable, str(CLI), *args], input="",
                       text=True, capture_output=True, env=env)
    return p.returncode, p.stdout, p.stderr


def is_block(stdout):
    return '"decision": "block"' in stdout


def main() -> int:
    failures: list[str] = []

    def expect(name, cond, detail=""):
        if not cond:
            failures.append(f"{name}: {detail}")

    # ============================ GATE behavior ============================
    with tempfile.TemporaryDirectory() as td:
        proj = pathlib.Path(td)
        claude = proj / ".claude"
        claude.mkdir()
        flag = claude / "sprint-gate.json"
        ticket = claude / "sprint-stop-ticket.json"
        count = claude / ".antistall-block-count"

        # A — not armed -> silent allow
        rc, out, _ = run_gate(proj)
        expect("A (not armed, silent)", rc == 0 and out.strip() == "", f"rc={rc} out={out!r}")

        # B — armed + no ticket -> block, counter == 1
        flag.write_text(json.dumps({"active": True, "note": "t", "owner": None}), encoding="utf-8")
        rc, out, _ = run_gate(proj)
        expect("B (armed -> block)", rc == 0 and is_block(out), f"rc={rc} out={out!r}")
        expect("B (counter==1)", count.exists() and count.read_text().strip() == "1", "counter wrong")
        count.unlink(missing_ok=True)

        # C — THE FIX: an agent-written DONE/BLOCKED/QUESTION ticket is IGNORED. The
        # gate still blocks AND never clears the gate file (stays armed).
        for reason in ("DONE", "BLOCKED", "QUESTION"):
            ticket.write_text(json.dumps({"reason": reason, "detail": "x", "ts": 9e9}), encoding="utf-8")
            _, out, _ = run_gate(proj)
            expect(f"C-{reason} (ticket ignored -> still block)", is_block(out), f"out={out!r}")
            expect(f"C-{reason} (gate stays armed)", flag.exists(), "gate file vanished")
            count.unlink(missing_ok=True)
        ticket.unlink(missing_ok=True)

        # E — THE FIX: stop_hook_active=true must STILL block (no 1-nudge escape).
        count.write_text("1", encoding="utf-8")
        rc, out, _ = run_gate(proj, payload=json.dumps({"stop_hook_active": True}))
        expect("E (stop_hook_active still blocks)", is_block(out), f"rc={rc} out={out!r}")
        count.unlink(missing_ok=True)

        # D/H — token-burn cap PAUSES (allow) but NEVER disarms. CAP=3: n=1 block,
        # n=2 block, n=3 -> pause(allow). Gate file remains after the pause.
        count.unlink(missing_ok=True)
        outs = []
        for _ in range(3):
            _, o, e = run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "3"})
            outs.append((o, e))
        expect("D (blocks before cap)", is_block(outs[0][0]) and is_block(outs[1][0]), f"{outs}")
        expect("D (pause at cap)", outs[2][0].strip() == "" and "cap" in outs[2][1].lower(), f"{outs[2]}")
        expect("D (STILL ARMED after pause)", flag.exists(), "cap pause must NOT disarm")
        count.unlink(missing_ok=True)

        # D0 — CAP=0 means never auto-pause: many consecutive blocks, all block.
        allblock = all(is_block(run_gate(proj, env_extra={"ANTISTALL_BLOCK_CAP": "0"})[1])
                       for _ in range(5))
        expect("D0 (cap=0 never pauses)", allblock, "cap=0 should block forever")
        count.unlink(missing_ok=True)

        # F — fail-open paths yield at most a PAUSE; the gate is NEVER cleared.
        count.write_text("not-a-number", encoding="utf-8")
        rc, out, _ = run_gate(proj)
        expect("F (corrupt counter -> pause)", rc == 0 and out.strip() == "", f"out={out!r}")
        expect("F (still armed)", flag.exists(), "fail-open must not disarm")
        count.unlink(missing_ok=True)
        count.mkdir()
        rc, out, err = run_gate(proj)
        expect("F3 (unreadable counter -> pause)", rc == 0 and out.strip() == "" and flag.exists(),
               f"out={out!r} err={err!r}")
        count.rmdir()

        # I — per-session isolation: session-scoped gate + counter.
        flag.unlink(missing_ok=True)  # clear the project-wide gate from earlier sections
        sflag = claude / "sprint-gate-sessAAA.json"
        sflag.write_text(json.dumps({"active": True, "owner": "sessAAA"}), encoding="utf-8")
        _, outA, _ = run_gate(proj, payload=json.dumps({"session_id": "sessAAA"}))
        _, outB, _ = run_gate(proj, payload=json.dumps({"session_id": "sessBBB"}))
        expect("I (armed session blocks)", is_block(outA), f"A out={outA!r}")
        expect("I (other session silent)", outB.strip() == "", f"B out={outB!r}")
        expect("I (per-session counter)", (claude / ".antistall-block-count-sessAAA").exists(),
               "session counter missing")
        sflag.unlink(missing_ok=True)
        for p in claude.glob(".antistall-block-count*"):
            p.unlink()

        # J — owner gating on a legacy project-wide gate: only the owner is blocked.
        flag.write_text(json.dumps({"active": True, "owner": "sessOWNER"}), encoding="utf-8")
        _, outOwner, _ = run_gate(proj, payload=json.dumps({"session_id": "sessOWNER"}))
        _, outOther, _ = run_gate(proj, payload=json.dumps({"session_id": "sessX"}))
        expect("J (owner blocked)", is_block(outOwner), f"out={outOwner!r}")
        expect("J (non-owner silent)", outOther.strip() == "", f"out={outOther!r}")
        flag.unlink(missing_ok=True)
        for p in claude.glob(".antistall-block-count*"):
            p.unlink()

    # ============================ CLI authority ============================
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as cfgd:
        proj = pathlib.Path(td)
        (proj / ".claude").mkdir()
        cfg = pathlib.Path(cfgd)
        sid = "sessCLI"
        gatef = proj / ".claude" / f"sprint-gate-{sid}.json"

        # K1 — arm REFUSED when no release secret exists.
        rc, _, err = run_cli(["arm", "goal"], proj, cfg, sid=sid)
        expect("K1 (arm refused w/o secret)", rc == 5 and not gatef.exists(), f"rc={rc} err={err!r}")

        # K2 — set release secret (non-interactive via env), then arm succeeds.
        rc, _, _ = run_cli(["set-release-secret"], proj, cfg, sid=sid, env_extra={"ANTISTALL_RELEASE": "s3cret"})
        expect("K2 (secret set)", rc == 0 and (cfg / "antistall-release.hash").exists(), f"rc={rc}")
        rc, _, _ = run_cli(["arm", "build all"], proj, cfg, sid=sid)
        expect("K2 (arm ok)", rc == 0 and gatef.exists(), f"rc={rc}")

        # K3 — agent 'done'/'blocked'/'question' are REMOVED: error, gate intact.
        for c in ("done", "blocked", "question"):
            rc, _, err = run_cli([c, "x"], proj, cfg, sid=sid)
            expect(f"K3 ({c} refused)", rc == 7 and gatef.exists(), f"rc={rc} armed={gatef.exists()}")

        # K4 — release with WRONG passphrase: refused, gate intact.
        rc, _, _ = run_cli(["release"], proj, cfg, sid=sid, env_extra={"ANTISTALL_RELEASE": "wrong"})
        expect("K4 (wrong pass refused)", rc == 6 and gatef.exists(), f"rc={rc} armed={gatef.exists()}")

        # K5 — request: notifies, does NOT disarm.
        rc, _, _ = run_cli(["request", "stuck"], proj, cfg, sid=sid)
        expect("K5 (request keeps armed)", rc == 0 and gatef.exists(), f"rc={rc} armed={gatef.exists()}")

        # K6 — release with RIGHT passphrase: the ONLY disarm.
        rc, _, _ = run_cli(["release"], proj, cfg, sid=sid, env_extra={"ANTISTALL_RELEASE": "s3cret"})
        expect("K6 (correct pass disarms)", rc == 0 and not gatef.exists(), f"rc={rc} armed={gatef.exists()}")

    # ============================ packaging / fallback ============================
    # M — CLAUDE_PROJECT_DIR unset: self-locating fallback still blocks.
    with tempfile.TemporaryDirectory() as td2:
        proj2 = pathlib.Path(td2)
        hooks2 = proj2 / ".claude" / "hooks"
        hooks2.mkdir(parents=True)
        gate2 = hooks2 / "antistall-gate.py"
        shutil.copyfile(GATE, gate2)
        (proj2 / ".claude" / "sprint-gate.json").write_text(json.dumps({"active": True}), encoding="utf-8")
        rc, out, _ = run_gate(proj2, gate=gate2, set_project_dir=False)
        expect("M (env-unset fallback blocks)", rc == 0 and is_block(out), f"rc={rc} out={out!r}")

    # N — shipped repo copies must be byte-identical.
    expect("N (gate copies identical)", GATE.read_bytes() == SKILL_GATE.read_bytes(),
           "hooks/ and skill/antistall/hooks/ antistall-gate.py differ")
    expect("N (cli copies identical)", CLI.read_bytes() == SKILL_CLI.read_bytes(),
           "hooks/ and skill/antistall/hooks/ antistall.py differ")

    # O — .sh wrapper smoke.
    bash = shutil.which("bash")
    if bash and shutil.which("python3") and WRAPPER.exists():
        with tempfile.TemporaryDirectory() as td3:
            proj3 = pathlib.Path(td3)
            (proj3 / ".claude").mkdir()
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(proj3))
            env.pop("CLAUDE_CODE_SESSION_ID", None)
            p = subprocess.run([bash, str(WRAPPER)], input="{}", text=True, capture_output=True, env=env)
            expect("O (.sh wrapper silent when unarmed)",
                   p.returncode == 0 and p.stdout.strip() == "", f"rc={p.returncode} out={p.stdout!r}")
    else:
        print("  (skipped O: bash/python3 wrapper smoke — not available here)")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("OK (v0.3.0): not-armed-silent / armed-blocks / TICKETS-IGNORED / stop_hook_active-still-blocks / "
          "cap-pauses-but-stays-armed / cap=0-holds / fail-open-never-disarms / per-session / owner-gating / "
          "arm-needs-secret / agent-cannot-disarm / wrong-pass-refused / human-release-only / fallback / "
          "copy-identity / wrapper-smoke — all pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
