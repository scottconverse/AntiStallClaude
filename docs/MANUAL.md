# AntiStallClaude — Manual

Version 0.1.0

This manual covers the design, the internals, the operating protocol, the Cowork
specifics, configuration, the behavioral test, and an FAQ. For a quick start see
the [README](../README.md).

---

## 1. What problem this solves

Autonomous coding agents **stall**: mid-task, with authorized work still queued
and nothing actually blocking them, they end the turn — usually right after
composing a "here's everything I did, next I'll…" summary. The human comes back
to a silent screen and a half-finished job.

The recurring tell: **the act of writing an "everything I did" summary is itself
the decision to stop.** For unfinished, authorized work, that decision is the
defect.

### Why the usual fixes fail

| Approach | Why it fails |
|----------|--------------|
| `CLAUDE.md` rule ("always finish") | *Advice.* Lives in the model's context, competes with every other consideration, and gets rationalized away ("clean checkpoint", "turn is long"). |
| Memory note | Same advice, different file. Degrades over a long session; loses to in-the-moment reasoning. |
| System-prompt nudge | Still text the model weighs — same failure class. |

They all live **inside the model's reasoning**, which is exactly the thing that
fails.

### Why a hook works

A `Stop` hook is a **separate process the harness executes** every time the
agent tries to end a turn. The model cannot weigh it, reinterpret it, or
rationalize past it — it is not the model's code to run. That structural
difference is the whole point.

---

## 2. Design

The gate is **default-deny while armed**. It inverts the agent's posture from
*"stopping is allowed unless I remember not to"* to *"stopping is blocked unless
I take a deliberate, logged action with a reason."*

Three — and only three — legitimate ways to end an armed turn:

- **`DONE`** — the entire queue of authorized work is finished.
- **`BLOCKED`** — a decision only the human can make blocks *all* remaining work.
- **`QUESTION`** — the agent asked the human something and needs the answer to proceed.

Each is recorded as a **single-use stop-ticket**. The hook consumes it and
allows exactly one turn-end. Anything else — including a tidy progress summary —
is blocked, and the agent is told to keep working.

### Safety: the anti-loop cap

A gate that can never be satisfied would trap a session forever. So after
`ANTISTALL_BLOCK_CAP` (default **6**) consecutive blocks, the gate **allows** the
stop and logs loudly. A genuine dead-end always escapes; casual stalling still
costs the agent six forced continuations. This is the escape hatch, not the
happy path.

### Silent when idle

When no sprint is armed, the gate exits 0 immediately. Normal conversational
turns, Q&A, and one-off tasks are never gated — you only arm it for autonomous
build stretches.

---

## 3. Internals

### Files installed into the project's `.claude/`

```
.claude/
├── hooks/
│   ├── antistall-gate.py            # the Stop hook (the enforcement)
│   ├── antistall-gate.sh            # self-locating wrapper the harness calls
│   ├── antistall-session-start.py   # SessionStart reminder injection
│   ├── antistall-session-start.sh   # wrapper
│   └── antistall.py                 # operator helper (arm/done/blocked/question/status)
└── settings.json                    # Stop + SessionStart wiring (merged, not clobbered)
```

### Runtime state (also in `.claude/`, git-ignored)

| File | Shape | Meaning |
|------|-------|---------|
| `sprint-gate.json` | `{"active": true, "note": "…"}` | the armed flag |
| `sprint-stop-ticket.json` | `{"reason": "...", "detail": "...", "ts": <epoch>}` | single-use stop-ticket |
| `.antistall-block-count` | integer | consecutive-block counter |

### The Stop hook algorithm (`antistall-gate.py`)

1. Read (and discard) the Stop payload from stdin. Fail **open** on an
   unparseable payload — never wedge a session on a framing change.
2. If `sprint-gate.json` is absent or not `active` → `exit 0` (silent).
3. If `sprint-stop-ticket.json` exists, consume it (delete — single-use). If its
   `reason` is `DONE`/`BLOCKED`/`QUESTION` and it is younger than
   `ANTISTALL_TICKET_MAX_AGE_S` (default 300s), reset the counter and `exit 0`
   (allow the stop).
4. Otherwise increment the block counter. If it reaches the cap, delete it,
   log the escape, and `exit 0`. Else print
   `{"decision":"block","reason":"… KEEP WORKING …"}` and `exit 0`.

Stop hooks signal "keep going" via the JSON `decision: block` on **stdout**, not
via exit code (that is the PreToolUse convention). The hook always exits 0.

### Self-location

