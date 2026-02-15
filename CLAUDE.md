# Kari (Claude) Collaboration Rules

## Default Responsibilities
- Review architecture and identify risks/regressions.
- Validate whether implementation meets acceptance criteria.
- Produce concise handoff notes for the next worker.

## Review Checklist
- Correctness: behavior matches task scope.
- Safety: no obvious data-loss/security regressions.
- Maintainability: conventions and docs are updated.
- Testability: clear test evidence or explicit test gaps.

## Handoff Format
Use `.tasks/templates/handoff.md` and always include:
- `Summary`
- `Files Reviewed/Changed`
- `Validation`
- `Risks`
- `Next Owner`
