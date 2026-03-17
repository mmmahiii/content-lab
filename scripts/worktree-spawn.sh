#!/usr/bin/env bash
set -euo pipefail

count=""
base_branch="main"
declare -a tasks=()

die() {
  echo "Error: $*" >&2
  exit 1
}

slugify() {
  local input="$1"
  local slug
  slug="$(echo "$input" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  [[ -n "$slug" ]] || die "Could not derive a slug from task '$input'."
  printf '%s\n' "$slug"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --count)
      shift
      [[ $# -gt 0 ]] || die "--count requires a value"
      count="$1"
      ;;
    --base-branch)
      shift
      [[ $# -gt 0 ]] || die "--base-branch requires a value"
      base_branch="$1"
      ;;
    --tasks)
      shift
      [[ $# -gt 0 ]] || die "--tasks requires at least one value"
      while [[ $# -gt 0 && "$1" != --* ]]; do
        tasks+=("$1")
        shift
      done
      continue
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

if [[ -n "$count" && ${#tasks[@]} -gt 0 ]]; then
  die "Use either --count or --tasks, not both."
fi
if [[ -z "$count" && ${#tasks[@]} -eq 0 ]]; then
  die "Provide either --count <N> or --tasks <task...>."
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$repo_root" ]] || die "Run this script from inside a git repository."
repo_name="$(basename "$repo_root")"
parent_dir="$(dirname "$repo_root")"

base_ref="origin/$base_branch"
if ! git show-ref --verify --quiet "refs/remotes/$base_ref"; then
  base_ref="$base_branch"
fi

declare -a created=()

action_create() {
  local branch="$1"
  local folder="$2"
  local label="$3"
  local worktree_path="$parent_dir/$folder"

  if [[ -e "$worktree_path" ]]; then
    echo "Skipping existing path: $worktree_path"
    return
  fi

  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git worktree add "$worktree_path" "$branch"
  else
    git worktree add -b "$branch" "$worktree_path" "$base_ref"
  fi

  created+=("$label|$branch|$worktree_path")
}

if [[ -n "$count" ]]; then
  [[ "$count" =~ ^[0-9]+$ ]] || die "--count must be a positive integer"
  (( count > 0 )) || die "--count must be greater than zero"
  for ((i=1; i<=count; i++)); do
    action_create "feat/task-$i" "$repo_name-task-$i" "task-$i"
  done
else
  for task in "${tasks[@]}"; do
    slug="$(slugify "$task")"
    action_create "feat/$slug" "$repo_name-$slug" "$task"
  done
fi

if [[ ${#created[@]} -eq 0 ]]; then
  echo "No new worktrees created."
  exit 0
fi

echo
echo "Created worktrees:"
printf '%-24s %-28s %s\n' "TASK" "BRANCH" "WORKTREE"
printf '%-24s %-28s %s\n' "------------------------" "----------------------------" "---------------------------"
for row in "${created[@]}"; do
  IFS='|' read -r task branch path <<< "$row"
  printf '%-24s %-28s %s\n' "$task" "$branch" "$path"
done

echo
echo "Next:"
echo "1) Open each Worktree folder in a separate Cursor window."
echo "2) Start one task chat per window and paste the task prompt."
echo "3) After tasks finish, run merge-agent chat from main worktree."
