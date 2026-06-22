# Changelog

All notable changes to AntiStallClaude are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/).

## [0.3.2] — 2026-06-22

### Fixed — disarm UX (the gated agent wouldn't bring up the passphrase box)
- **The gate now tells the agent to run `release` itself on a stop request — which pops the
  masked password box for the human.** Real-world failure: when the user said "disarm," the
  gated agent would (a) tell them to run a command in a terminal they don't use, (b) point them
  at an obscure `.cmd` file to hunt for, or (c) **falsely claim "you released it"** while the gate
  was still armed and blocking. The disarm window never reliably appeared.
- **Rewrote the gate's block message** (`antistall-gate.py`) to instruct, on any
  stop/disarm/cancel request: *immediately run `python3 <hooks>/antistall.py release`* — it opens
  the password box on the user's screen for them to type into (the agent can open it, never fill
  it). It now **explicitly forbids**: pointing the user at a terminal, sending them to find a
  `.cmd`/file, or claiming the user released it. This message is re-read on every block, so the
  fix takes effect immediately in already-running sessions (no restart).
- Reworded the `arm` confirmation, the no-secret refusal, and `SKILL.md` to match: "just tell the
  agent disarm → box pops; no file, no terminal." The double-click launchers are now documented
  as a **fallback**, not the primary path. README updated.

## [0.3.1] — 2026-06-22

### Added — no-CLI (Cowork) secret entry
- **Masked GUI password dialog for `set-release-secret` and `release`.** On Windows these now
  pop a native masked input box instead of requiring a terminal. The agent can launch the
  window but cannot read what is typed into it — the human-only property holds in a pure
  point-and-click (Cowork) workflow with no terminal.
- **Two double-click launchers** (`launchers/Set-AntiStall-Secret.cmd`, `Release-Sprint.cmd`),
  copied by `install.py` into the `.claude/` dir. They use windowless `pythonw` so only the
  password box appears — no console. `Release-Sprint.cmd` pops a folder picker to choose the
  project, then the masked passphrase box.

### Fixed
- **Secret prompt fell back to a terminal `getpass` when a console was attached** (e.g. launched
  via `Start-Process` or a `.cmd`), so a desktop user saw a confusing console instead of the
  masked box. `_read_passphrase` now prefers the GUI dialog on Windows **always** (env override
  still wins; terminal `getpass` remains the fallback when the GUI is unavailable).

## [0.3.0] — 2026-06-21

### Changed (BREAKING) — human-only disarm
- **The agent can no longer stop or disarm a sprint. Closing the self-exit hole.**
  In v0.2.x an agent could write a `DONE` ticket which both allowed the stop AND cleared
  `sprint-gate.json` — i.e. the agent it polices held the off switch, and could declare a
  project "done" to quit early (observed: a sprint marked done with 100+ tests and many
  required features unbuilt). Now:
  - **`done` / `blocked` / `question` are removed.** The gate no longer reads or honors any
    stop-ticket. There is no agent-usable command that ends a sprint.
  - **Disarm requires a human release passphrase**, stored only as a salted PBKDF2-SHA256
    hash (`~/.claude/antistall-release.hash`) — never plaintext, never in the agent's
    context. `release` verifies it; `set-release-secret` sets it (changing it requires the
    current one). `arm` refuses unless a release secret exists.
  - **The Stop hook never clears the gate file** — only a verified human `release` does. Every
    loop-safety fail-open path now yields at most a *pause*, never a disarm.
  - **`stop_hook_active` no longer grants a free stop.** Enforcement is bounded instead by a
    consecutive-block cap (`ANTISTALL_BLOCK_CAP`, default **25**, `0` = hold until release);
    at the cap the gate PAUSES one stop **without disarming** and fires a desktop
    notification so a human is summoned. The sprint stays armed and re-enforces next turn.
  - New **`request "<why>"`**: the agent's only voice — records a note and notifies the
    human; it does NOT disarm.
- SessionStart reminder and README rewritten for the new model; `tests/test_gate.py` rewritten
  to assert tickets are ignored, the agent cannot disarm, and only a human passphrase releases.

### Security note
- This removes every *sanctioned* self-exit; a drift-prone agent has no way to quit a sprint.
  It is not a sandbox — an agent with full filesystem/admin rights could still delete the
  gate/secret files (flagrant tampering, out of scope for a userspace hook). For OS-hard
  enforcement, ACL-lock those files so the agent's normal token cannot write them.

## [0.2.1] — 2026-06-21

### Fixed
- **Cross-session collision: two sessions in one project gated each other.** Sprint
  state (`sprint-gate.json` / `sprint-stop-ticket.json`) was project-scoped while the
  loop-guard counter was already session-scoped, so a sprint armed by session A blocked
  session B in the same folder (e.g. a TinkerQuarry session's gate firing on an
  unrelated session sharing `Desktop/CODE`). Now sprint state is **session-scoped**:
  `arm` writes `sprint-gate-<session_id>.json` (with an `owner` field) and the gate keys
  off the Stop payload's `session_id`. The CLI reads `CLAUDE_CODE_SESSION_ID` (the same
  id the harness puts in the Stop payload), so arming/ticketing targets exactly the
  state the gate reads. `_clear_counts` now clears only the current session's counter.

### Compatibility
- A pre-0.2.1 project-wide `sprint-gate.json` is still honored: treated as unowned
  (applies to all sessions, old behavior) unless it carries `"owner": "<session_id>"`,
  in which case only that session is gated. `status` now reports the session scope and
  flags any legacy/other-owner gate. SessionStart reminder is session-aware too.

## [0.2.0] — 2026-06-21

