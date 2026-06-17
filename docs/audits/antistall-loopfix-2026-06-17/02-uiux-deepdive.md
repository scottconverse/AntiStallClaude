# UI/UX Designer deep-dive — AntiStallClaude loop-fix (branch `fix/stop-hook-infinite-loop`, commit e31f858)

Role: UI/UX Designer. Scope is deliberately narrow: this artifact has almost no visual surface.
The only "UI" is (a) the static landing page `docs/index.html`, (b) the operator-facing TEXT of the
hook's block/allow stderr messages, and (c) the `arm/done/blocked/question/status` helper CLI ergonomics.
I assessed readability/accuracy of the flow diagram, clarity/actionability/tone of the `[ANTI-STALL]`
messages, and CLI ergonomics. I read the full files, not just the diff.

## Scope honesty
There is no rendered/interactive UI to drive (no Playwright target). The landing page is a single static
HTML file with inline CSS and no JS. So this review is mostly copy/UX-of-text, not visual QA. I credit
that the team kept the surface tiny and dependency-free.

---

## What's correct (credit where due)

- **Flow diagram is now accurate to the code.** `docs/index.html:92-103` renders the exact decision order
  the code executes: sprint armed? → `stop_hook_active`? → fresh ticket? → cap/corrupt? → block. This matches
  `hooks/antistall-gate.py` `main()` ordering (flag check L124, `stop_hook_active` L133, ticket L142-152,
  counter L156-184, block L195). The new `stop_hook_active` branch and the fail-open ("counter unreadable/corrupt
  → allow") branch are both present in the diagram (L96, L100). The README ASCII diagram agrees
  (`README.md:84,92`). Prior to the fix these branches did not exist; the doc was updated in lockstep.
- **Block message is genuinely actionable.** `hooks/antistall-gate.py:186-194` tells the operator/agent the
  exact file to write, the exact JSON shape, and defines DONE/BLOCKED/QUESTION inline. It ends with `Block n/cap`
  so the reader sees loop progress. This is a strong, self-documenting nudge.
- **Allow messages explain *why* a stop was permitted** (loop guard / ticket / cap / fail-open), each on one
  stderr line — good for log forensics. See L135-137, L152, L162, L169, L173-177, L183.
- **Tone is non-alarming and directive.** "KEEP WORKING — finish the next concrete step" is imperative without
  being punitive. No scary words, no all-caps shouting beyond the one verb.
- **CLI help is excellent.** `hooks/antistall.py:6-18` documents every subcommand with the side effect spelled
  out (arm blocks drift-stops; done also clears the flag; blocked/question stay armed). The landing page
  "Use it" block (`index.html:122-126`) mirrors it with realistic example notes.
- **"Honest about limits" section** (`index.html:129-135`, MANUAL §8) is a model of trustworthy product copy:
  it states the spoofability limit plainly rather than overselling.
- **The cap arithmetic in MANUAL is correct.** §6 (`MANUAL.md:191`) says cap=6 ⇒ allowed on the 6th attempt
  after 5 forced continuations. Code: `n = current+1; if n >= cap: allow` blocks at n=1..5 and allows at n=6.
  Accurate.

---

## Findings

### F-UX-1 — Message TAG mismatch between repo copy and live copy will confuse operators following the docs (Minor)
- **Evidence:** Repo hook emits `[ANTI-STALL]` (`hooks/antistall-gate.py:64`). The live customized copy emits
  `[HARD-RULE-12]` (`C:/Users/scott/Desktop/Code/.claude/hooks/antistall-gate.py`, `RULE=12`, `_allow` writes
  `[HARD-RULE-{RULE}]`). The MANUAL behavioral test (`MANUAL.md:205`) and README (`README.md:178`) instruct the
  reader to look for `[ANTI-STALL] … KEEP WORKING`. An operator on the live project box who runs the §7 test will
  see `[HARD-RULE-12] …`, not `[ANTI-STALL] …`, and may conclude the hook is "not firing" (the doc's own failure
  signal). This is an intentional customization per audit scope, but the docs don't warn the reader the tag is
  configurable/varies.
- **Why it matters (UX):** The single most important diagnostic string in the manual is the literal tag, and it's
  presented as fixed. Tag drift between distributions silently breaks the "prove it fires" ritual.
- **Blast radius:** Documentation/operator-trust only. No functional impact.
- **Fix:** In MANUAL §7 and README, phrase the expected output as "blocked with a `[ANTI-STALL]` (or your
  configured tag) … KEEP WORKING line," or note the TAG constant is editable. Alternatively hoist TAG to an env
  var so the customization doesn't require editing the file.

### F-UX-2 — Env-var config documented in MANUAL but absent from the live copy / not surfaced on the landing page (Minor)
- **Evidence:** MANUAL §6 documents `ANTISTALL_BLOCK_CAP` and `ANTISTALL_TICKET_MAX_AGE_S`
  (`MANUAL.md:189-195`), and the repo hook honors them (`hooks/antistall-gate.py:68-72,127-128`). The live copy
  hard-codes `CAP=6` / `TICKET_MAX_AGE=300.0` with no env override, so on the live box those documented knobs do
  nothing. The landing page never mentions configuration at all (a reader who only reads the page won't know the
  cap is tunable).
