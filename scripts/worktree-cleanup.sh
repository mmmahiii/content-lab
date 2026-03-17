#!/usr/bin/env bash
# Removes task worktrees. Use same --count or --tasks as spawn.
# Run from main repo after merge chat finishes.
set -euo pipefail

count=""
declare -a tasks=()

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --count) shift; count="$1" ;;
    --tasks)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do tasks+=("$1"); shift; done
      continue
      ;;
    *) echo "Error: unknown $1" >&2; exit 1 ;;
  esac
  shift
done

[[ -n "$count" || ${#tasks[@]} -gt 0 ]] || { echo "Error: provide --count N or --tasks a b c" >&2; exit 1; }
[[ (-z "$count") || (-n "$count" && ${#tasks[@]} -eq 0) ]] || { echo "Error: use one of --count or --tasks" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
repo_name="$(basename "$repo_root")"
parent_dir="$(dirname "$repo_root")"

if [[ -n "$count" ]]; then
  for ((i=1; i<=count; i++)); do
    path="$parent_dir/$repo_name-task-$i"
    [[ -e "$path" ]] && git worktree remove "$path" && echo "Removed: $path" || echo "Skipped: $path"
  done
else
  for t in "${tasks[@]}"; do
    slug="$(slugify "$t")"
    path="$parent_dir/$repo_name-$slug"
    [[ -e "$path" ]] && git worktree remove "$path" && echo "Removed: $path" || echo "Skipped: $path"
  done
fi

git worktree prune
echo "Pruned."
