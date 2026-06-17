# Walkthrough / Wiring-Contract Audit — Anti-Stall Stop-Hook Loop Fix

- **Branch / commit:** `fix/stop-hook-infinite-loop` @ `e31f858`
- **Repo:** `C:/Users/scott/Desktop/Code/AntiStallClaude`
- **Role:** walkthrough (audit mode). **There is NO UI to drive** — this artifact is a headless
  Claude Code CLI **Stop** hook (a `.py` invoked by a `.sh` wrapper from `settings.json`). A
  Playwright/click-through walkthrough is therefore **not applicable**. In its place this report
  performs the rigorous **static wiring / contract cross-check** the role requires, plus **live
  execution** of both test suites and a hand-run of the loop and cap arithmetic.
- **Date:** 2026-06-17

---

## Method

Read in full (not just the diff): `hooks/antistall-gate.py`, `skill/antistall/hooks/antistall-gate.py`,
`tests/test_gate.py`, `hooks/antistall-gate.sh`, `install.py`, README.md / docs/MANUAL.md /
docs/index.html / CHANGELOG.md (relevant sections), and the live customized copy
`C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py` with its test
`C:/Users/scott/Desktop/Code/.claude/hooks/test_antistall_gate.py`. Ran both suites; hand-simulated
the harness auto-continue loop and the cap counter externally.

---

## Stop-hook contract conformance (Claude Code)

| Contract requirement | Implementation | Verdict |
|---|---|---|
| Read the Stop payload from **stdin** | `sys.stdin.read()` then `json.loads`, both wrapped, non-dict/parse-fail → `{}` (`antistall-gate.py:110-120`) | PASS |
| Use `stop_hook_active` to detect a block-induced continuation | `if payload.get("stop_hook_active"):` → unconditional allow (`:133-138`) | PASS |
| Signal "keep going" via `{"decision":"block"}` on **stdout** | `print(json.dumps({"decision":"block","reason":...}))` (`:195`) | PASS |
| **Always exit 0** (block is via JSON, not exit code 2) | every path calls `sys.exit(0)` or `_allow`→`sys.exit(0)`; no exit 2 anywhere | PASS |
| Stay silent when ungated | flag not active → bare `sys.exit(0)`, no stdout (`:124-125`) | PASS |

The `stop_hook_active` semantics are honored exactly as documented by Anthropic: the field is set
true on a Stop that is itself the product of a prior block, and the hook treats that as an
unconditional allow — capping at one nudge per continuation chain.

## Wiring chain (settings.json → .sh → .py)

- **Live `settings.json`** wires `Stop` to `"$CLAUDE_PROJECT_DIR"/.claude/hooks/antistall-gate.sh`
  (verified by parsing `C:/Users/scott/Desktop/Code/.claude/settings.json`). The matcher entry is
  intact and the only Stop entry.
- **`antistall-gate.sh`** self-locates (`DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`) and
  `exec python3 "$DIR/antistall-gate.py"` — it does exec the `.py`, and is robust to
  `CLAUDE_PROJECT_DIR` being unset. PASS.
- **`install.py`** copies the FIXED hook from the correct source dir
  (`_src_hooks() = <repo>/hooks`, `:_src_hooks`), copies all five hook files, chmods the `.sh`,
  and merges Stop/SessionStart into `settings.json` idempotently with a backup and a
  refuse-on-invalid-JSON guard. The `GATE_CMD` it writes matches the live wiring. PASS.

## Two copies identical?

`md5sum` of `hooks/antistall-gate.py` and `skill/antistall/hooks/antistall-gate.py` are **identical**
(`5f54d99b…`), and `diff` reports no differences. The live copy at
`C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py` is intentionally a **customized**
variant (TAG `[HARD-RULE-12]` vs `[ANTI-STALL]`, hard-coded `CAP=6`/`TICKET_MAX_AGE=300` instead of
env overrides, Scott-specific reason wording). Its control flow is logically equivalent: same branch
order, same `stop_hook_active` primary guard, same fail-open counter, same exit-0/stdout-block
contract. This is expected and correct per the role brief ("same fix, different TAG/wording").

## Test results (actually run)

- `python3 tests/test_gate.py` → **exit 0**, "OK: … all pass" (cases A–D plus new E `stop_hook_active`
  allow, F corrupt-counter fail-open, G bounded-loop ≤1 block).
- `python3 C:/Users/scott/Desktop/Code/.claude/hooks/test_antistall_gate.py` → **exit 0**, 21/21 PASS,
  including the two boundedness tests (≤1 block with `stop_hook_active`; <CAP blocks without it).

