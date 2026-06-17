# Audit Lite — anti-stall Stop-hook loop fix

**Scope:** branch `fix/stop-hook-infinite-loop` @ `e31f858`, repo
`C:/Users/scott/Desktop/Code/AntiStallClaude`.
**Method:** read full files (not just diff); ran both test suites; byte-compared
the two repo copies; adversarially probed for residual loop / over-correction.
**Verdict: SHIP.** No Blocker/Critical. Two Minor, two Nit. No escalation to
audit-team warranted.

---

## What's correct (credit where due)

- **The core fix is sound and addresses the root cause.** The primary guard
  (`hooks/antistall-gate.py:133`) honors `stop_hook_active` and allows
  unconditionally — this caps the gate at one block per continuation chain and,
  critically, **depends on no shared mutable file**, so it is genuinely immune
  to the cross-agent `.antistall-block-count` race that caused the original
  loop. This is the right design, not a band-aid.
- **The secondary guard truly fails open now.** Every counter anomaly path —
  unreadable (`:160-162`), unparseable (`:164-170`), unwritable (`:179-184`) —
  calls `_allow()` and returns. The old fail-closed reset-to-0 behavior is gone.
- **Defense in depth is real, not cosmetic.** The two guards are independent: #1
  covers harnesses that surface `stop_hook_active`; #2 bounds the loop at CAP for
  any harness that doesn't. Either alone terminates the loop.
- **Tests actually prove termination (not vacuous).** `tests/test_gate.py` case
  G (`:113-131`) and the live `test_antistall_gate.py` case 8 (`:143-160`)
  *simulate the real harness auto-continue loop* — they set `stop_hook_active`
  true after a block and assert `blocks <= 1`. Case 8b (`:162-176`) proves
  CAP-bounded termination when the flag is absent. These are the right
  assertions; they would fail if the loop regressed. Both suites: **ALL PASS**
  (verified by running them).
- **The two repo copies are byte-identical** — `md5sum` of
  `hooks/antistall-gate.py` and `skill/antistall/hooks/antistall-gate.py` both
  `5f54d99b4b033a6307646dd8fe7abe66`; `diff` reports identical.
- **The live customized copy** (`C:/Users/scott/Desktop/Code/.claude/hooks/`)
  carries the same logic with project-specific TAG/wording, and its test suite
  passes all 21 checks.
- **Docs were corrected honestly.** README, MANUAL §Safety, index.html, and
  CHANGELOG all now state the cap is *not* the sole guarantee and document the
  old fail-closed defect plainly ("**replace it**"). The diagrams in all three
  doc surfaces gained the `stop_hook_active` branch in the correct position.

---

## Findings

### M-1 (Minor) — A valid stop-ticket is left unconsumed when `stop_hook_active` is true
**Evidence:** `hooks/antistall-gate.py:133-138` allows and `sys.exit(0)`s before
the ticket-consumption block at `:141-152`. If the agent writes a DONE/BLOCKED/
QUESTION ticket on a turn that is itself a continuation (`stop_hook_active`
true), the ticket file is never deleted.
**Why it matters:** the ticket persists into the next turn. If the sprint is
still armed and the agent stops again >0s later with `stop_hook_active` false,
the stale (but possibly still-fresh, <300s) ticket will be consumed then and
allow that stop — a stop the operator may not have re-authorized. Low
likelihood (requires a ticket written precisely on a continuation turn) and the
stop was already allowed this turn, so impact is one extra un-nudged stop within
the 300s window.
**Blast radius:** single session, one turn-end; bounded by `TICKET_MAX_AGE`.
**Fix:** in the `stop_hook_active` branch, also `_safe_unlink(ticket_path)`
before `_allow(...)` (read `ticket_path` first or unlink unconditionally).

### M-2 (Minor) — Entire primary guarantee rests on an unverified harness contract
**Evidence:** `:133` `payload.get("stop_hook_active")`. The comment at `:37-42`
asserts "The agent harness sets this field to true on a Stop that is itself the
result of a previous block." This is the documented Claude Code contract, but
the hook has no way to confirm the running harness honors it.
**Why it matters:** if a harness never sets the flag (or sets it false on
continuations), guard #1 silently does nothing and ALL protection falls to the
fail-open counter — which is exactly the component that failed in the original
bug. The counter is now fail-open so it cannot *loop*, but it also means in that
scenario the gate degrades to "block up to CAP-1 times then give up," which is
the weaker pre-fix posture (minus the loop). This is inherent and acceptable,
but the "two INDEPENDENT guarantees" framing slightly oversells: #1's value is
contingent on a contract the code cannot enforce.
**Blast radius:** correctness/robustness on non-conforming harnesses only.
**Fix:** none required; optionally note in MANUAL that #1 requires the harness
to honor `stop_hook_active` and #2 is the floor when it doesn't.

### N-1 (Nit) — Stale `.sh` wrapper references in docs (pre-existing, not introduced)
**Evidence:** `README.md:78,142-143`, `docs/MANUAL.md:100,102,133` reference
`antistall-gate.sh` / `antistall-session-start.sh` wrappers. Not touched by this
fix; flagged only because the audit read the full doc files.
**Fix:** out of scope for this branch; confirm the `.sh` wrappers still exist in
the install path or reconcile docs in a separate change.

### N-2 (Nit) — `tests/test_gate.py` case B asserts counter only `if count.exists()`
**Evidence:** `tests/test_gate.py:56` — `if count.exists() and ... != "1"`. If a
regression caused the counter never to be written, the `count.exists()` guard
makes the count assertion silently pass (the block assertion at `:54` still
catches a missing block, so this is harmless today).
**Fix:** assert `count.exists()` is true after a block, then assert its value.
(The live `test_antistall_gate.py:104` does this correctly.)

---

## Adversarial probes (results)

- **Can it still loop?** No. With `stop_hook_active` honored, terminates in ≤1
  block (test G/8 prove it). Without it, terminates at CAP; every counter
  anomaly fails open. No code path re-blocks indefinitely.
- **Over-correction — does it now let real drift-stops through?** Only (a) on a
  continuation chain (one nudge by design) or (b) on a counter anomaly. Both are
  deliberate, bounded, and logged to stderr. Acceptable.
- **Are the two copies identical?** Yes (md5 match).
- **Do tests pass vacuously?** No — G/8 simulate the actual harness loop and
  assert a hard bound; they would fail on regression.
- **Are doc claims accurate?** Yes, with the minor caveat in M-2.

## Escalation recommendation
**No escalation.** Findings are Minor/Nit; the fix is correct and well-tested.
Address M-1 (one-line unlink) opportunistically; it does not block ship.
