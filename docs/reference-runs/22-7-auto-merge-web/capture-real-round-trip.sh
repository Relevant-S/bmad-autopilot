#!/usr/bin/env bash
# Story 22.7 AC-7 — capture the GENUINE `gh pr ready` -> `gh pr merge --squash`
# round-trip landing a REAL squashed commit on `main`, against a real throwaway
# GitHub repo. Maintainer-executed (reference runs are historically maintainer-run;
# the dev environment is not assumed to have a throwaway remote to mutate).
#
# This script runs EXACTLY the two `gh` invocations the auto-merge actuator issues
# in `attempt_auto_merge` (auto_merge_execution.py), in the same order, on the same
# per-story branch passed explicitly:
#     gh pr ready  <branch>           # Story 22.7 draft->ready transition (NEW)
#     gh pr merge --squash <branch>   # Story 17.3 merge (UNCHANGED)
# It is the genuine AC-7 witness: a real draft PR is marked ready, then squash-merged,
# landing one real commit on `main`. NO `git push` of the merge itself, no --force,
# no --rebase, no --delete-branch — `gh pr ready`/`gh pr merge` are GitHub-side PR
# mutations on the branch's own PR (NFR-S3 / NFR-R3).
#
# Requires: an authenticated `gh` with `repo` scope (`gh auth status`), on a plan
# where draft PRs are exercisable (public repo on Free, or private on Team/Enterprise).
#
# Usage:
#     ./capture-real-round-trip.sh 2>&1 | tee run-output.txt
# Then commit run-output.txt and fill the {{...}} placeholders in narrative.md.
set -euo pipefail

REPO_NAME="${REPO_NAME:-bmad-autopilot-automerge-witness-$(date +%Y%m%d-%H%M%S)}"
VISIBILITY="${VISIBILITY:---public}"   # draft PRs need Free=public OR private+Team/Enterprise
BRANCH="bmad-automation/story/sample-auto-001"
KEEP_REPO="${KEEP_REPO:-0}"            # set KEEP_REPO=1 to skip the teardown

echo "=== Story 22.7 AC-7 genuine auto-merge round-trip witness ==="
echo "gh version:"; gh --version | head -1
echo "gh auth (account only):"; gh auth status 2>&1 | grep -E "Logged in|Active account" || true

WORK="$(mktemp -d)"
cleanup() {
  if [ "${KEEP_REPO}" != "1" ]; then
    echo "=== teardown: deleting throwaway repo ==="
    gh repo delete "${REPO_NAME}" --yes 2>&1 || echo "(manual cleanup may be needed: gh repo delete ${REPO_NAME} --yes)"
  fi
  rm -rf "${WORK}"
}
trap cleanup EXIT

cd "${WORK}"
git init -q -b main
git config user.email "dribnucko@gmail.com"
git config user.name "dribniuk"
printf '# automerge witness\n' > README.md
git add README.md
git commit -q -m "init main"

echo "=== create throwaway remote + push main ==="
gh repo create "${REPO_NAME}" "${VISIBILITY}" --source=. --remote=origin --push

echo "=== create per-story branch with one commit, push, open DRAFT PR ==="
git switch -q -c "${BRANCH}"
printf 'story change (squash target)\n' >> README.md
git commit -qam "story: sample-auto-001 change"
git push -q -u origin "${BRANCH}"
gh pr create --draft --base main --head "${BRANCH}" \
  --title "sample-auto-001" --body "Story 22.7 AC-7 genuine witness."

echo "=== PRE-STATE: PR is draft (this is what makes a bare gh pr merge fail on a real project) ==="
gh pr view "${BRANCH}" --json number,isDraft,state,mergeStateStatus

echo "=== ACTUATOR CALL 1 (Story 22.7): gh pr ready ${BRANCH} ==="
gh pr ready "${BRANCH}"

echo "=== POST-READY: PR is no longer draft ==="
gh pr view "${BRANCH}" --json number,isDraft,state,mergeStateStatus

echo "=== ACTUATOR CALL 2 (Story 17.3): gh pr merge --squash ${BRANCH} ==="
gh pr merge --squash "${BRANCH}"

echo "=== POST-MERGE: PR merged; the real squashed commit on main ==="
gh pr view "${BRANCH}" --json number,state,mergedAt,mergeCommit
git fetch -q origin main
echo "main log after merge:"; git log -3 --oneline origin/main

echo "=== DONE — a real commit landed on main via gh pr ready -> gh pr merge --squash ==="
