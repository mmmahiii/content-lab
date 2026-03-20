#!/usr/bin/env bash
# Removes task worktrees and optionally deletes merged branches (local + remote).
# Use same --count or --tasks as spawn.
# Run from main repo after merge chat finishes.
set -euo pipefail

count=""
declare -a tasks=()
delete_branches=true

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
    --no-delete-branches) delete_branches=false ;;
    *) echo "Error: unknown $1" >&2; exit 1 ;;
  esac
  shift
done

[[ -n "$count" || ${#tasks[@]} -gt 0 ]] || { echo "Error: provide --count N or --tasks a b c" >&2; exit 1; }
[[ (-z "$count") || (-n "$count" && ${#tasks[@]} -eq 0) ]] || { echo "Error: use one of --count or --tasks" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
repo_name="$(basename "$repo_root")"
parent_dir="$(dirname "$repo_root")"

# True if $1 is still listed as a worktree root for this repo.
is_registered_worktree() {
  local candidate="$1"
  local cand_abs
  cand_abs="$(cd "$candidate" 2>/dev/null && pwd)" || return 1
  local line wt_path wt_abs
  while IFS= read -r line; do
    [[ "$line" == worktree\ * ]] || continue
    wt_path="${line#worktree }"
    wt_abs="$(cd "$wt_path" 2>/dev/null && pwd)" || continue
    if [[ "$cand_abs" == "$wt_abs" ]]; then
      return 0
    fi
  done < <(git -C "$repo_root" worktree list --porcelain 2>/dev/null)
  return 1
}

remove_worktree_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    echo "Skipped (not found): $path"
    return
  fi
  if git worktree remove "$path" 2>/dev/null || git worktree remove --force "$path" 2>/dev/null; then
    echo "Removed: $path"
    return
  fi
  if [[ ! -e "$path" ]]; then
    echo "Removed: $path"
    return
  fi
  if is_registered_worktree "$path"; then
    echo "Skipped (could not remove; still a registered worktree): $path" >&2
    return
  fi
  rm -rf "$path"
  echo "Removed orphaned folder: $path"
}

declare -a branches=()
if [[ -n "$count" ]]; then
  for ((i=1; i<=count; i++)); do
    path="$parent_dir/$repo_name-task-$i"
    remove_worktree_path "$path"
    branches+=("feat/task-$i")
  done
else
  for t in "${tasks[@]}"; do
    slug="$(slugify "$t")"
    path="$parent_dir/$repo_name-$slug"
    remove_worktree_path "$path"
    branches+=("feat/$slug")
  done
fi

git worktree prune
echo "Pruned."

if [[ "$delete_branches" == true && ${#branches[@]} -gt 0 ]]; then
  if [[ "$(git branch --show-current)" != "main" ]]; then
    echo "Skipping branch deletion (not on main). Switch to main first."
  else
    for b in "${branches[@]}"; do
      if git show-ref --verify --quiet "refs/heads/$b" 2>/dev/null; then
        if git branch -d "$b" 2>/dev/null; then
          echo "Deleted local: $b"
        else
          echo "Skipped local $b (not fully merged or in use)"
        fi
      fi
      if git show-ref --verify --quiet "refs/remotes/origin/$b" 2>/dev/null; then
        if git push origin --delete "$b" 2>/dev/null; then
          echo "Deleted remote: origin/$b"
        else
          echo "Skipped remote origin/$b (push failed)"
        fi
      fi
    done
  fi
fi
