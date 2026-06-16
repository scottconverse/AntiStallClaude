#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# AntiStallClaude — SessionStart wrapper (self-locating).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/antistall-session-start.py"
