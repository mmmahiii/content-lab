#!/usr/bin/env bash
# Creates packages/<name>/py compat layout for Cursor scaffold verification.
# Each py/ dir contains symlinks to the parent's pyproject.toml, src, tests.
# Run from repo root.
set -e
for p in core auth storage assets creative editing qa runs outbox ingestion features intelligence; do
  parent="packages/$p"
  pyDir="$parent/py"
  [[ -d "$parent" ]] || continue
  rm -rf "$pyDir"
  mkdir -p "$pyDir"
  for link in pyproject.toml src tests poetry.lock; do
    if [[ -e "$parent/$link" ]]; then
      ln -sf "../$link" "$pyDir/$link"
    fi
  done
done
echo "Scaffold compat layout created."
