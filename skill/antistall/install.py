#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""AntiStallClaude installer.

Copies the anti-stall hooks into a target project's PROJECT-LEVEL ``.claude/``
and merges the Stop + SessionStart wiring into ``.claude/settings.json``.

Project-level is deliberate: user-level (``~/.claude``) hooks do NOT fire in
Cowork's Code tab — only project-level hooks do. So the gate must live in the
project. See README.md / docs/MANUAL.md.

Usage:
    python3 install.py [TARGET_PROJECT_DIR]      # defaults to the current directory

Idempotent: re-running refreshes the hook scripts and never duplicates the
settings entries. The existing settings.json (if any) is backed up first.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import time

HOOK_FILES = (
    "antistall-gate.py",
    "antistall-gate.sh",
    "antistall-session-start.py",
    "antistall-session-start.sh",
    "antistall.py",
)
GATE_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/antistall-gate.sh'
SESSION_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/antistall-session-start.sh'


def _src_hooks() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "hooks"


def _has_cmd(entries: list, needle: str) -> bool:
    return any(
        needle in str(h.get("command", ""))
        for entry in entries
        for h in entry.get("hooks", [])
    )


def main(argv: list[str]) -> int:
    target = pathlib.Path(argv[1]).resolve() if len(argv) > 1 else pathlib.Path.cwd()
    if not target.is_dir():
        print(f"target project dir does not exist: {target}", file=sys.stderr)
        return 2

    claude = target / ".claude"
    hooks = claude / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)

    src = _src_hooks()
    for name in HOOK_FILES:
        shutil.copyfile(src / name, hooks / name)
        if name.endswith(".sh"):
            try:
                (hooks / name).chmod(0o755)
            except OSError:
                pass
    print(f"copied {len(HOOK_FILES)} hook scripts -> {hooks}")

    settings_path = claude / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        backup = settings_path.with_name(f"settings.json.bak-{int(time.time())}")
        shutil.copyfile(settings_path, backup)
        print(f"backed up existing settings.json -> {backup.name}")
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARNING: existing settings.json is not valid JSON; refusing to overwrite.",
                  file=sys.stderr)
            return 3

    hooks_block = settings.setdefault("hooks", {})
    stop = hooks_block.setdefault("Stop", [])
    session = hooks_block.setdefault("SessionStart", [])
    if not _has_cmd(stop, "antistall-gate.sh"):
        stop.append({"hooks": [{"type": "command", "command": GATE_CMD}]})
        print("wired Stop hook")
    else:
        print("Stop hook already wired (skipped)")
    if not _has_cmd(session, "antistall-session-start.sh"):
        session.append({"hooks": [{"type": "command", "command": SESSION_CMD}]})
        print("wired SessionStart hook")
    else:
        print("SessionStart hook already wired (skipped)")

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {settings_path}")

    print(
        "\nDone. Next:\n"
        "  1. RESTART the Code tab / Claude Code (hooks load at session start).\n"
        "  2. Arm a sprint when you start autonomous work:\n"
        "       python3 .claude/hooks/antistall.py arm \"<the sprint goal>\"\n"
        "  3. To stop legitimately, write a ticket:\n"
        "       python3 .claude/hooks/antistall.py done|blocked|question \"<why>\"\n"
        "  4. Verify the gate fires (see docs/MANUAL.md \"Behavioral test\")."
    )
    if os.name == "nt":
        print(
            "\nWindows note: hooks run python3 — ensure `python3` resolves on PATH "
            "(the Python launcher / Microsoft Store shim both work)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
