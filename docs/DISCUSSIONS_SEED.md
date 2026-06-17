# GitHub Discussions — seed posts

Ready-to-post seed threads for the repo's Discussions tab. Create the categories
(Announcements, Q&A, Show and tell, Ideas) under *Settings → Features →
Discussions*, then paste each post into its category. (The maintainer can also
post these via `gh api graphql` — see the repo's publish notes.)

---

## 📣 Announcements — "AntiStallClaude 0.1.0 is here: stop your agent quitting early"

Autonomous coding agents stall. Mid-task, with work still queued and nothing
actually blocking them, they write a tidy "here's what I did, next I'll…"
summary — and stop. You come back to a silent screen and a half-finished job.

We tried the usual fixes. A `CLAUDE.md` rule is advice the model rationalizes
past. A memory note degrades over a long session. They all live *inside* the
model's reasoning — the exact thing that's failing.

**AntiStallClaude 0.1.0** is the structural fix: a project-level `Stop` hook the
harness runs on every turn-end. While a sprint is armed, ending a turn is
**blocked** unless the agent writes a single-use stop-ticket declaring `DONE`,
`BLOCKED`, or `QUESTION`. An anti-loop cap guarantees a real dead-end always
escapes; the gate is silent when no sprint is armed.

It was extracted from a real session: an agent that kept announce-then-halting
mid-build, and a human who finally asked, *"is there a hard hook we can put in
place to stop this?"* There is.

- Install + docs: see the README.
- Built for Claude Code & Cowork. The shipped hook speaks Claude Code's protocol; no other runtime (Codex, Gemini CLI, Copilot CLI) is verified. MIT.

What stalls *your* agent most? Drop a reply.

---

## ❓ Q&A — "How is this different from just putting a rule in CLAUDE.md?"

**Q:** I already tell my agent "always finish the task" in `CLAUDE.md`. Why do I
need a hook?

**A:** Because a `CLAUDE.md` rule is *advice*. It lives in the model's context
and competes with every other consideration in the moment — "this is a clean
checkpoint", "the turn is long", "I'll continue next time". Over a long session
that advice loses. A `Stop` hook is a **separate process** the harness runs;
the model can't reinterpret or rationalize past code that isn't its to run.
AntiStallClaude flips the default from "stopping is allowed unless I remember not
to" to "stopping is blocked unless I write a `DONE`/`BLOCKED`/`QUESTION` ticket."

---

## ❓ Q&A — "I installed it but the gate never fires (Cowork)"

**Q:** I put the hooks in `~/.claude/` and nothing happens.

**A:** That's the #1 gotcha. **User-level (`~/.claude/`) hooks do NOT fire in
Cowork's Code tab — only project-level hooks do.** AntiStallClaude's installer
puts everything in the *project's* `.claude/`. Check:

1. Hooks are in `<project>/.claude/hooks/` (not `~/.claude/hooks/`).
2. `<project>/.claude/settings.json` is valid JSON and has the `Stop` entry.
3. `python3` resolves on PATH in the hook runtime.
4. You **restarted** after install — hooks load at session start.

Also note: some Cowork builds don't surface the project *SessionStart* reminder
(the **Stop** hook — the enforcement — still fires). Put the one-line rule in
`CLAUDE.md` for an always-loaded reminder.

---

## 🙌 Show and tell — "Post your arm/done/blocked/question workflow"

How are you using the gate? Share your sprint flow:

- What do you `arm` it with at the start of an autonomous run?
- How often do you legitimately `blocked` vs `question`?
- Did it catch a drift-stop it shouldn't have? (Tune `ANTISTALL_BLOCK_CAP` or
  file an issue.)

Screenshots of the `[ANTI-STALL] … KEEP WORKING` block in the wild welcome.

---

## 💡 Ideas — "Roadmap & wishlist for 0.2.0"

Some directions on the table — 👍 the ones you want, or propose your own:

- A **PreToolUse companion** gate (e.g., block `git push` until a checklist
  passes) to pair with the Stop gate.
- **Multi-agent / sub-agent** awareness (per-agent sprint flags).
- **Config presets** (strict / lenient) and a richer ticket schema.
- A tiny **dashboard** of the current sprint state + block history.
- Adapters for other agent runtimes' hook formats.

What would make this a daily-driver for you?
