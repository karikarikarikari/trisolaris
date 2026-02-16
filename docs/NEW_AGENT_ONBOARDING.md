# New Agent Onboarding

Use this guide when joining work on `stormforge1/trisolaris`.

## 1) Initial Setup
```bash
cd ~/Documents
git clone git@github.com:stormforge1/trisolaris.git Trisolaris
cd ~/Documents/Trisolaris
git checkout main
git pull --rebase
cp .mcp.template.json .mcp.json
```

If SSH is not set up yet, clone with HTTPS:
```bash
git clone https://github.com/stormforge1/trisolaris.git Trisolaris
```

## 2) Daily Start
```bash
cd ~/Documents/Trisolaris
git checkout main
git pull --rebase
```

Then read:
- `.tasks/in-progress.md`
- `.tasks/backlog.md`
- `.tasks/tasks/`
- `docs/COLLAB_WORKFLOW.md`

## 3) Claim/Take a Task
1. Pick an assigned task or coordinate with the team.
2. Confirm task scope and acceptance criteria in `.tasks/tasks/<TASK_ID>.md`.
3. Ensure `.tasks/in-progress.md` reflects active owner and branch.

## 4) Branch Naming
- Codex agents: `codex/<task-id>-<short-topic>`
- Claude agents: `claude/<task-id>-<short-topic>`

Examples:
- `codex/T-20260215-02-deer-research`
- `claude/T-20260215-01-flowers-research`

## 5) Do the Work
Deliverables usually include:
- Task output file(s) (for example under `docs/research/`)
- Handoff note using `.tasks/templates/handoff.md` (store in `.tasks/handoffs/`)

Keep changes scoped to one task per branch.

## 6) Validate, Commit, Push
```bash
git status
git add <files>
git commit -m "<task-id>: <imperative summary>"
git push -u origin <branch>
```

## 7) Open PR to Main
PR title format:
- `<task-id> <short title>`

PR body must include:
- Scope completed
- Validation evidence
- Risks / follow-ups

## 8) Review and Merge
If branch protection requires review:
```bash
gh pr review --repo stormforge1/trisolaris <PR_NUMBER> --approve
gh pr merge --repo stormforge1/trisolaris <PR_NUMBER> --squash --delete-branch
```

## 9) Close Task Board
After merge:
1. Move task entry from `.tasks/in-progress.md` to `.tasks/done.md`.
2. Update `.tasks/tasks/<TASK_ID>.md` acceptance checkboxes and PR link.
3. Sync local `main`:
```bash
git checkout main
git pull --rebase
```

## 10) Minimum Done Criteria
- Acceptance criteria checked.
- Deliverables present.
- Handoff note present when ownership/work handoff applies.
- PR merged to `main`.

