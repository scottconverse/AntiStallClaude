---
name: antistall
description: Install and operate the AntiStallClaude gate — a Stop hook that physically blocks the "announce-then-halt" / silent drift-stop failure where an agent ends a turn with unfinished, authorized work. Use when the user says "install the anti-stall gate", "stop me/the agent stalling", "make me keep going", "anti-stall", "enforce no drift-stop", or wants an autonomous build to not bail at convenient boundaries. Also use to ARM a sprint, set the human release secret, or (human-only) RELEASE one. The agent CANNOT disarm — only a human passphrase can.
---

# AntiStallClaude — anti-stall gate (v0.3.0)

A memory note or CLAUDE.md rule that says "don't stop early" is **advice the
model rationalizes past**. This skill installs a **harness-enforced Stop hook**:
a separate process the harness runs on every turn-end that the model cannot
reason around. While a sprint is armed, ending a turn is **blocked**.

**Human-only disarm (the core guarantee):** the agent can ARM a sprint but can
NEVER turn it off. There is no stop-ticket and no agent command that ends a
sprint. Disarming requires a **human release passphrase** (stored only as a
salted hash, never in the agent's context). This closes the hole where an agent
wrote a "DONE" ticket to disarm itself and quit early.

## When invoked

- **Install** ("install the anti-stall gate", "stop me stalling") → Step A.
- **Set the release secret** (human, first-time) → Step B.
- **Arm a sprint** ("arm a sprint", "green-light autonomous work") → Step C.
- **Release** (human only, "I'm satisfied, stop the sprint") → Step D.
- **Verify** ("does the gate work", "test it") → Step E.

## Scope: global or project

On current Claude Code / Cowork builds the Code-tab session launches with
`--setting-sources=user,project,local`, so **user-level `~/.claude` hooks DO
fire** — a global install works and covers every project. (Older builds excluded
the `user` source; that's no longer true.) Use `--global` for machine-wide, or a
path for one project. The gate resolves `CLAUDE_PROJECT_DIR` at runtime, so one
global gate still uses each project's own per-session sprint state.

## Step A — Install

Run the bundled installer (copies the five hook scripts and merges the
`Stop` + `SessionStart` wiring, idempotently, backing up settings.json):

```
python3 install.py --global        # machine-wide (~/.claude)
python3 install.py <project-dir>   # one project (defaults to cwd)
```

Then tell the user to **restart the Code tab / Claude Code** (hooks load at
session start). Optionally add the one-line rule to `CLAUDE.md` (README "The rule
text") so the agent knows the protocol in-context.

## Step B — Set the release secret (HUMAN, first-time, out of band)

`arm` refuses until a release secret exists. The human must set it **in their own
terminal, not through the agent** (so the agent never sees it):

```
python3 .claude/hooks/antistall.py set-release-secret   # prompts (hidden) for a passphrase
```

The passphrase is stored only as a salted PBKDF2 hash in
`~/.claude/antistall-release.hash`. Changing it later requires the current one.

## Step C — Arm a sprint (agent or human)

```
python3 .claude/hooks/antistall.py arm "<the sprint goal>"   # gate now blocks drift-stops
python3 .claude/hooks/antistall.py status                    # armed state + whether a secret is set
python3 .claude/hooks/antistall.py request "<why you think you should stop>"  # notifies the human; does NOT disarm
```

**Arm when the user green-lights autonomous work.** Once armed, you (the agent)
**cannot stop or disarm**. A status summary is NEVER a stop. If you hit a genuine
human-only blocker, run `request "<why>"` to notify the operator, then KEEP
WORKING on anything else still buildable. Do NOT declare the work "done" to
escape — there is no such escape; finish it.

Token-burn safety: after `ANTISTALL_BLOCK_CAP` consecutive blocks (default 25)
the gate allows ONE stop but **does not disarm** (stays armed, notifies the
human, re-enforces next turn). `ANTISTALL_BLOCK_CAP=0` holds until release.

## Step D — Release (the human's passphrase ends it — but YOU run the command)

**When the user asks you to stop / disarm / cancel / "that's enough" — DO NOT refuse,
do NOT point them at a terminal, and do NOT tell them to find a `.cmd` file. Immediately
run, yourself:**

```
python3 <hooks>/antistall.py release --all
```

That **pops a masked PASSWORD BOX on the user's screen.** They type their passphrase into
it; you can't (and never see it). Correct passphrase → disarmed, you stop cleanly. Wrong /
cancelled → still armed, keep working. `--all` clears every gate under the project so a
project-dir mismatch can't make you "miss" the armed one.

**Never** claim the user released you, **never** say "run this in your terminal," **never**
send them hunting for a file. The whole disarm UX is: user says stop → you run `release` →
box appears → they type. If you're a *different* (non-gated) agent or there's no agent at
all, the user can also double-click `Release-Sprint.cmd` — but that's the fallback, not what
you tell them to do.

## Step E — Behavioral test (prove it fires AND that the agent can't escape)

In a session started AFTER install, with a release secret set:
1. `python3 .claude/hooks/antistall.py arm "gate test"`
2. Try to end the turn with no work done → you must be **blocked** with
   `[ANTI-STALL] … KEEP WORKING`.
3. Confirm the agent cannot escape: `... done "x"` is refused (removed); the gate
   stays armed.
4. Human: `python3 .claude/hooks/antistall.py release` (with the passphrase) →
   only now does it stop.

If Step 2 does not block, surface that loudly: check hooks are wired (global or
project `settings.json`), JSON is valid, and `python3` resolves on PATH.

## Removal

Delete the `Stop`/`SessionStart` entries from `settings.json` and remove
`hooks/antistall-*` + `hooks/antistall.py`. State files (`sprint-gate-*.json`,
`sprint-stop-request.json`, `.antistall-block-count-*`, and
`~/.claude/antistall-release.hash`) are harmless to delete.
