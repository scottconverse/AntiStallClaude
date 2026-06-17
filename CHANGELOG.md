# Changelog

All notable changes to AntiStallClaude are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/).

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
  - **Fail-open anti-loop counter** (secondary): any unreadable / corrupt /
    unwritable counter now **allows** the stop instead of blocking again.
  Regression tests added to `tests/test_gate.py` (E: `stop_hook_active` allow,
  F: corrupt-counter fail-open, G: bounded-loop ≤1 block). Docs corrected (README,
  MANUAL §"Safety") — the anti-loop cap is no longer described as the sole
  guarantee. **Anyone running an earlier `antistall-gate.py` should update.**

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
