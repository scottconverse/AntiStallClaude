# RE-AUDIT — Verification pass (anti-stall loop-fix)

**Date:** 2026-06-17 · **Branch:** `fix/stop-hook-infinite-loop` · **HEAD:** `3309e0a`
**Scope:** confirm the prior audit's 5 Major + ~13 Minor + ~9 Nit findings are
genuinely closed in the post-fix state, and that the fixes introduced no
regressions. Style: audit-lite (single-pass, evidence-cited).

---

## Severity rollup (post-fix)

| Severity | Prior | Now | Notes |
|----------|------:|----:|-------|
| Blocker  | 0 | **0** | — |
| Critical | 0 | **0** | — |
| Major    | 5 | **0** | ENG-1, TEST-01/02/03, DOC-1 all closed |
| Minor    | ~13 | **0** | all closed (see table) |
| Nit      | ~9 | **0** | all closed |

**Verdict: 0 / 0 / 0 / 0 / 0.**

---

## Test suite output (verbatim)

```
$ python tests/test_gate.py
OK: anti-stall gate — silent / block / allow+consume / stale / future-dated / anti-loop cap /
cap-boundary / stop_hook_active loop-guard / fail-open (corrupt/empty/unreadable/unwritable) /
bounded-loop / per-session isolation / env-unset fallback / copy-identity / wrapper-smoke all pass
EXIT=0
```

All cases A–O pass (case O — `.sh` wrapper smoke — ran; bash + python3 present). Exit 0.

---

## Adversarial verification of the core claim

**Per-session counter eliminates the race (ENG-1).** `_count_path`
(`hooks/antistall-gate.py:90-99`) derives the counter filename from
`payload["session_id"]`, sanitized and truncated, as
`.antistall-block-count-<sid>`. Two distinct sessions therefore write to two
distinct files — there is no shared mutable file for two processes to race on.
This is structural, not probabilistic. Test I (`tests/test_gate.py:171-181`)
proves two session_ids produce two distinct counters and never touch the shared
base name. The PRIMARY guard (`stop_hook_active`, line 151-157) depends on no
file at all and caps nudges at 1 per continuation chain, independent of the
counter. Race closed.

**All four fail-open branches truly ALLOW (not block).** Each calls `_allow()`
(line 116-119), which writes to stderr and `sys.exit(0)` with **no**
`{"decision":"block"}` on stdout:
- unreadable (read raises) → line 183 `_allow(...)`.
- empty/whitespace → `.strip()` → `""` → `int("")` raises → line 189 `_allow(...)`.
- corrupt (non-int) → line 189 `_allow(...)`.
- unwritable (write raises) → line 201 `_allow(...)`.
- missing → `FileNotFoundError` → `current="0"` (clean 0), proceeds normally.

Tests F/F2/F3/F4 (`tests/test_gate.py:117-144`) exercise corrupt, empty,
unreadable (dir-in-place), and unwritable (read-only) respectively, all
asserting `out.strip() == ""` (no block). Confirmed fail-open.

---

## Per-finding closed/open table