- **Why it matters (UX):** A documented control that silently no-ops on one shipped copy erodes trust; an operator
  who sets `ANTISTALL_BLOCK_CAP=3` on the live project gets the default 6 with no error.
- **Blast radius:** Config predictability on the customized deployment.
- **Fix:** Either backport the `_int_env` overrides into the live copy, or scope the MANUAL claim to "the
  distributed hook" and note customized installs may hard-code values. Out of strict UI scope but it's a copy/accuracy issue.

### F-UX-3 — Flow diagram omits the stale/invalid-ticket path; reads as if any ticket is consumed-and-allowed (Minor)
- **Evidence:** Diagram node `index.html:98`: "fresh DONE/BLOCKED/QUESTION ticket? — yes → consume, allow."
  The code consumes the ticket file **even when stale or invalid** (`antistall-gate.py:144` unlinks before the
  freshness check at L150) and then falls through to the counter/block path. The diagram's single yes/no branch
  hides that a stale ticket is silently eaten and you still get blocked. An operator who wrote a ticket 6 minutes
  ago (> 300s) will be confused: the diagram implies "ticket present → allowed."
- **Why it matters (UX):** The diagram is the primary mental model on the page. The stale-ticket-still-consumed
  behavior is exactly the kind of surprise that diagrams exist to prevent.
- **Blast radius:** Reader comprehension; minor support burden ("I wrote a ticket and it still blocked me").
- **Fix:** Add a qualifier to the node, e.g. "fresh (< max-age) ticket?" and a footnote that any ticket file is
  single-use/consumed on read. The MANUAL already implies single-use (`MANUAL.md` "authorizes exactly ONE turn-end");
  mirror that on the page.

### F-UX-4 — `status` output is machine-ish, not operator-friendly (Nit)
- **Evidence:** `hooks/antistall.py:74` prints `armed={armed} note={note!r} pending_ticket={ticket}` where
  `pending_ticket` is the raw JSON file contents (or the literal string `none`). For an operator running `status`
  to orient on resume (the exact use case CLAUDE.md cites — "to learn whether a sprint is armed RIGHT NOW"), this
  is a developer-repr line, not a human summary. `note={note!r}` shows Python quoting; a populated ticket dumps raw JSON.
- **Why it matters (UX):** `status` is the one read-only, human-facing command and it's the least polished. A clear
  "SPRINT ARMED — '<note>'. Pending ticket: DONE (12s ago)" would serve the resume-orientation goal far better.
- **Blast radius:** Cosmetic; the data is all present.
- **Fix:** Format `status` as a short human sentence; parse the ticket and show reason + age rather than raw text.

### F-UX-5 — `arm`/`done`/`blocked`/`question` give no confirmation that the gate is actually loaded (Nit)
- **Evidence:** `arm` prints `armed: sprint gate ACTIVE — <note>` (`antistall.py:54`) purely from writing the flag
  file; it cannot and does not confirm the Stop hook is wired in `settings.json` or that the session was restarted.
  The MANUAL §7 correctly makes the operator prove firing manually, but the cheerful "ACTIVE" success line could be
  read as "enforcement is on now," which is not guaranteed until a post-install session restart.
- **Why it matters (UX):** Mild over-promise in the most-used command's success copy.
- **Blast radius:** Expectation-setting only.
- **Fix:** Append a one-line hint on `arm`, e.g. "(enforced only if the Stop hook is installed + you've restarted —
  see MANUAL §7)."

---

## Adversarial UX probes (asked, answered)
- *Does the block message tell the operator exactly what to do?* Yes — file path, JSON shape, and reason semantics
  are all inline (`antistall-gate.py:186-194`). Strong.
- *Is the cap message actionable on the escape-hatch path?* Yes — it explicitly suggests `clear .claude/sprint-gate.json`
  and explains the likely cause (stale flag) (`L173-177`). Good.
- *Are the fail-open allow messages alarming?* No — they're explanatory, not panicky ("failing open" reads as
  intentional design, reinforced by the matching landing-page/MANUAL copy).
- *Are the two repo copies' messages identical?* Yes — `hooks/` and `skill/antistall/hooks/` are byte-identical
  (verified via diff). The live copy differs by design (different tag/wording) per audit scope; that's the source of F-UX-1/F-UX-2.
- *Is the flow diagram readable?* Yes — monospace ASCII, correct branch order, fits the column. Only the
  stale-ticket nuance (F-UX-3) is glossed.

## Verdict
The text/diagram UX is accurate to the fixed code and the messaging is clear, actionable, and appropriately
non-alarming — the diagram correctly gained the two new branches. No Blocker/Critical/Major UX issues. Remaining
items are Minor/Nit: doc-vs-live tag and env-var drift (F-UX-1/2), a glossed stale-ticket branch in the diagram
(F-UX-3), and rough-but-functional `status`/`arm` copy (F-UX-4/5).
