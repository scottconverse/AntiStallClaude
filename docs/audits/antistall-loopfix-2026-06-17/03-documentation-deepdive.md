# Documentation Deep-Dive — AntiStallClaude loop-fix (branch `fix/stop-hook-infinite-loop`, commit e31f858)

**Role:** Technical Writer
**Date:** 2026-06-17
**Scope:** README.md, docs/MANUAL.md, docs/index.html, CHANGELOG.md (0.1.1), cross-checked against
`hooks/antistall-gate.py`, `skill/antistall/hooks/antistall-gate.py`, `tests/test_gate.py`, and the
live customized copy `C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py`.

**Verdict (one line):** The prose claims about the two guards, the one-nudge-per-chain cap, and
`stop_hook_active` are now accurate and no longer overclaim that the cap alone guarantees escape — but
the user-facing **version string is still `0.1.0`** on three surfaces, and the "earlier versions should
update" warning is **missing from the README and landing page** (the two highest-traffic surfaces).

---

## Severity counts
- Blocker: 0
- Critical: 0
- Major: 1
- Minor: 3
- Nit: 2

---

## Findings

### DOC-1 (Major) — Version string still reads `0.1.0` on README, MANUAL, and landing page after shipping the 0.1.1 fix
**Evidence:**
- `README.md:5` — `Version 0.1.0 · MIT licensed …`
- `docs/MANUAL.md:3` — `Version 0.1.0`
- `docs/index.html:56` — `<div class="tag">v0.1.0 · MIT · Claude Code &amp; Cowork</div>`
- `CHANGELOG.md:7` — `## [0.1.1] — 2026-06-17` documents this exact loop-fix as the current release.

**Why it matters:** The loop bug is the *defining* defect of 0.1.0. A new adopter who pulls the fix and
opens the README, manual, or landing page sees "0.1.0" — the version that still has the infinite-loop
bug — with no indication they are on the patched build. The version that is the headline of the whole
changelog entry is invisible everywhere the user actually looks. This is precisely the drift a doc
audit exists to catch: the code moved, the version metadata did not.

**Blast radius:** Three docs; user trust / "do I have the fix?" ambiguity. No code impact.
**Fix:** Bump the three version strings to `0.1.1` (README:5, MANUAL:3, index.html:56). Consider a
machine-checkable single source of version truth so this cannot drift again.

---

### DOC-2 (Minor) — "Earlier versions should update" warning is absent from README and the landing page
**Evidence:** The role asks specifically whether this warning is present and clear. It is:
- `CHANGELOG.md:26` — **bold**: "**Anyone running an earlier `antistall-gate.py` should update.**" (clear)
- `docs/MANUAL.md:78-82` — a ⚠️ warning box: "If you carried an older copy of `antistall-gate.py`, replace it." (clear)

It is **absent** from `README.md` (the two-guard prose at lines 51-65 has no update notice) and from
`docs/index.html` (the "How it works" safety paragraph at 104-108 has no update notice). `grep -niE
"earlier|older|update|replace|upgrade"` over README.md and index.html returns no security/upgrade
warning — only the unrelated "stop-ticket older than this is stale" row and the version tags.

**Why it matters:** README and the landing page are the highest-traffic surfaces and the ones a casual
adopter reads; the people most likely to be carrying a vulnerable 0.1.0 copy are the least likely to
read CHANGELOG/MANUAL §2. The warning that exists is good, but it is hidden from the audience that
needs it most.
**Blast radius:** Two docs; adopters on the buggy version may not learn to update.
**Fix:** Add a one-line upgrade notice to README (e.g. near the runtime-support callout or in a short
"0.1.1 — loop fix; update if you carried 0.1.0" note) and a short banner/line on index.html.

---

### DOC-3 (Minor) — On the only *verified* runtimes the effective nudge count is 1, but the cap docs describe "five forced continuations" without that framing
**Evidence:** Code: `hooks/antistall-gate.py:133-138` allows immediately when `stop_hook_active` is
true (Claude Code / Cowork — the only verified runtimes per README:13-14 and MANUAL §8). The cap path
(`:171` `if n >= cap`, cap=6) only executes on a runtime that does **not** surface the flag. README:192
and MANUAL:191 accurately describe the cap as "N−1 forced continuations (5 at the default)".

**Why it matters:** The math is correct, but a reader on Claude Code/Cowork could infer they will be
nudged up to five times before escape, when in reality the primary guard caps them at exactly **one**
nudge per chain. The "five" only applies to a hypothetical unverified runtime. The two facts sit in
different sections and are never reconciled.
**Blast radius:** Reader expectation only; no inaccuracy, just an unstated qualifier.
**Fix:** In the `ANTISTALL_BLOCK_CAP` rows (README:192, MANUAL:191) add a clause like "—
only reached on a runtime that does not surface `stop_hook_active`; on Claude Code/Cowork the primary
guard caps nudges at 1."

