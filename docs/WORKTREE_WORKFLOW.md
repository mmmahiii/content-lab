# Worktree Multi-Agent Workflow

This workflow lets you run multiple AI task chats in parallel with minimal conflicts by giving each task its own Git worktree and branch.

---

## Exact workflow (your daily steps)

**No manual folders—spawn creates everything.**

1. **Spawn** (in terminal)
   ```powershell
   cd content-lab
   .\scripts\worktree-spawn.ps1 -Count 5
   ```
   Creates worktree dirs automatically. Output includes a **Copy-paste for merge agent** block—keep terminal open or copy that block now.

2. **Open Cursor windows**
   - File → Open Folder → pick each `../content-lab-task-N` (one window per worktree).

3. **Task chats (parallel)**
   - Run `.\scripts\worktree-copy-task.ps1` once.
   - Window 1: New chat → Ctrl+V (task prompt) → paste backlog item 1 → send.
   - Window 2: New chat → Ctrl+V (task prompt) → paste backlog item 2 → send.
   - Repeat for each window. Do not wait for one to finish—start all at once.

4. **Wait** until all task chats report done.

5. **Merge** (after all tasks finish)
   - Main worktree: open `content-lab` in Cursor.
   - New chat → run `.\scripts\worktree-copy-merge.ps1` → Ctrl+V (merge prompt).
   - Paste the branch list from spawn output (the Copy-paste block).

6. **Cleanup** (after merge chat finishes—once per batch, in terminal)
   ```powershell
   .\scripts\worktree-cleanup.ps1 -Count 5
   ```
   Use same `-Count` or `-Tasks` as spawn. Removes worktrees and deletes merged branches (local + remote). Use `-DeleteBranches:$false` to skip branch deletion.

---

## Why this works

- Each task has a separate folder (worktree), so edits do not collide on disk.
- Each worktree has its own branch, so commits stay isolated.
- A dedicated merge agent merges completed branches into `main` in a controlled sequence.

## Prerequisites

- Run from repository root.
- Local `main` exists and is up to date.
- Clean working tree in the main repo before starting.

## Step 1: Spawn task worktrees

### PowerShell (Windows)

```powershell
# Numbered tasks (feat/task-1, feat/task-2, ...)
.\scripts\worktree-spawn.ps1 -Count 3

# Named tasks (feat/auth-fix, feat/new-endpoint, ...)
.\scripts\worktree-spawn.ps1 -Tasks "auth-fix","new-endpoint","ui-tweak"
```

### Bash (Linux/macOS)

```bash
# Numbered tasks
./scripts/worktree-spawn.sh --count 3

# Named tasks
./scripts/worktree-spawn.sh --tasks auth-fix new-endpoint ui-tweak
```

The script prints each created worktree path and branch name.

## Step 2: Open one Cursor window per worktree

For each created folder (for example, `../content-lab-task-1`), open a separate Cursor window with that folder.

## Step 3: Start one task chat per window

In each task window:

1. Open a new chat.
2. Paste the Task Agent Initial Prompt from [`docs/worktree-prompts.md`](docs/worktree-prompts.md).
3. Paste exactly one backlog item under `Your task (backlog item)`.

Yes, this is the intended loop: prompt first, backlog item next, one backlog item per chat/worktree.

## Step 4: Wait for task chats to finish

Each task chat should report:

- branch name
- commit SHA
- checks run and results
- any merge warnings

## Step 5: Run merge agent in main worktree

Go back to the original repository folder (main worktree):

1. Open a dedicated merge chat.
2. Paste the Merge Agent Genesis Prompt from [`docs/worktree-prompts.md`](docs/worktree-prompts.md).
3. Send branch list in desired order, for example:

```text
Merge these branches in order:
feat/task-1
feat/task-2
feat/task-3
```

The merge agent merges sequentially, resolves conflicts, and runs checks.

## Step 6: Verify and clean up

After merges pass:

- push `main`
- run cleanup script (use same `-Count` or `-Tasks` as spawn):

```powershell
.\scripts\worktree-cleanup.ps1 -Count 5
```

```bash
./scripts/worktree-cleanup.sh --count 5
```

## Recommended merge policy

- Merge smaller/riskier branches first.
- Keep merge order deterministic and documented.
- If two branches touch the same area, merge one, re-run checks, then merge the next.

## Troubleshooting

- `path already exists`: remove or rename existing folder, then rerun spawn script.
- `branch already checked out`: ensure branch is not already attached to another worktree.
- frequent conflicts in one module: reduce parallelism for that module, or split by subsystem.
- stale worktree records: run `git worktree prune`.

## Related files

- [`scripts/worktree-spawn.ps1`](scripts/worktree-spawn.ps1)
- [`scripts/worktree-spawn.sh`](scripts/worktree-spawn.sh)
- [`scripts/worktree-copy-task.ps1`](scripts/worktree-copy-task.ps1)
- [`scripts/worktree-copy-merge.ps1`](scripts/worktree-copy-merge.ps1)
- [`scripts/worktree-cleanup.ps1`](scripts/worktree-cleanup.ps1)
- [`scripts/worktree-cleanup.sh`](scripts/worktree-cleanup.sh)
- [`docs/worktree-prompts.md`](docs/worktree-prompts.md)
