# AntiStallClaude

**A harness-enforced gate that stops AI coding agents from quitting early.**

Version 0.1.0 · MIT licensed · built for [Claude Code](https://claude.com/claude-code) & Cowork

> **Runtime support — read this honestly.** The gate is built against **Claude
> Code's** `Stop`-hook contract: it returns `{"decision":"block"}` on stdout and
> wires in via a project-level `.claude/settings.json`. It runs **as-is on Claude
> Code and Cowork** (Cowork is Claude Code in desktop-agent mode). The *idea* — a
> block-capable turn-end hook — could port to another agent runtime, but the
> shipped script speaks Claude Code's protocol, so you would have to adapt it.
> **No other runtime (Codex, Gemini CLI, GitHub Copilot CLI, …) has been verified
> to support a compatible block-on-stop hook.** Don't assume drop-in portability.

---

## The problem

Autonomous coding agents stall. Mid-task, with authorized work still on the
queue and nothing actually blocking them, they end the turn — often after
writing a tidy "here's what I did, next I'll…" summary, and then just… stopping.
You come back to a silent screen and a half-finished job.

The usual "fixes" don't hold:

- **A `CLAUDE.md` rule** ("always finish the task") is *advice*. It lives in the
  model's context and competes with every other consideration; the model
  rationalizes past it ("this is a clean checkpoint", "the turn is long").
- **A memory note** is the same advice in a different file. It degrades over a
  long session and loses to in-the-moment reasoning.

The tell is consistent: **the moment the agent starts composing an
"everything I did" summary, it has already decided to stop.** For unfinished,
authorized work, that decision is the bug.

## The fix

AntiStallClaude installs a **`Stop` hook** — a separate process the harness runs
*every time the agent tries to end a turn*. The model can't reason its way past
code that isn't its to run.

While a **sprint is armed**, ending a turn is **blocked** and the agent is
pushed back to work, unless it writes a fresh, single-use **stop-ticket**
declaring a legitimate reason:

- **`DONE`** — the whole queue is finished (also disarms the sprint).
- **`BLOCKED`** — a decision only the human can make halts *all* remaining work.
- **`QUESTION`** — the agent asked the human something and needs the answer.

**The gate can never loop or trap a session.** A blocking `Stop` hook that
re-blocks while the agent is *already* continuing because of a prior block would
run forever and burn tokens without limit — the single most dangerous failure
mode of this kind of hook. Two independent guards prevent it:

1. **`stop_hook_active` (primary).** The harness sets this flag on a `Stop` that
   is itself the result of a previous block. When it's set, the gate **always**
   allows the stop. So the gate nudges a drift-stop at most **once per
   continuation chain** — it stops the drift, it can't loop on it. This depends
   on no shared file, so it's immune to races.
2. **Fail-open anti-loop cap (secondary).** For any runtime that doesn't surface
   `stop_hook_active`, a consecutive-block counter (default 6) still caps the
   loop — and *any* uncertainty about that counter (unreadable, corrupt, or two
   agents racing on the file) **allows** the stop rather than blocking again. A
   loop guard must never be able to loop itself.

When no sprint is armed, the gate is **silent**: normal conversational turns are
never gated.

This inverts the default. Instead of *"stopping is allowed unless I remember not
to,"* it becomes *"stopping is blocked unless I take a deliberate, logged action
with a reason."* The announce-then-halt drift literally cannot happen — if the
agent writes "next I'll do X" and tries to end, the hook bounces it back into X.

## How it works

```
agent finishes a turn ──▶ harness runs .claude/hooks/antistall-gate.sh
                                   │
                  sprint armed? ───┼─── no ──▶ exit 0  (silent)
                                   │
                                  yes
                                   │
            stop_hook_active? ─────┼─── yes ──▶ allow stop  (LOOP GUARD — never block a
                                   │            continuation that a prior block caused)
                                   no
                                   │
                fresh DONE/BLOCKED/QUESTION ticket? ── yes ──▶ consume it, allow stop
                                   │
                                   no
                                   │
       block count ≥ cap, OR counter unreadable/corrupt? ── yes ──▶ allow stop  (fail-open escape)
                                   │
                                   no
                                   ▼
                 {"decision":"block","reason":"KEEP WORKING …"}  ── agent continues
```

State lives in the project's `.claude/`:

| File | Meaning |
|------|---------|
| `sprint-gate.json` | `{"active": true, "note": "…"}` — the armed flag |
| `sprint-stop-ticket.json` | the single-use ticket the hook consumes |
| `.antistall-block-count` | consecutive-block counter (anti-loop) |

## Cowork note (important)

**User-level (`~/.claude/`) hooks do NOT fire in Cowork's Code tab — only
project-level hooks do.** AntiStallClaude installs everything into the
project's `.claude/`. (Some Cowork builds also don't surface project
*SessionStart* `additionalContext`; the project **Stop** hook — the enforcement
— still fires. The `CLAUDE.md` rule below covers the reminder either way.)

