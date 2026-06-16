#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# AntiStallClaude — anti-stall Stop hook wrapper.
# Self-locating: works whether or not CLAUDE_PROJECT_DIR is set at hook runtime.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/antistall-gate.py"
