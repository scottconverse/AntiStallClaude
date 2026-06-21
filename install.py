#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""AntiStallClaude installer.

Copies the anti-stall hooks into a target ``.claude/`` and merges the Stop +
SessionStart wiring into ``.claude/settings.json``.

Two scopes:

* PROJECT (default) — installs into ``<project>/.claude/``; hooks are wired with
  ``$CLAUDE_PROJECT_DIR`` and run via the ``.sh`` self-locating wrappers.
* GLOBAL / user-level (``--global``) — installs into ``~/.claude/`` (or
  ``$CLAUDE_CONFIG_DIR``); hooks are wired with absolute ``python3`` invocations
  so they fire for EVERY session, in every project, with no per-project install.

  Global works because on current Claude Code / Cowork builds the session is
  launched with ``--setting-sources=user,project,local`` — i.e. user-level
  settings (and their hooks) ARE loaded. (Older Cowork builds excluded the
  ``user`` source, which is why earlier docs said user-level hooks don't fire;
  that is no longer true — verified on claude-code 2.1.181.) The gate/session
  scripts resolve ``CLAUDE_PROJECT_DIR`` at runtime, so a single global gate
  still reads/writes each project's own ``.claude/`` sprint state.

Usage:
    python3 install.py [TARGET_PROJECT_DIR]   # project scope; defaults to cwd
    python3 install.py --global               # user-level (~/.claude) scope

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
# Project scope: self-locating .sh wrappers under the project's .claude.
GATE_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/antistall-gate.sh'
SESSION_CMD = '"$CLAUDE_PROJECT_DIR"/.claude/hooks/antistall-session-start.sh'


def _user_claude_dir() -> pathlib.Path:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return pathlib.Path(cfg) if cfg else pathlib.Path.home() / ".claude"


def _global_cmds(hooks: pathlib.Path) -> tuple[str, str]:
    # Absolute python3 invocations (shell-independent; no $CLAUDE_PROJECT_DIR, since
    # global hooks must resolve the project at runtime, not install time).
    g = hooks.joinpath("antistall-gate.py").as_posix()
    s = hooks.joinpath("antistall-session-start.py").as_posix()
    return f'python3 "{g}"', f'python3 "{s}"'


def _src_hooks() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent / "hooks"


def _has_cmd(entries: list, needle: str) -> bool:
    return any(
        needle in str(h.get("command", ""))
        for entry in entries
        for h in entry.get("hooks", [])
    )


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a not in ("--global", "--user")]
    is_global = any(a in ("--global", "--user") for a in argv[1:])

    if is_global:
        claude = _user_claude_dir()
        claude.mkdir(parents=True, exist_ok=True)
        hooks = claude / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        gate_cmd, session_cmd = _global_cmds(hooks)
        print(f"scope: GLOBAL (user-level) -> {claude}")
    else:
        target = pathlib.Path(args[0]).resolve() if args else pathlib.Path.cwd()
        if not target.is_dir():
            print(f"target project dir does not exist: {target}", file=sys.stderr)
            return 2
        claude = target / ".claude"
        hooks = claude / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        gate_cmd, session_cmd = GATE_CMD, SESSION_CMD
        print(f"scope: PROJECT -> {claude}")

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
            # utf-8-sig tolerates a BOM (Windows editors / PowerShell often add one).
            settings = json.loads(settings_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            print("WARNING: existing settings.json is not valid JSON; refusing to overwrite.",
                  file=sys.stderr)
            return 3

    hooks_block = settings.setdefault("hooks", {})
    stop = hooks_block.setdefault("Stop", [])
    session = hooks_block.setdefault("SessionStart", [])
    # Match on the extension-less basename so .sh and .py wirings both dedup,
    # and a project install never double-adds alongside a global one (or vice versa).
    if not _has_cmd(stop, "antistall-gate"):
        stop.append({"hooks": [{"type": "command", "command": gate_cmd}]})
        print("wired Stop hook")
    else:
        print("Stop hook already wired (skipped)")
    if not _has_cmd(session, "antistall-session-start"):
        session.append({"hooks": [{"type": "command", "command": session_cmd}]})
        print("wired SessionStart hook")
    else:
        print("SessionStart hook already wired (skipped)")

    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {settings_path}")

    arm_path = (hooks / "antistall.py").as_posix() if is_global else ".claude/hooks/antistall.py"
    print(
        "\nDone. Next:\n"
        "  1. RESTART the Code tab / Claude Code (hooks load at session start).\n"
        "  2. Arm a sprint when you start autonomous work (run from the project root\n"
        "     so it targets that project's state):\n"
        f"       python3 {arm_path} arm \"<the sprint goal>\"\n"
        "  3. To stop legitimately, write a ticket:\n"
        f"       python3 {arm_path} done|blocked|question \"<why>\"\n"
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