**Do the tests prove termination (not vacuously)?** Yes. Both suites contain an explicit harness-loop
simulation (repo G: 50-iteration loop, asserts `blocks <= 1`; live #8/#8b: same plus the
no-`stop_hook_active` path asserting `< CAP`). Independently hand-verified: with `stop_hook_active`
always false and default cap, the gate blocks exactly 5 times and **allows on the 6th attempt** — it
cannot loop unboundedly on either path.

## Adversarial probing

- **Can it still loop?** No, on two independent grounds. (1) Any harness that surfaces
  `stop_hook_active` caps at one block. (2) A harness that never sets it falls to the fail-open
  counter, which terminates at CAP and **fails open** on every counter anomaly
  (FileNotFound→0 baseline, unreadable→allow, corrupt int→allow+reset, unwritable→allow). I traced
  every `except` in the counter block (`:156-184`): there is no path that re-blocks on counter
  uncertainty.
- **Over-correction (lets a real drift-stop through too easily)?** Mild and by design. The primary
  guard means the gate nudges **at most once** per continuation chain — a determined drift-stop that
  blocks once, gets continued, then immediately tries to stop again with `stop_hook_active=true` is
  allowed through. This is the deliberate, documented trade (loop-safety over infinite nudging) and
  is stated plainly in README/MANUAL/index.html and the file header. Not a defect.
- **Doc/code drift?** Verified the cap arithmetic claim ("allowed on the Nth attempt after N−1
  continuations; 5 at the default") matches observed behavior (allowed at attempt 6 after 5 blocks).
  README/MANUAL/index.html flow diagrams, the `stop_hook_active` description, the fail-open language,
  and the CHANGELOG 0.1.1 entry all match the code. No overclaim remains; MANUAL explicitly retracts
  the prior "cap alone" guarantee.

---

## What's correct (credit)

- Stop-hook contract fully honored: stdin read, `stop_hook_active` checked, `decision:block` on
  stdout, exit 0 on every path, silent when ungated.
- Primary guard is genuinely race-proof — depends on a payload field, no shared mutable file.
- Counter fails **open** on every anomaly; the previous fail-closed bug is fully inverted.
- Ticket is consumed-on-sight (valid or not), preventing a stale ticket from lingering.
- Wiring chain intact end to end; `install.py` copies the fixed hook from the right source.
- Two distributed copies byte-identical; live copy a deliberate, logically-equivalent customization.
- Both test suites pass and prove boundedness non-vacuously on both the `stop_hook_active` and
  cap-only paths.
- Docs are accurate and the CHANGELOG honestly describes the prior bug.

## Findings

No Blocker / Critical / Major findings. Two Nits below.

### NIT-1 — Distributed copy vs customized live copy can confuse a code-reader
- **Severity:** Nit
- **Evidence:** `hooks/antistall-gate.py` uses TAG `[ANTI-STALL]` and env-configurable
  `ANTISTALL_BLOCK_CAP`/`ANTISTALL_TICKET_MAX_AGE_S`; the live copy
  `C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py:59-61` hard-codes `CAP=6` /
  `TICKET_MAX_AGE=300` and TAG `[HARD-RULE-12]`. Both are correct; the divergence is intentional but
  undocumented in-tree.
- **Blast radius:** Documentation/maintenance only — no runtime effect.
- **Fix:** Add a one-line header comment in the live copy noting it is a hand-customized fork of the
  AntiStallClaude `hooks/antistall-gate.py` (different TAG and hard-coded constants), so a future
  editor knows to keep the loop-safety logic in sync.

### NIT-2 — Counter `read_text` newline tolerance is implicit
- **Severity:** Nit
- **Evidence:** `antistall-gate.py:157` does `.read_text(...).strip()` then `int(current)+1`. A
  counter file containing only whitespace (`""` after strip) would hit the corrupt-int branch and
  fail open — correct, but relies on `int("")` raising. This is fine; just under-commented relative
  to the explicit FileNotFound and corrupt-write cases.
- **Blast radius:** None (behavior is correct: fail-open).
- **Fix:** Optional — note in the comment that an empty/whitespace counter also routes to fail-open.

---

## Verdict

**Ship.** The fix correctly honors the Claude Code Stop-hook contract, the wiring chain is intact,
`install.py` sources the fixed hook, the two distributed copies are byte-identical, the live
customized copy is logically equivalent, both test suites pass and prove termination
non-vacuously, and every doc claim matches behavior. Only two Nits, neither blocking.