### Added
- **Global / user-level install (`python3 install.py --global`).** Installs the
  hooks into `~/.claude/` (or `$CLAUDE_CONFIG_DIR`) and wires `Stop` +
  `SessionStart` with absolute `python3` invocations, so the gate fires for every
  session in every project with no per-project install. The existing user
  `settings.json` is preserved/merged (other hooks kept, no duplicates).
- `antistall.py` (arm/ticket CLI) now resolves state via `CLAUDE_PROJECT_DIR` →
  `cwd/.claude` → script-relative, matching the gate. A globally-installed CLI
  therefore arms/tickets the **current project's** state, not `~/.claude`.

### Changed
- **Corrected the stale "user-level hooks don't fire in Cowork" guidance.** On
  current builds (verified claude-code 2.1.181) Cowork's Code tab launches with
  `--setting-sources=user,project,local`, so user-level hooks DO fire — global
  install works. Proven empirically: a user-source `SessionStart` sentinel fired
  in a session launched with the Cowork flags. README "Cowork note" updated.

### Fixed
- Installer now reads `settings.json` as `utf-8-sig`, tolerating a UTF-8 BOM
  (PowerShell/Windows editors often add one) instead of refusing to merge.

## [0.1.1] — 2026-06-17

### Fixed
- **Critical: the `Stop` hook could loop forever and burn tokens without limit.**
  `antistall-gate.py` never checked `stop_hook_active`, so when it blocked a stop
  the agent continued and immediately tried to stop again — and the hook blocked
  again. The only brake was the consecutive-block counter, which failed **closed**:
  any read error reset it to `0`, so it never reached the cap. Two agents sharing
  one project `.claude/` (or any mid-write race on `.antistall-block-count`) pinned
  the counter near 1 and the gate looped indefinitely, leaving the session pinned
  "running". Two independent fixes:
  - **Honor `stop_hook_active`** (primary, race-proof): always allow a stop that is
    itself the product of a prior block. Caps the gate at one nudge per
    continuation chain — depends on no shared file.
  - **Per-session, fail-open anti-loop counter** (secondary): the counter file is
    keyed on the Stop payload's `session_id` (`.antistall-block-count-<sid>`), so
    two agents in one project never share it — the cross-agent read-modify-write
    race is now structurally impossible, not merely unlikely. And any missing /
    empty / corrupt / unreadable / unwritable counter now **allows** the stop
    instead of blocking again.
  **Anyone running an earlier `antistall-gate.py` should update.**

### Hardened (post-fix audit pass — audit-lite + walkthrough + 5-role audit-team)
- Loop-guard branch now also consumes any pending stop-ticket (no stale re-use).
- Future-dated ticket `ts` (clock skew / hand-edit) is treated as stale (`0 <= age`).
- Tests expanded in `tests/test_gate.py`: all four fail-open branches
  (corrupt/empty/unreadable/unwritable), exact cap boundary, per-session counter
  isolation, `CLAUDE_PROJECT_DIR`-unset self-locating fallback, the two shipped
  copies byte-identical, and a `.sh` wrapper smoke test. The bounded-loop sentinel
  (case G) simulates the real harness auto-continue loop and fails if it blocks twice.
- Docs accuracy: version strings bumped to 0.1.1 on README/MANUAL/landing; upgrade
  notice added to README + landing; the "N−1 forced continuations" figure is now
  qualified (on Claude Code/Cowork the primary guard caps nudges at 1); the
  `[ANTI-STALL]` verify signal is noted as "or your configured TAG"; the landing
  flow shows ticket freshness + single-use consume; CHANGELOG cites MANUAL §2
  (Safety subsection); `antistall-gate.py`'s `_allow` is typed `NoReturn`.

## [0.1.0] — 2026-06-16

Initial public release.

### Fixed
- Corrected cross-runtime portability claim: the shipped hook speaks Claude Code's
  Stop-hook protocol and is verified only on Claude Code and Cowork; Codex, Gemini
  CLI, and GitHub Copilot CLI are explicitly not verified (README, MANUAL §8,
  DISCUSSIONS_SEED, release notes, Discussion #1).
- Fixed anti-loop off-by-one in docs: `ANTISTALL_BLOCK_CAP=6` blocks `cap−1 = 5`
  turn-ends and allows the 6th — corrected in README, MANUAL §2 and §6, and the
  release notes ("six forced continuations" → "five forced continuations at the
  default").

### Added
- **Anti-stall `Stop` hook** (`hooks/antistall-gate.py` + `.sh`) — blocks ending
  a turn while a sprint is armed unless a fresh `DONE`/`BLOCKED`/`QUESTION`
  stop-ticket is present; anti-loop escape cap (default 6); silent when no
  sprint is armed.
- **Operator helper** (`hooks/antistall.py`) — `arm` / `done` / `blocked` /
  `question` / `status`.
- **SessionStart reminder** (`hooks/antistall-session-start.py` + `.sh`) —
  injects the gate's existence + current armed state.
- **Installer** (`install.py`) — copies hooks into a project's `.claude/` and
  merges the `Stop` + `SessionStart` wiring into `.claude/settings.json`
  (project-level; Cowork-safe; idempotent; backs up existing settings).
- **Claude Code skill** (`skill/antistall/`) — install + operate via the agent.
- **Self-contained unit test** (`tests/test_gate.py`).
- Docs: README, full manual, landing page, example settings, discussion seeds.
- Env config: `ANTISTALL_BLOCK_CAP`, `ANTISTALL_TICKET_MAX_AGE_S`.

### Known limitations
- Not unspoofable (a false `DONE` ticket is possible) — but it converts silent
  drift into an explicit, logged, auditable claim, and default-deny removes the
  lazy path.
- Enforces *don't stop early*, not *do good work* — pair with tests/CI.
