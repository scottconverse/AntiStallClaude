# Test Engineer Deep-Dive — anti-stall loop fix (commit e31f858)

Branch `fix/stop-hook-infinite-loop` · repo `C:/Users/scott/Desktop/Code/AntiStallClaude`
Scope: `tests/test_gate.py` (canonical) and `C:/Users/scott/Desktop/Code/.claude/hooks/test_antistall_gate.py` (live).

## Suites actually run (both PASS)

| Suite | Command | Result |
|---|---|---|
| Canonical | `python tests/test_gate.py` | exit 0 — all cases A,B,C,C2,C3,C4,D,E,F,G pass |
| Live | `python C:/Users/scott/Desktop/Code/.claude/hooks/test_antistall_gate.py` | exit 0 — 21/21 checks PASS |

Both were executed in this audit; output captured. The suites are genuine subprocess
tests (they `subprocess.run` the real gate exactly as the harness would, against a
throwaway temp project), not mocks. This is the correct shape for a hook test.

## Does case G genuinely prove termination? — YES, non-vacuously

`tests/test_gate.py` G (lines 112-131) drives the real harness auto-continue loop:
it starts `sha=False`, and on each `"decision":"block"` it sets `sha=True` so the
*next* invocation carries `stop_hook_active=true` — precisely what the Anthropic hook
contract does after a block. It counts blocks over 50 iterations and asserts `blocks <= 1`.

I verified G would FAIL if `stop_hook_active` were ignored: the gate's only other
allow paths on an armed sprint with no ticket are the CAP escape (would block 5 times
first at default cap) or fail-open (needs a corrupt/unreadable counter — not present
here). So with the loop guard removed, G would record `blocks == 6` (cap) and trip
`blocks > 1`. G is a real regression sentinel, not a vacuous pass. The live suite's
case 8 (lines 146-160) is the equivalent and is also non-vacuous. Live 2b (lines 91-98)
additionally seeds the exact looped state (counter="1", no ticket) and proves the guard
beats it — strong, targeted coverage.

## Does F prove fail-open? — PARTIALLY

Canonical F (lines 106-110) writes `"not-a-number"` and asserts allow. This proves the
**corrupt-parse** fail-open branch (gate lines 164-170). Live case 7 (lines 137-141)
is identical. Confirmed non-vacuous: if the corrupt branch blocked instead of allowed,
F's `out.strip()==""` assertion would fail.

BUT "fail-open" has THREE branches in the gate and only ONE is tested:
- corrupt/unparseable counter (gate 164-170) — **tested** (F / live 7)
- **unreadable** counter, e.g. permission error (gate 160-162) — **NOT tested**
- **unwritable** counter, cannot persist (gate 181-184) — **NOT tested**

The two untested branches are the ones most likely to regress silently because they
depend on OS-level IO failure that a refactor could swallow. F does not prove the full
fail-open contract the header comment (gate lines 43-47) claims.

## What is NOT covered (gaps)

1. **Cross-process concurrent counter race — UNTESTED and demonstrably real.** I ran 10
   near-simultaneous blocking invocations against one project dir; the counter landed at
   **4, not 10** (lost read-modify-write updates). This is the exact race the bug report
   blamed for pinning the old counter near 1. The PRIMARY `stop_hook_active` guard makes
   it benign in the real harness, but the SECONDARY counter remains racy and no test
   asserts behavior under concurrency. A harness that never sets `stop_hook_active`
   (the case live 8b exists for) running two agents could still mis-cap. Worth at least
   one test documenting the known limitation.