Both `.sh` wrappers and the `.py` scripts resolve the project `.claude/` from
`$CLAUDE_PROJECT_DIR` when set, else from the script's own path
(`parents[1]`). So they work whether or not the harness exports
`CLAUDE_PROJECT_DIR` at hook runtime.

---

## 4. Operating protocol

```bash
# Arm when the human green-lights autonomous work:
python3 .claude/hooks/antistall.py arm "build + test the export pipeline"

# End an armed turn ONLY by writing a ticket:
python3 .claude/hooks/antistall.py done     "pipeline shipped, tests green"   # also disarms
python3 .claude/hooks/antistall.py blocked  "need prod DB creds from you"     # stays armed
python3 .claude/hooks/antistall.py question "which storage backend?"          # stays armed

python3 .claude/hooks/antistall.py status     # armed? pending ticket?
```

**The discipline the gate enforces:** a status summary is not a stop. If work
remains and nothing blocks you, keep working in the same turn. The only honest
ways to stop are `done`, `blocked`, or `question`.

After a `blocked`/`question` ticket, the sprint stays armed: when the human
answers, you resume under the gate. After `done`, the sprint disarms.

---

## 5. Cowork notes (important)

AntiStallClaude is built for Claude Code and Cowork. Two Cowork facts shaped the
design:

1. **User-level (`~/.claude/`) hooks do NOT fire in Cowork's Code tab.** Only
   **project-level** hooks fire. Everything installs into the project's
   `.claude/`. Putting hooks in `~/.claude/` is the #1 way to get a gate that
   silently never runs.
2. **Some Cowork builds do not surface project `SessionStart` `additionalContext`**
   to the agent (the project **Stop** hook still fires). So the SessionStart
   reminder is best-effort; **enforcement does not depend on it.** Put the
   one-line rule in your `CLAUDE.md` (README → "The rule text") for an
   always-loaded reminder, and/or run `antistall.py status` on resume to learn
   the live armed state.

In plain Claude Code (CLI/desktop, non-Cowork), both hooks fire normally and the
SessionStart reminder surfaces.

---

## 6. Configuration

| Env var | Default | Meaning |
|---------|---------|---------|
| `ANTISTALL_BLOCK_CAP` | `6` | consecutive blocks before the escape hatch fires |
| `ANTISTALL_TICKET_MAX_AGE_S` | `300` | a stop-ticket older than this is treated as stale |

Set them in the project's `.claude/settings.json` `env` block or the
environment the harness launches hooks in.

---

## 7. Behavioral test (prove it fires)

Hooks load at session start, so test in a session started **after** install.

1. `python3 .claude/hooks/antistall.py arm "gate test"`
2. Try to end the turn with a one-line reply and **no** ticket → you must be
   **blocked** with `[ANTI-STALL] … KEEP WORKING`. If you stop cleanly, the hook
   is **not** firing.
3. `python3 .claude/hooks/antistall.py done "test complete"` → you can now stop.

If step 2 does not block, check, in order:
- The hooks are **project-level** (`<project>/.claude/`), not `~/.claude/`.
- `.claude/settings.json` is valid JSON and contains the `Stop` entry.
- `python3` resolves on PATH in the hook runtime.
- You restarted after install (hooks load at session start).

There is also a harness-free unit test: `python3 tests/test_gate.py`.

---

## 8. FAQ

**Can the agent cheat by writing a fake `DONE` ticket?**
Yes — it is not unspoofable. But that turns a *silent passive drift* into an
*explicit, logged, auditable claim* sitting next to obviously-unfinished work.
You can see it; you can call it. And default-deny removes the lazy path —
stopping now requires a deliberate, named action.

**Does this make the agent do good work?**
No. It enforces *don't stop early*, not *do the work well*. Pair it with tests,
CI, and review.

**Will it nag me during normal chat?**
No. The gate is silent unless a sprint is armed. Arm it only for autonomous
build stretches; disarm with `done` (or delete `sprint-gate.json`).

**It blocked me when I genuinely needed to stop and ask.**
That is the `question` ticket: `antistall.py question "…"`. Or `blocked` for a
hard external blocker. Both are legitimate, logged exits.

**Does it work outside Claude Code?**
Any agent runtime that supports a `Stop`-style hook returning a block decision
can use `antistall-gate.py`. The wiring (`settings.json`) is Claude Code's
format; adapt it to your runtime's hook config.

---

## 9. Removal

Delete the `Stop`/`SessionStart` entries from `.claude/settings.json` and the
`.claude/hooks/antistall-*` files. The state files (`sprint-gate.json`,
`sprint-stop-ticket.json`, `.antistall-block-count`) are harmless to delete.
