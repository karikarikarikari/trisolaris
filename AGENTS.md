# Multi-Agent Operating Guide

This repository is set up for parallel work across multiple AI workers and machines.

## Team Map
- `Odin`: human coordinator, approvals, and merge decisions.
- `Salomon`: Codex worker (this agent), implementation and execution.
- `Stormforge`: second Codex worker, parallel implementation and execution.
- `Kari`: Claude worker, architecture/review/synthesis.

## Roles
- `Salomon` and `Stormforge`: implementation, refactors, tests, and PR-ready code changes.
- `Kari`: architecture review, risk analysis, docs synthesis, and final QA notes.
- `Odin`: prioritization, approvals, merge decisions.

## Routing Rules
- Send coding tasks with clear file-level scope to `Salomon` or `Stormforge`.
- Send cross-file design tradeoffs, review requests, and summary/report tasks to `Kari`.
- If a task mixes both, split into two linked tasks in `.tasks/`.

## Completion Criteria
- Task file includes acceptance criteria and owner.
- Owner posts status update in task file before handoff.
- Handoff includes: changed files, test results, open risks, next action.

## Sync Discipline
- Pull before starting work.
- Push after every meaningful milestone.
- Do not force-push shared branches.
