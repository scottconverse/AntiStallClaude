# QA Engineer — Deep Dive: Stop-hook infinite-loop fix

**Branch:** `fix/stop-hook-infinite-loop` @ `e31f858`
**Repo:** `C:/Users/scott/Desktop/Code/AntiStallClaude`
**Method:** Black-box subprocess invocation of `hooks/antistall-gate.py` with crafted stdin and env, mirroring the harness (`subprocess.run([python, gate], input=payload, env=...)`). Every documented branch exercised; observed exit codes + stdout(decision)/stderr recorded. Repo regression suite run. Three copies byte-compared.

---

## Verdict

The fix is sound and ships. Both loop guards work as designed and as documented; the regression tests prove termination non-vacuously (the bounded-loop test G actually simulates the harness auto-continue chain and asserts ≤1 block). The two in-repo copies are byte-identical. No input was found that blocks when it must allow (no loop risk) nor that allows a genuine first-attempt drift-stop. Findings are all Minor/Nit — no Blocker/Critical/Major.

---

## What's correct (credit)

- **PRIMARY loop guard (`stop_hook_active`)** — `hooks/antistall-gate.py:133-138`. Verified: armed + no ticket + stuck counter `1` + `{"stop_hook_active":true}` → exit 0, empty stdout, stderr "loop guard: stop_hook_active", and the counter file is unlinked. Race-proof: decision depends on the payload field, not on shared file state. Truthy non-bool (`"stop_hook_active":1`) also allows (correct — `.get()` truthiness).
- **SECONDARY fail-open counter** — `:154-184`. Corrupt counter (`"garbage"`) → allow (`:164-170`). Unreadable counter (directory in place of file) → allow (`:160-162`). Unwritable persist path would allow (`:179-184`). All three uncertainty paths fail OPEN, exactly inverting the old fail-closed bug.
- **Cap boundary** — default CAP=6 produces exactly 5 blocks then ALLOW on the 6th attempt; matches README "N−1 forced continuations (5 at the default)" (`README.md:192`). Off-by-one is correct.
- **Env overrides honored (repo copy)** — `ANTISTALL_BLOCK_CAP=2` capped at block 2; `ANTISTALL_TICKET_MAX_AGE_S` flips a 50s-old DONE ticket between stale→block (max=10) and fresh→allow (max=100000). `_int_env` (`:68-72`) falls back to defaults on bad input.
- **Ticket lifecycle** — single-use: any dict ticket (valid, stale, or invalid-reason `"MAYBE"`) is consumed (unlinked) on sight (`:143-144`); only fresh+valid allows. Stale DONE (age>max) → block AND consumed. Missing `ts` → age=1e9 → stale (`:147-149`).
- **Payload robustness** — non-dict JSON (`[1,2]`) and unparseable stdin both coerce to `{}` and fall through to the flag/counter path (`:115-120`); a framing change can't wedge the session.
- **Not-armed silence** — no `sprint-gate.json` → exit 0, empty stdout/stderr (`:124-125`).
- **Identical copies** — `md5sum` of `hooks/antistall-gate.py` and `skill/antistall/hooks/antistall-gate.py` match (`5f54d99b...`).
- **Regression suite** — `python tests/test_gate.py` → exit 0, all 10 cases (A–G incl. fail-open F and bounded-loop G) pass.

---

## Findings

### QA-1 (Minor) — Live customized copy ignores the env overrides
**Evidence:** `C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py:60-61` hardcodes `CAP = 6` and `TICKET_MAX_AGE = 300.0`; it has no `_int_env` helper (grep found none). The repo copies read `ANTISTALL_BLOCK_CAP` / `ANTISTALL_TICKET_MAX_AGE_S` (`hooks/antistall-gate.py:127-128`).
**Why:** The two files are intentionally divergent (different TAG `[HARD-RULE-12]` vs `[ANTI-STALL]`, Scott-specific wording), and the live copy is out of primary scope. The repo docs (`README.md:192-193`) only describe the repo artifact, so no doc is *wrong*. But the divergence means an operator who learned the env knobs from the repo cannot tune the live gate. **Blast radius:** local only; behavior at defaults is identical.
**Fix:** Either port `_int_env` into the live copy, or add a one-line comment in the live file noting the knobs are fixed there by design.

### QA-2 (Nit) — Future-dated ticket (`ts` in the future) is treated as fresh
**Evidence:** `:146-150` computes `age = time.time() - ts`; a future `ts` yields negative age, which satisfies `age < max_age`. A clock-skewed or hand-crafted future ticket would be honored.
**Why:** Negligible — the ticket is single-use and authored by the agent/operator; there's no adversary. Worth a `0 <= age < max_age` guard only for tidiness.
**Fix:** `if reason in VALID_REASONS and 0 <= age < max_age:` (optional).

### QA-3 (Nit) — `_claude_dir()` fallback resolves to the *gate's own repo* `.claude`, not the consuming project
**Evidence:** With `CLAUDE_PROJECT_DIR` unset (or pointing at a dir with no `.claude`), `:78-83` falls back to `parents[1]` = `.../AntiStallClaude` (i.e. the directory the script file lives under, not `.claude`). Confirmed `parents[1]` resolves to `...\AntiStallClaude`. In a real install the script lives at `<project>/.claude/hooks/`, so `parents[1]` correctly == `<project>/.claude`; the fallback is only "wrong" when running the repo source in place (a non-install scenario).
**Why:** Correct for the install layout it's designed for; only surprising when auditing the source tree directly. No runtime impact in production.
**Fix:** None needed; the docstring already explains the layout assumption (`:76-77`).

---

## Adversarial probes that found nothing (negative results)

- **Can it still loop?** No. With `stop_hook_active` honored, the harness chain terminates in ≤1 block (test G, 50-iteration simulation, ≤1 block). For a harness that never sets the flag, the counter climbs to CAP and escapes; and every counter-uncertainty path fails open, so the old race (read-error→reset→pin-near-1) now *allows* instead of re-blocking.
- **Over-correction (allow a real first drift-stop)?** No. First attempt with `stop_hook_active=false`, armed, no ticket → block (count→1). The gate still nudges exactly once before any continuation chain.
- **Concurrent-agent counter share:** even if two sessions share `.antistall-block-count` and increment it cleanly, it still monotonically reaches CAP (bounded). If they race and corrupt it, fail-open allows. Either way: bounded, no infinite loop.
