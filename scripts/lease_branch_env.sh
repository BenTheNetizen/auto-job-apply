#!/usr/bin/env bash
# Canonical worker setup for the auto-job-apply build.
# Collapses the old multi-step (treehouse get → jq → cd → checkout → cd back)
# into ONE bash call that prints a sourced env block. Combine with the parent
# passing cwd=<worktree> so the worker NEVER has to cd manually.
#
# Two modes:
#   1. With worktree already leased (cwd is inside it):
#        eval "$(bash <repo>/scripts/lease_branch_env.sh <branch>)"
#   2. Fresh lease (cwd may be repo root): helper leases + branches + prints
#      the worktree path so the parent can re-dispatch with cwd=<path> on
#      subsequent turns.
#
# Accepts: <branch>
set -euo pipefail
BRANCH="${1:?branch required}"

# If we're already inside a treehouse worktree, just branch it.
CUR="$(pwd)"
if [[ "$CUR" == *"/.treehouse/"* ]]; then
  git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
  printf 'export TREEHOUSE_PATH=%q\n' "$CUR"
  echo "in-worktree branch: $CUR @ $BRANCH"
  exit 0
fi

# Otherwise lease a fresh worktree and report its path for a parent re-dispatch.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
LEASE_JSON="$(treehouse get --lease --lease-holder "leaf-$BRANCH" --json)"
PATH_V="$(printf '%s' "$LEASE_JSON" | jq -r .path)"
LEASE_ID="$(printf '%s' "$LEASE_JSON" | jq -r .lease_id)"
cd "$PATH_V"
git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
printf 'export TREEHOUSE_PATH=%q\n' "$PATH_V"
printf 'export TREEHOUSE_LEASE_ID=%q\n' "$LEASE_ID"
echo "leased: $PATH_V @ $BRANCH"