2. **`CLAUDE_PROJECT_DIR` unset → `parents[1]` fallback — UNTESTED, and the fallback is
   subtly wrong for the repo layout.** Both suites ALWAYS set `CLAUDE_PROJECT_DIR`
   (canonical line 27, live line 28), so the fallback at gate lines 78-83 is never
   exercised. I ran the canonical gate with the var unset: `parents[1]` resolves to the
   **repo root** (`.../AntiStallClaude`), not a `.claude` dir, so it finds no
   `sprint-gate.json` and silently exits 0. The fallback only works when the gate is
   physically installed at `<project>/.claude/hooks/`. For the in-repo path it
   fails-silent. No test catches this; a test should assert the fallback against a gate
   copied into a `.claude/hooks/` layout.

3. **`.sh` wrapper — UNTESTED.** `hooks/antistall-gate.sh` (and the skill copy) `exec
   python3 "$DIR/antistall-gate.py"`. If a harness is wired to the `.sh` entrypoint, none
   of it is covered. On Windows `python3` may not resolve at all. No smoke test invokes
   the wrapper.

4. **Empty-string counter** ("" written by a truncating writer mid-rotate): I confirmed it
   hits the corrupt branch and fails open (good), but it is untested. Easy add.

5. **Two copies' divergence is UNVERIFIED by any test.** The canonical and skill copies
   are byte-identical (I diffed them). The **live** copy is intentionally different
   (TAG `[HARD-RULE-12]`, hardcoded `CAP=6`/`TICKET_MAX_AGE=300.0`, no env overrides). No
   test asserts the two shipped copies (`hooks/` vs `skill/antistall/hooks/`) stay in
   sync — a drift between them would ship silently. Recommend a one-line identity test.

6. **Counter-not-reset-on-allow-via-ticket while counter present** is covered (C3/C4
   unlink count first), but the interaction "block to 5, then valid ticket resets to
   gone" is not asserted as a sequence.

## Highest-value missing tests (recommended, ranked)

1. **Copy-identity test**: assert `hooks/antistall-gate.py` == `skill/antistall/hooks/
   antistall-gate.py` byte-for-byte. One assert; prevents silent skill-copy drift.
2. **`CLAUDE_PROJECT_DIR`-unset fallback test**: copy the gate into a temp
   `<proj>/.claude/hooks/`, unset the env var, arm a sprint, assert it still blocks.
   Proves the self-locating claim that production relies on.
3. **Unreadable + unwritable fail-open tests**: chmod the counter file (or its dir) and
   assert allow. Covers the two untested fail-open branches the header promises.
4. **Concurrency limitation test**: spawn N parallel blocking invocations with
   `stop_hook_active=false`; assert the loop still terminates within a bound (documents
   the known race rather than leaving it implicit).
5. **`.sh` wrapper smoke test** (skip cleanly if `python3`/bash unavailable).

## What's correct (credit)

- Both suites run the real subprocess against an isolated temp dir — the right
  methodology for a Stop hook; no internal mocking that could mask integration breakage.
- Case G / live case 8 genuinely simulate the harness auto-continue loop and WOULD fail
  if `stop_hook_active` were ignored — the central fix is protected by a real sentinel.
- Live 2b seeds the precise historical loop state (counter="1", armed, no ticket) — a
  strong targeted regression guard.
- Ticket lifecycle is well covered: fresh DONE/BLOCKED/QUESTION allow+consume (C,C3,C4 /
  live 4), stale-consumed-then-block (C2 / live 5), invalid-reason-block (live 5b).
- CAP escape hatch covered both via env-tuned cap=3 (canonical D) and seeded counter=5
  (live 6), plus counter-reset-after-cap (live 6).
- Corrupt-counter fail-open is asserted non-vacuously in both suites.
- The two in-scope copies (canonical + skill) are byte-identical — verified by diff.

## Verdict

The tests genuinely prove the PRIMARY fix (stop_hook_active loop guard) and the
corrupt-counter fail-open branch; case G is a real, non-vacuous termination sentinel.
They do NOT prove the full fail-open contract (2 of 3 branches untested), the
self-locating fallback, copy-sync, or the `.sh` path, and they leave the still-racy
secondary counter undocumented. No false greens, but coverage gaps are Major.
