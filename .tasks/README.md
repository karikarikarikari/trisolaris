# Task Board

Use this folder as the shared async control plane for all workers.

## Files
- `backlog.md`: approved but not started.
- `in-progress.md`: actively worked tasks.
- `done.md`: completed tasks with links to PRs/commits.
- `templates/task.md`: new task template.
- `templates/handoff.md`: handoff note template.

## Task ID Convention
- Format: `T-YYYYMMDD-XX`
- Example: `T-20260215-01`

## Status Flow
1. Create task in `backlog.md`.
2. Move it to `in-progress.md` with owner + branch.
3. Add handoff note when work changes owner.
4. Move to `done.md` when merged or explicitly closed.

## Ownership Rule
Only one active owner per task. Reassign only with a handoff note.

Allowed owner values: `salomon`, `stormforge`, `kari`, `odin`.
