# Engineering Deep-Dive — AntiStall Stop-Hook Loop Fix

**Role:** Principal Engineer (correctness, security, races, edge cases, termination guarantee)
**Branch:** `fix/stop-hook-infinite-loop` @ `e31f858`
**Repo:** `C:/Users/scott/Desktop/Code/AntiStallClaude`
**Date:** 2026-06-17

## Scope & method

Read the full files (not just the diff): `hooks/antistall-gate.py`,
`skill/antistall/hooks/antistall-gate.py`, `tests/test_gate.py`, the four doc
files, plus the live customized copy `C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py`
and its test. Ran both test suites. Compared the two repo copies by sha256.
Adversarially probed the termination guarantee against every payload/state
permutation the role brief names.

## Verdict

The fix is **correct and the primary termination guarantee holds.** The
`stop_hook_active` guard is race-proof and caps the gate at one nudge per
continuation chain; the fail-open counter is a genuine independent backstop and
every counter anomaly branch verifiably allows (fails open). The two repo copies
are byte-identical. Tests pass and are non-vacuous. One **Major** residual:
the doc/comment claim that the *cross-agent counter race is closed* is only true
when the harness surfaces `stop_hook_active`; a harness lacking that flag plus
two agents racing the counter file is not fully closed by the fail-open counter
alone (a successful-but-stale concurrent write is not an "anomaly"). Plus minor
doc/file-name drift. No Blockers, no Critical.

---

## What's correct (credit where due)

- **Primary guard is sound and race-proof.** `hooks/antistall-gate.py:133-138`:
  if `payload.get("stop_hook_active")` is truthy, unlink the counter and allow.
  This is derived purely from the per-event stdin payload — no shared mutable
  file — so it is immune to the cross-agent counter race that caused the
  original bug. It caps the gate at exactly one block per continuation chain.
- **Counter genuinely fails OPEN on every anomaly** (`:156-184`): FileNotFound →
  treat as `"0"` (block path, correct — first block); unreadable (other OSError)
  → `_allow` (`:162`); unparseable `int()` → unlink + `_allow` (`:169`);
  `n >= cap` → unlink + `_allow` (`:173`); unwritable → `_allow` (`:183`). Every
  uncertainty path reaches `_allow`/exit 0 with no `{"decision":"block"}`. I
  traced each branch; none can emit a block.
- **Fail-open vs the old fail-closed bug is real.** The old code reset an
  unreadable counter to 0 and kept blocking; here an unreadable counter allows.
  Confirmed by test F (`tests/test_gate.py:106-110`) and live test step 7.
- **Ticket consume-then-validate ordering is correct** (`:143-152`): the ticket
  is unlinked the instant it is read as a dict (`:144`), *before* the
  validity/freshness check, so a stale or invalid ticket is consumed on sight
  and cannot be replayed. Counter reset only happens on a *valid fresh* ticket
  (`:151`). Verified by C2 (stale consumed) and live 5/5b.
- **Counter reset ordering vs allow.** On every allow path that resets the
  counter (`stop_hook_active`, valid ticket, cap reached) the unlink precedes
  `_allow`, and `_allow` calls `sys.exit(0)` — no further code runs, so there is
  no window where the counter is left stale after an allow.
- **Unparseable payload fails open to the flag check** (`:115-120`): non-dict or
  bad JSON → `{}` → `stop_hook_active` reads falsy → falls through to normal gate
  logic rather than wedging. Empty stdin handled (`raw.strip()` guard).
- **`CLAUDE_PROJECT_DIR` unset is handled** (`_claude_dir`, `:75-83`): falls back
  to `parents[1]` of the resolved file path, which is `<project>/.claude`. The
  `.sh` wrapper `exec python3`s the script in place, preserving `__file__`, so
  the fallback resolves correctly. If the env var is set but points at a
  non-dir, it correctly falls back rather than trusting it (`:81-83`).
- **Both repo copies are byte-identical.** sha256 of `hooks/antistall-gate.py`
  and `skill/antistall/hooks/antistall-gate.py` both
  `fdebc68a01bd9b7ef33459437b2e9ac461c4767244c50046b3af37f839f504a2`. The live
  customized copy is intentionally divergent (TAG `[HARD-RULE-12]`, hardcoded
  CAP/TICKET_MAX_AGE, Scott-specific wording) — structurally equivalent, same
  branch logic; not required to match.
- **Tests are non-vacuous.** Test G (`:113-131`) and live step 8 simulate the
  real harness auto-continue loop (set `stop_hook_active=True` after a block) and
  assert `blocks <= 1`. This actually exercises termination, not a tautology.
  Both suites pass (exit 0).

---

## Findings

### ENG-1 (Major) — "cross-agent race closed" is overclaimed for harnesses without `stop_hook_active`

