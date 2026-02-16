# Multi-Machine Collaboration Workflow

For unattended orchestration (Odin submits once, agents self-coordinate), use `/docs/AUTONOMY.md`.
For full machine bootstrap and role startup commands, use `/docs/NEW_AGENT_ONBOARDING.md`.

## Team Mapping
- `Odin` = human coordinator.
- `Salomon` = Codex worker.
- `Stormforge` = Codex worker.
- `Kari` = Claude worker.

## 1) Daily Start (each machine)
1. `git checkout main`
2. `git pull --rebase`
3. Review `.tasks/in-progress.md` and pick assigned task.

## 2) Branch Naming
- `codex/<task-id>-<short-topic>` for `Salomon` and `Stormforge`
- `claude/<task-id>-<short-topic>` for `Kari`
- Keep branch scope to one task.

## 3) Commit Convention
- `<task-id>: <imperative summary>`
- Example: `T-20260215-03: add retry logic to rpc client`

## 4) Handoff Protocol
1. Update task status in `.tasks/in-progress.md`.
2. Add handoff note using `.tasks/templates/handoff.md`.
3. Push branch and reference commit/PR.
4. Reassign owner in task board.

## 5) PR Convention
- PR title: `<task-id> <short title>`
- PR body must include:
  - Scope completed
  - Validation evidence
  - Risks and follow-ups

## 6) Definition of Done
- Acceptance criteria checked.
- Relevant tests pass or test gap documented.
- Task moved to `.tasks/done.md` with PR/commit reference.
