#!/usr/bin/env bash
# Squash merges turn the PR title into the commit on main, so it must be a
# Conventional Commit. Usage: check-pr-title.sh "<title>"
set -euo pipefail

title="$1"
types='feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert'
pattern="^(${types})(\([a-z0-9._/-]+\))?!?: (.+)$"
if [[ ! "$title" =~ $pattern ]]; then
  echo "::error::PR title must be '<type>(<scope>): <subject>' with type one of: ${types//|/, }"
  exit 1
fi
subject="${BASH_REMATCH[3]}"
if (( ${#subject} > 72 )); then
  echo "::error::Subject is ${#subject} characters long; the limit is 72."
  exit 1
fi
if [[ "$subject" == *. ]]; then
  echo "::error::Subject must not end with a period."
  exit 1
fi
echo "OK: $title"