**Evidence:** `hooks/antistall-gate.py:43-47` and README/MANUAL state the
fail-open counter closes "two agents sharing this file / mid-write race." But the
fail-open branch only triggers on an *anomaly* (unreadable / unparseable /
unwritable). The original bug's race did not require corruption: two processes
can each successfully read "0"/"1" and each write a small valid integer, pinning
the counter low **with no anomaly at all**. That parses fine (`:165`), stays
below cap, and blocks again. So for a runtime that does NOT surface
`stop_hook_active`, the documented cross-agent race is *not* fully closed by the
secondary guard — only the primary guard closes it, and that guard is exactly
what such a runtime lacks.

**Why it matters:** The whole safety story rests on "two independent guarantees."
For Claude Code (which does set `stop_hook_active`) the primary guard makes this
moot and the system is safe. But the docs assert the *secondary* guard also
defends the race, which is false. A reader deploying on a `stop_hook_active`-less
harness with shared `.claude/` would believe they are protected when they are
only protected against corruption, not against a clean concurrent low-write.

**Blast radius:** Documentation/claim accuracy + a real (if narrow) residual loop
window on non-Claude-Code harnesses with shared state. Does not affect the
shipped Claude Code use case.

**Fix:** Either (a) scope the claim: state plainly that the cross-agent race is
closed *by the `stop_hook_active` guard*, and the fail-open counter only defends
against counter *corruption*, not against a clean concurrent write that keeps the
count low; or (b) make the counter per-session/per-pid (e.g. include
`session_id` from the payload in the counter filename) so two agents don't share
it. (a) is sufficient and honest given Claude Code is the target.

### ENG-2 (Minor) — flowchart/docs name a `.sh` wrapper as the hook entry but prose calls it the hook

**Evidence:** README.md:78 / :142 and `examples/settings.json:10` wire
`antistall-gate.sh`; the diff added the new `stop_hook_active?` node into that
same flow. The wrapper exists (`hooks/antistall-gate.sh`) and correctly
`exec python3`s the `.py`. This is consistent, not a bug — but MANUAL/README
elsewhere refer to "the hook (`antistall-gate.py`)", so a reader bouncing between
`.sh` (wiring) and `.py` (logic) must infer the indirection. Pre-existing, not
introduced by this fix.

**Fix:** One sentence in MANUAL near the file tree: "`settings.json` calls the
`.sh` wrapper, which execs `antistall-gate.py`; all logic lives in the `.py`."

### ENG-3 (Minor) — `n >= cap` allows on the cap-th block, so default 6 means 5 blocks then allow; README "blocks 5 turn-ends, then lets the 6th through" is correct but the env default semantics are easy to misread

**Evidence:** `:171` `if n >= cap` with `n = int(current)+1`. With CAP=6: counts
persist 1..5, the 6th invocation computes n=6, hits the cap, allows. So 5 blocks
+ 1 allow. README/MANUAL describe exactly this. Live test step 6 seeds "5" and
asserts the next allows — matches. No correctness defect; flagging only because
the off-by-one here is the kind of thing a future edit can silently break, and
the only test pinning it (live step 6) is in the *customized* suite, not the
shipped `tests/test_gate.py` (which uses CAP=3 and only checks the cap fires at
all, not the exact boundary).

**Fix:** Add an explicit boundary assertion to `tests/test_gate.py` (seed cap-1,
assert block; seed cap-1+1 worth, assert allow) so the off-by-one is regression-locked in the shipped suite.

### ENG-4 (Nit) — fail-open `_allow` branches have unreachable `return` after `sys.exit(0)`

**Evidence:** `:162-163`, `:169-170`, `:183-184` call `_allow(...)` (which
`sys.exit(0)`s) immediately followed by `return`. The `return` is dead. Harmless,
and arguably documents intent, but it is dead code.

**Fix:** Optional — drop the `return`s or annotate `_allow` as `NoReturn`.

---

## Termination proof (adversarial summary)

| Scenario | Outcome | Bounded? |
|---|---|---|
| `stop_hook_active` present/true | allow immediately (`:133`) | Yes — ≤1 block/chain |
| `stop_hook_active` absent or always-false | counter increments, allows at cap | Yes — ≤ CAP-1 blocks |
| `stop_hook_active` always-true | allows every time | Yes (under-blocks, safe) |
| counter unreadable | allow (`:162`) | Yes |
| counter unparseable / partial write | allow + reset (`:169`) | Yes |
| counter unwritable | allow (`:183`) | Yes |
| `CLAUDE_PROJECT_DIR` unset | `parents[1]` fallback, normal logic | Yes |
| unparseable payload | `{}` → falls through, flag check | Yes |
| two agents, shared counter, NO `stop_hook_active`, clean concurrent low writes | counter pinned low, **blocks repeatedly until CAP** | Bounded by CAP only — see ENG-1 |

**Conclusion:** No sequence loops *unbounded*. On Claude Code (which sets
`stop_hook_active`) the loop is capped at one block per chain. On a flag-less
harness the only bound is CAP, and the ENG-1 residual means the cross-agent race
is bounded by CAP rather than eliminated — the docs should say so. The fix
achieves its stated goal; the overclaim is the one substantive correction.
