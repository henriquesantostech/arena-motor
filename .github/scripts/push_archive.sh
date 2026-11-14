#!/usr/bin/env bash
# Commits the intel/ folder of the private archive and pushes, rebasing on top of other runs (arena night).
# Only intel/ is staged: this job never touches the arena's own files.
set -euo pipefail
msg="${1:-intel}"
git config user.name "arena-motor"
git config user.email "250372676+henriquesantostech@users.noreply.github.com"
git add -A intel
if git diff --cached --quiet; then echo "nothing new"; exit 0; fi
git commit -q -m "$msg $(date -u +%Y-%m-%d)"
for i in 1 2 3 4 5; do
  if git push -q; then echo "saved"; exit 0; fi
  git fetch -q --depth=50 origin
  git rebase -q origin/HEAD || git rebase -q "origin/$(git rev-parse --abbrev-ref HEAD)"
  sleep $((i * 5))
done
echo "push failed"; exit 1