---

### DOC-4 (Minor) — README/landing flowchart label `antistall-gate.sh`; the in-scope fixed artifact is `antistall-gate.py`
**Evidence:** `README.md:78` (`harness runs .claude/hooks/antistall-gate.sh`), `README.md:142-143`
(settings.json wires the `.sh`), `docs/index.html:92` (`harness runs antistall-gate`). MANUAL §3
(`:98-104`) correctly documents both the `.py` (enforcement) and the `.sh` (self-locating wrapper).

**Why it matters:** This is *consistent and correct* (the harness calls the `.sh` wrapper, which
invokes the `.py`), so it is not a drift — but the audit prompt centers the `.py` as "the primary
artifact," and a reader comparing the flowchart label to the fixed file could briefly wonder whether
the fix landed in the wrong file. Worth a one-word clarification, not a correction.
**Blast radius:** Momentary reader confusion; no inaccuracy.
**Fix:** Optional — annotate the flowchart node as `antistall-gate.sh → .py` once, or footnote that
the `.sh` is a thin wrapper.

---

### DOC-5 (Nit) — `stop_hook_active` `_allow` stderr note is not surfaced in user-facing docs as the observable signal
**Evidence:** Code `:135-138` emits a distinctive stderr line ("stop ALLOWED (loop guard:
stop_hook_active)..."). The behavioral-test sections (README:172-180, MANUAL §7) tell the user what
they will see on a *block* (`[ANTI-STALL] … KEEP WORKING`) but never describe what the loop-guard
allow looks like. A user debugging "why did it let me stop on the second try?" has no documented signal
to look for.
**Fix:** Optional — mention the loop-guard stderr line in MANUAL §7 troubleshooting.

---

### DOC-6 (Nit) — CHANGELOG 0.1.1 cites `MANUAL §"Safety"`; the actual heading is §2's sub-section "Safety: why the gate can never loop or trap a session"
**Evidence:** `CHANGELOG.md:25` — "Docs corrected (README, MANUAL §"Safety")". MANUAL has no top-level
"Safety" section; the safety prose is a sub-heading under `## 2. Design` (`docs/MANUAL.md:58`). Minor
citation imprecision; a reader scanning the MANUAL TOC for "Safety" finds nothing.
**Fix:** Cite "MANUAL §2 (Safety subsection)".

---

## What's correct (credit where due)

- **The core overclaim is fixed.** No doc surface now says or implies the cap *alone* guarantees
  escape. README:51-65, MANUAL §2:58-82, and index.html:104-108 all present **two independent guards**
  with `stop_hook_active` as primary and the fail-open cap as secondary. The headline failure-mode prose
  is accurate.
- **`stop_hook_active` behavior is described accurately.** "Always allows the stop … nudges a drift-stop
  at most once per continuation chain" (README:56-60, MANUAL:65-70, index.html:104-106) matches the code
  exactly (`:133-138` unconditional allow on the flag, race-proof because it reads no shared mutable
  file). The "one nudge per chain" claim is precise.
- **Fail-open semantics are described accurately.** "any uncertainty about that counter (unreadable,
  corrupt, or two agents racing) allows the stop" (README:61-65, MANUAL:71-76) matches the three
  fail-open branches in code (`:160-162` unreadable, `:166-169` corrupt, `:181-183` unwritable).
- **The bug narrative in CHANGELOG 0.1.1 is technically faithful** — "failed closed: any read error
  reset it to 0, so it never reached the cap … pinned the counter near 1" matches the described old
  behavior and the new `:158-162` fail-open contrast.
- **The cap math is internally consistent and correct.** `cap=6` blocks at n=1..5 then allows at n=6;
  README:192 ("N−1 forced continuations") and MANUAL:191 ("5 at the default") both compute correctly
  against code `:171`.
- **The two repo hook copies are byte-identical** — verified `md5sum` `5f54d99b…` for both
  `hooks/antistall-gate.py` and `skill/antistall/hooks/antistall-gate.py`. The docs that assume one
  canonical hook are not contradicted.
- **The tests prove termination, not vacuously.** Test G (`tests/test_gate.py:111-131`) simulates the
  real harness auto-continue loop (sets `stop_hook_active=true` after the first block) and asserts
  `blocks <= 1`; test E asserts the flag forces allow even with a stuck counter; test F asserts
  fail-open on a corrupt counter. Suite passes (`python tests/test_gate.py` → exit 0).
- **The runtime-support honesty callout** (README:7-14, MANUAL §8) correctly limits verified support to
  Claude Code and Cowork and names Codex/Gemini CLI/Copilot CLI as explicitly unverified — no
  portability overclaim.
- **The live customized copy** (`C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py`) carries
  the same two-guard logic (`:121-126` flag guard, `:145-173` fail-open counter) under Hard-Rule-12
  wording — functionally faithful to the shipped fix; its docs are the project CLAUDE.md rule, which
  matches.
