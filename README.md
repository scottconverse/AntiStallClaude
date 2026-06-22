# AntiStallClaude

**A harness-enforced gate that stops AI coding agents from quitting early.**

Version 0.3.1 · MIT licensed · built for [Claude Code](https://claude.com/claude-code) & Cowork

> **Upgrading from 0.1.0?** 0.1.0 shipped a `Stop`-hook bug that could loop
> forever and burn tokens (the counter failed closed and the hook ignored
> `stop_hook_active`). **Replace `antistall-gate.py` with the 0.1.1 version** (or
> re-run `install.py`). See the [CHANGELOG](CHANGELOG.md).

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
2. **Per-session, fail-open anti-loop cap (secondary).** For any runtime that
   doesn't surface `stop_hook_active`, a consecutive-block counter (default 6)
   still caps the loop. The counter file is **keyed on the session id**, so two
   agents in one project never share it — closing the cross-agent race for real,
   not just on paper. And *any* uncertainty about the counter (missing, empty,
   corrupt, unreadable, or unwritable) **allows** the stop rather than blocking
   again. A loop guard must never be able to loop itself.

When no sprint is armed, the gate is **silent**: normal conversational turns are
never gated.

This inverts the default. Instead of *"stopping is allowed unless I remember not
to,"* it becomes *"stopping is blocked unless I take a deliberate, logged action
with a reason."* The announce-then-halt drift literally cannot happen — if the
agent writes "next I'll do X" and tries to end, the hook bounces it back into X.

## How it works

```
agent finishes a turn ──▶ harness runs antistall-gate.sh  (thin wrapper → execs antistall-gate.py; all logic is in the .py)
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

**Update (verified on claude-code 2.1.181): user-level (`~/.claude/`) hooks now
DO fire in Cowork's Code tab.** The Code-tab session is launched with
`--setting-sources=user,project,local`, so user-level settings — and their
hooks — are loaded. This means a **global install (`--global`) works** and you no
longer need to install per-project. (Earlier Cowork builds excluded the `user`
source, which is why prior versions of this doc said user-level hooks don't fire;
that limitation is gone on current builds. Verify your own build with
`Get-CimInstance Win32_Process -Filter "Name='claude.exe'"` and look for `user`
in `--setting-sources`.)

The globally-installed gate resolves `CLAUDE_PROJECT_DIR` at runtime, so a single
gate in `~/.claude/` still reads and writes **each project's own** `.claude/`
sprint state — arming a sprint in project A never affects project B.

**Multiple sessions in one project (v0.2.1+).** Sprint state is **session-scoped**:
`arm` writes `sprint-gate-<session_id>.json` (stamped with an `owner`) and the gate
keys off the Stop payload's `session_id` (the harness exposes the same id to the CLI
as `CLAUDE_CODE_SESSION_ID`). So two Cowork sessions working in the same folder no
longer gate each other — only the session that armed a sprint is held to it. A
pre-0.2.1 project-wide `sprint-gate.json` is still honored for backward compatibility
(treated as unowned → applies to all sessions, or pin it to one session by adding
`"owner": "<session_id>"`).

(Some Cowork builds still don't surface project *SessionStart* `additionalContext`;
the **Stop** hook — the actual enforcement — fires regardless. The `CLAUDE.md`
rule below covers the reminder either way.)

## Install

### Option 1 — the installer (any project)

```bash
git clone https://github.com/scottconverse/AntiStallClaude.git
python3 AntiStallClaude/install.py /path/to/your/project   # project scope; defaults to cwd
python3 AntiStallClaude/install.py --global                # user-level (~/.claude) — every project
```

**Project scope** copies the hooks into `<project>/.claude/hooks/` and merges the
`Stop` + `SessionStart` wiring into `<project>/.claude/settings.json`.

**Global scope** (`--global`) installs into `~/.claude/` (or `$CLAUDE_CONFIG_DIR`)
and wires the hooks with absolute `python3` invocations so they fire for **every
session in every project** — no per-project install. See the Cowork note above for
why this works on current builds. The gate still uses each project's own state at
runtime. Don't run both scopes for the same project; the installer dedups by hook
name, but a hand-rolled mix could double-fire.

Both are idempotent and back up any existing `settings.json` first.

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

## Human-only disarm (v0.3.0 — important)

**The agent can arm a sprint but can never turn it off.** Earlier versions let the
agent write a `DONE` ticket to disarm itself — which meant a drifting agent could
declare victory and quit early (the exact failure the gate exists to prevent). That
self-service exit is **removed**. Disarming now requires a **human release passphrase**
stored only as a salted PBKDF2 hash — never in plaintext, never in the agent's context.

```bash
# HUMAN, once, in YOUR OWN terminal (not via the agent, so it never sees the secret):
python3 .claude/hooks/antistall.py set-release-secret      # prompts (hidden) for a passphrase

# Arm a sprint (agent or human) — refused unless a release secret exists:
python3 .claude/hooks/antistall.py arm "build the export pipeline"

# The agent now CANNOT stop or disarm. Its only options while armed:
#   keep working  ·  or surface a blocker to you (does NOT disarm):
python3 .claude/hooks/antistall.py request "need the prod DB credentials"  # notifies you

# HUMAN, to end the sprint — the ONLY disarm, needs the passphrase:
python3 .claude/hooks/antistall.py release          # this session's/owner gate
python3 .claude/hooks/antistall.py release --all    # every gate in the project

python3 .claude/hooks/antistall.py status           # armed state + whether a secret is set
```

**No terminal? (Cowork / GUI users — v0.3.1).** You never have to touch a CLI. On Windows,
`set-release-secret` and `release` pop a **masked password dialog** (the agent launches the
window but cannot see what you type into it). Two **double-click launchers** are installed next
to the hooks so it's pure point-and-click:

- **`Set-AntiStall-Secret.cmd`** — set/change your passphrase (masked box).
- **`Release-Sprint.cmd`** — pick the project, type your passphrase, disarm.

`install.py` copies both into the `.claude/` dir (e.g. `~/.claude/`). To disarm from a chat
agent instead, tell it "disarm" — it pops the same box; you type the passphrase; it still can't
supply it. The passphrase is stored only as a salted PBKDF2 hash; the agent never sees it.

Token-burn safety: after `ANTISTALL_BLOCK_CAP` consecutive blocks (default **25**) the gate
allows ONE stop so a stuck agent can't burn tokens forever — but this **pauses without
disarming** (the sprint stays armed, you get a desktop notification, it re-enforces next
turn). Set `ANTISTALL_BLOCK_CAP=0` to hold indefinitely until you `release`.

**Threat model (honest):** this removes every *sanctioned* self-exit, so a well-behaved but
drift-prone agent has no way to quit a sprint. It is not a sandbox: an agent with full
filesystem + admin rights on the same machine could still delete the gate/secret files
outright — that's flagrant tampering, not a normal exit, and is out of scope for a userspace
hook. For OS-hard enforcement, lock the gate/secret files via ACLs (e.g. an elevated helper)
so the agent's normal token can't write them.

## The rule text (drop into your `CLAUDE.md`)

> **Anti-Stall Gate.** A `Stop` hook blocks ending a turn while a sprint is armed
> (`.claude/sprint-gate-<session>.json`). You (the agent) **cannot** stop or disarm it —
> there is no ticket you can write; only a human, with a release passphrase, ends it via
> `antistall.py release`. Do **not** declare work "done" to escape — finish it. If truly
> blocked on a human-only decision, run `antistall.py request "<why>"` to notify the
> operator, then keep working on anything else still buildable. A status summary is NOT a stop.

## Verify it works

In a session started *after* install:

```bash
python3 .claude/hooks/antistall.py set-release-secret    # once, if you haven't
python3 .claude/hooks/antistall.py arm "gate test"
# now try to end your turn → you should be BLOCKED with [ANTI-STALL] … KEEP WORKING.
# Confirm the agent CANNOT escape: `... done "x"` is refused; the gate stays armed.
python3 .claude/hooks/antistall.py release               # human + passphrase → only way to stop
```

There's also a self-contained unit test (no harness needed):

```bash
python3 tests/test_gate.py
```

## Config (optional env)

| Variable | Default | Meaning |
|----------|---------|---------|
| `ANTISTALL_BLOCK_CAP` | `6` | consecutive-block count that trips the secondary escape hatch (allows the Nth turn-end after N−1 forced continuations). Only reached on a runtime that does **not** surface `stop_hook_active`; on Claude Code/Cowork the primary guard caps nudges at exactly **1** per chain, so this is rarely hit. |
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
