# Changelog

All notable changes to AntiStallClaude are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/).

## [0.1.0] — 2026-06-16

Initial public release.

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