| ID | Finding | Status | Evidence |
|----|---------|--------|----------|
| ENG-1 | Counter race not closed | **CLOSED** | per-session keying `antistall-gate.py:90-99`; test I:171-181 |
| TEST-01 | unreadable/unwritable untested | **CLOSED** | F3 (dir):129-134, F4 (read-only):136-144 |
| TEST-02 | concurrent race untested | **CLOSED (structurally moot)** | race eliminated by design; isolation proven by test I |
| TEST-03 | env-unset fallback untested + wrong | **CLOSED** | `_claude_dir` parents[1] `:79-87`; test M:185-193 (gate at `.claude/hooks/`, blocks) |
| DOC-1 | version still 0.1.0 | **CLOSED** | README:5, MANUAL:3, index.html:56 all `0.1.1` |
| M-1 | ticket not consumed on stop_hook_active branch | **CLOSED** | `_safe_unlink(ticket_path)` line 152; test E:114 |
| QA-2 | future-dated ticket treated fresh | **CLOSED** | `0 <= age < max_age` line 169; test C5:93-97 |
| ENG-3 | cap boundary untested | **CLOSED** | test H:162-169 (CAP=3, n=2 block, n=3 allow) |
| ENG-4 | dead return after sys.exit | **CLOSED** | `_allow` typed `-> NoReturn` (66, 116); no dead returns remain |
| N-2/F2 | empty counter untested | **CLOSED** | test F2:123-127 |
| TEST-04 | copies byte-identical untested | **CLOSED** | test N:195-197; verified all 5 files identical |
| TEST-05 | .sh wrapper untested | **CLOSED** | test O:199-211 (ran, passed) |
| DOC-2 | no upgrade notice | **CLOSED** | README:7-10; index.html:61-63 |
| DOC-3 | five-continuations unqualified | **CLOSED** | MANUAL:195 + README:199 qualify "primary caps at 1" |
| DOC-4/ENG-2/N-1 | .sh-vs-.py clarity | **CLOSED** | README:85, MANUAL:107/137-140 |
| DOC-5 | loop-guard stderr undocumented | **CLOSED** | MANUAL:219-225 |
| DOC-6 | CHANGELOG cite | **CLOSED** | CHANGELOG:42 ("`NoReturn`"); §2 Safety described |
| F-UX-1 | TAG mismatch in docs | **CLOSED** | README:185 + MANUAL:210 "or your configured TAG" |
| F-UX-2/QA-1 | live copy ignored env overrides | **CLOSED** | env read in shipped gate (72-76); copies identical (test N) |
| F-UX-3 | flow omits freshness/consume | **CLOSED** | index.html flow: "fresh (< max-age) … single-use: consumed on read" |
| F-UX-4 | status raw repr | **CLOSED** | `antistall.py:80-91` formats reason/age/detail human-readably |
| F-UX-5 | arm over-promises | **CLOSED** | `antistall.py:59-63` adds "enforced only if installed + restarted" caveat |
| NIT-1 | live copy fork undocumented | **CLOSED** | single source; byte-identical copies verified |
| NIT-2 | empty-counter comment | **CLOSED** | `antistall-gate.py:175-176` explains empty→corrupt branch |

---

## New-defect sweep (did the fixes break anything?)

- **Counter file leak (per-session files accumulate).** Each session leaves a
  `.antistall-block-count-<sid>` file. These are deleted on allow (valid ticket,
  cap-hit, loop-guard, fail-open) and `antistall.py arm/done` globs them away
  (`_clear_counts`, `antistall.py:32-38`). A session that ends mid-block-chain
  without ever allowing could orphan one tiny file. Impact: a few bytes, in
  `.claude/` (git-ignored), reaped on next arm. **Nit-below-threshold — not
  filed.**
- **Empty-string read path:** handled — `.strip()` → `int("")` raises → fail-open
  (line 184-189). Correct.
- **`NoReturn` correctness:** `_allow` always ends in `sys.exit(0)`; annotation is
  accurate and every call site treats it as terminal. Correct.
- **Doc edits:** version strings consistent (0.1.1 on README/MANUAL/index.html);
  upgrade banners present; flow diagram matches code (silent/loop-guard/ticket/
  fail-open ordering = code order lines 138-212). No broken edits found.
- **`DISCUSSIONS_SEED.md` still says "0.1.0 is here"** — this is a historical
  announcement seed for the 0.1.0 release, not a current version surface;
  appropriate to leave. Not a finding.

No new defects at or above Nit threshold.

---

## VERDICT: **SHIP**

All 5 Majors and every Minor/Nit from the prior audit are genuinely closed in
code, tests, and docs. The race is eliminated structurally (per-session counter)
rather than papered over, both loop guards are independent and fail-open, the
test suite passes 0-failures covering all four fail-open branches, the cap
boundary, per-session isolation, env-unset fallback, copy-identity, and the .sh
wrapper. The two shipped copies (`hooks/` and `skill/antistall/hooks/`) are
byte-identical across all five files. Post-fix severity is **0/0/0/0/0**.
