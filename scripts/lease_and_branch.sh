#!/usr/bin/env bash
# Lease a treehouse worktree, branch it, and print BEL-separated env lines
# so the caller can `source` it with `eval` without re-cd'ing on every tool call.
# Usage: eval "$(bash scripts/lease_and_branch.sh <holder> <branch>)"
set -euo pipefail
HOLDER="${1:?holder required}"
BRANCH="${2:?branch required}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LEASE_JSON="$(treehouse get --lease --lease-holder "$HOLDER" --json)"
PATH_V="$(printf '%s' "$LEASE_JSON" | jq -r .path)"
LEASE_ID="$(printf '%s' "$LEASE_JSON" | jq -r .lease_id)"
cd "$PATH_V"
git checkout -b "$BRANCH" 2>/dev/null || { git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" origin/main; }
printf 'export TREEHOUSE_LEASE_ID=%q\n' "$LEASE_ID"
printf 'export TREEHOUSE_PATH=%q\n' "$PATH_V"
printf 'alias cdwt="cd %q"\n' "$PATH_V"
printf 'echo "leased wt: %s @ branch %s"\n' "$PATH_V" "$BRANCH"
