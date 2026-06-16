---
name: antistall
description: Install and operate the AntiStallClaude gate — a project-level Stop hook that physically blocks the "announce-then-halt" / silent drift-stop failure where an agent ends a turn with unfinished, authorized work. Use when the user says "install the anti-stall gate", "stop me/the agent stalling", "make me keep going", "anti-stall", "enforce no drift-stop", or wants an autonomous build to not bail at convenient boundaries. Also use to ARM/DISARM a sprint or write a stop-ticket (done/blocked/question).
---

# AntiStallClaude — anti-stall gate

A memory note or CLAUDE.md rule that says "don't stop early" is **advice the
model rationalizes past**. This skill installs a **harness-enforced Stop hook**:
a separate process the harness runs on every turn-end that the model cannot
reason its way around. While a sprint is armed, ending a turn is **blocked**
unless a fresh single-use stop-ticket declares a legitimate reason
(`DONE` / `BLOCKED` / `QUESTION`). An anti-loop cap guarantees a real dead-end
can always escape.

## When invoked

Figure out which the user wants:

- **Install** ("install the anti-stall gate", "stop me stalling") → Step A.
- **Arm / disarm / ticket** ("arm a sprint", "I'm done", "I'm blocked") → Step B.
- **Verify** ("does the gate work", "test it") → Step C.

## Cowork constraint (read first)

User-level (`~/.claude/`) hooks **do not fire in Cowork's Code tab** — only
**project-level** hooks do. Everything goes in the project's `.claude/`. If you
put hooks in `~/.claude/`, they silently never run.

## Step A — Install

1. Confirm the target project directory (default: the current working dir / the
   repo root the user is in).
2. Copy the five hook scripts from this skill's `hooks/` into
   `<project>/.claude/hooks/`:
   `antistall-gate.py`, `antistall-gate.sh`, `antistall-session-start.py`,
   `antistall-session-start.sh`, `antistall.py`. Make the `.sh` files executable.
   (Or run the bundled installer: `python3 install.py <project>` — it copies the
   hooks and merges the settings wiring for you.)
3. Merge into `<project>/.claude/settings.json` (create it if absent; back it up
   first; do NOT clobber existing entries):
   ```json
   {
     "hooks": {
       "Stop": [{ "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/antistall-gate.sh" }] }],
       "SessionStart": [{ "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/antistall-session-start.sh" }] }]
     }
   }
   ```
4. Tell the user: **restart the Code tab / Claude Code** (hooks load at session
   start), then run the behavioral test (Step C).
5. Optionally add a one-line rule to the project `CLAUDE.md` so the agent knows
   the protocol in-context (see README "The rule text").

## Step B — Arm / disarm / ticket (the helper)

Run from the project root:

```
python3 .claude/hooks/antistall.py arm  "<the sprint goal>"   # arm: gate now blocks drift-stops
python3 .claude/hooks/antistall.py done "<why finished>"      # whole queue done (also disarms)
python3 .claude/hooks/antistall.py blocked  "<human-only decision needed>"   # stays armed
python3 .claude/hooks/antistall.py question "<what you asked the human>"      # stays armed
python3 .claude/hooks/antistall.py status                     # show armed state + pending ticket
```

**Arm when the user green-lights autonomous work.** A status summary is NEVER a
stop — if work remains and nothing blocks you, keep working in the same turn.
Stop only by writing a ticket with a real reason.

## Step C — Behavioral test (prove it fires)

Hooks load at session start, so test in a session started AFTER install:
1. `python3 .claude/hooks/antistall.py arm "gate test"`
2. Try to end the turn with a one-line reply and NO ticket → you must be
   **blocked** with `[ANTI-STALL] … KEEP WORKING`. If you stop cleanly, the hook
   is not firing (wrong scope, or the harness isn't running project Stop hooks).
3. `python3 .claude/hooks/antistall.py done "test complete"` → you can now stop.

If Step 2 does not block, surface that loudly and check: hooks are PROJECT-level,
`settings.json` is valid JSON, and `python3` resolves on PATH.

## Removal

Delete the `Stop`/`SessionStart` entries from `.claude/settings.json` and remove
`.claude/hooks/antistall-*` + `.claude/hooks/antistall.py`. State files
(`.claude/sprint-gate.json`, `sprint-stop-ticket.json`, `.antistall-block-count`)
are harmless to delete.