## Install

### Option 1 — the installer (any project)

```bash
git clone https://github.com/scottconverse/AntiStallClaude.git
python3 AntiStallClaude/install.py /path/to/your/project   # defaults to the current dir
```

It copies the hooks into `<project>/.claude/hooks/` and merges the `Stop` +
`SessionStart` wiring into `<project>/.claude/settings.json` (backing up any
existing file; idempotent).

### Option 2 — as a Claude Code skill

Copy `skill/antistall/` into `~/.claude/skills/antistall/`, then ask the agent
to *"install the anti-stall gate"* — the skill installs it into your current
project and walks you through the behavioral test.

### Option 3 — manual

Copy the five files in `hooks/` into `<project>/.claude/hooks/`, then add to
`<project>/.claude/settings.json` (see [`examples/settings.json`](examples/settings.json)):

```json
{
  "hooks": {
    "Stop": [{ "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/antistall-gate.sh" }] }],
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/antistall-session-start.sh" }] }]
  }
}
```

**Then restart the Code tab / Claude Code** — hooks load at session start.

## Usage

```bash
# When you green-light autonomous work:
python3 .claude/hooks/antistall.py arm "build the export pipeline"

# The agent now cannot drift-stop. It ends a turn only via a ticket:
python3 .claude/hooks/antistall.py done     "pipeline shipped + tests green"   # disarms
python3 .claude/hooks/antistall.py blocked  "need the prod DB credentials"     # stays armed
python3 .claude/hooks/antistall.py question  "which storage backend do you want?"

python3 .claude/hooks/antistall.py status    # show armed state + pending ticket
```

## The rule text (drop into your `CLAUDE.md`)

> **Anti-Stall Gate.** A project `Stop` hook blocks ending a turn while a sprint
> is armed (`.claude/sprint-gate.json`) unless a fresh stop-ticket declares
> `DONE`/`BLOCKED`/`QUESTION`. A status summary is NOT a stop — if work remains
> and nothing blocks you, keep working in the same turn. Arm/ticket via
> `python3 .claude/hooks/antistall.py {arm|done|blocked|question|status}`.

## Verify it works

In a session started *after* install:

```bash
python3 .claude/hooks/antistall.py arm "gate test"
# now try to end your turn with no ticket → you should be BLOCKED with [ANTI-STALL] … KEEP WORKING
python3 .claude/hooks/antistall.py done "test complete"   # now you can stop
```

There's also a self-contained unit test (no harness needed):

```bash
python3 tests/test_gate.py
```

## Config (optional env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ANTISTALL_BLOCK_CAP` | `6` | consecutive-block count that trips the escape hatch (allows the Nth turn-end after N−1 forced continuations) |
| `ANTISTALL_TICKET_MAX_AGE_S` | `300` | a stop-ticket older than this is stale |

## Removal

Delete the `Stop`/`SessionStart` entries from `.claude/settings.json` and the
`.claude/hooks/antistall-*` files. The state files are harmless to delete.

## Honest limitations

- It is **not** unspoofable: the agent could write a false `DONE` ticket. But
  that converts a *silent passive drift* into an *explicit, logged, auditable
  claim* you can see next to obviously-unfinished work — a categorical
  improvement, and the default-deny makes the lazy path impossible.
- It enforces *don't stop early*, not *do good work*. Pair it with tests/CI.

## Docs

- [Full manual](docs/MANUAL.md) — design, internals, Cowork specifics, FAQ.
- [Landing page](docs/index.html).
- [CHANGELOG](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

> AntiStallClaude was extracted from a real fix: an agent that kept
> announce-then-halting mid-build, and a human who finally asked, *"is there a
> hard hook we can put in place to stop this?"* There is. This is it.
