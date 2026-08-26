#!/usr/bin/env bash
# One-time per-worktree warm-up. Fixes the recurring macOS hidden-flag pth
# corruption and ensures the editable install resolves, then runs the suite.
set -euo pipefail
chflags nohidden .venv/lib/python3.13/site-packages/*.pth 2>/dev/null || true
uv sync -q 2>&1 | tail -1 || uv sync -q
echo "bootstrap ok in $(pwd)"
