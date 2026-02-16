# Autonomous Multi-Agent Orchestration

This repo now supports autonomous coordination across Odin, Salomon, Stormforge, and Kari using GitHub Issues as the shared control plane.

## What It Solves
- Odin submits one job.
- System creates multiple autonomous task issues with owners and dependencies.
- Each agent machine claims and executes its own tasks automatically.
- Lease + heartbeat + retries prevent stuck work from halting the queue.
- Cross-agent coordination happens in issue comments and labels.

## Why This Design
Using GitHub Issues instead of committing queue state to `main` avoids merge conflicts and branch-protection deadlocks while all machines coordinate in near-real-time.

Design choices align with official guidance:
- Branch protection and PR requirements can block direct writes to `main`, so queue state should not depend on direct branch pushes. See GitHub docs: [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
- Polling and mutating API calls are rate-limited; loops use moderate polling intervals, jitter, and retries. See: [Best practices for using the REST API](https://docs.github.com/en/rest/guides/best-practices-for-using-the-rest-api) and [Rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api).
- Task claiming uses lease semantics (claim expires if no heartbeat), modeled after visibility-timeout patterns in queue systems. See AWS SQS: [Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html).
- Retry logic uses exponential backoff + jitter guidance. See AWS docs: [Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html).

## Files Added
- `scripts/autonomy.py`: orchestration engine.
- `scripts/autonomy_bootstrap.sh`: one-time setup + status.
- `scripts/autonomy_submit.sh`: submit a job spec.
- `scripts/autonomy_agent_loop.sh`: run one agent worker loop.
- `scripts/autonomy_supervisor_loop.sh`: stale lease recovery + board sync loop.
- `.tasks/autonomy/config.json`: shared defaults.
- `.tasks/autonomy/specs/job-template.json`: template for new jobs.
- `.tasks/autonomy/specs/flowers-deer-demo.json`: working example.

## One-Time Setup (All Machines)
Before running autonomy loops, ensure GitHub account + SSH identity are configured:
- `/docs/GITHUB_SETUP.md`
- `/docs/NEW_AGENT_ONBOARDING.md`

1. Ensure GitHub CLI auth exists:
```bash
gh auth status
```
2. Run bootstrap from repo root:
```bash
scripts/autonomy_bootstrap.sh
```
This creates required labels and validates API connectivity.

## Optional Local Override (Per Machine)
If a machine should use a different runner command, create `.tasks/autonomy/local.json` (gitignored):

```bash
cp .tasks/autonomy/local.example.json .tasks/autonomy/local.json
```

```json
{
  "agents": {
    "kari": {
      "runner": "shell",
      "command": "your-kari-command --prompt-file {prompt_file} --output {output_file}"
    }
  }
}
```

Supported runners:
- `codex`: uses `codex exec` automatically.
- `shell`: executes custom shell command template.
- `noop`: immediate success (for dry-run/testing).

Template variables for `shell` commands:
- `{repo_root}`
- `{prompt_file}`
- `{output_file}`
- `{issue_number}`
- `{agent}`

## Start Autonomous Loops
Run these on dedicated terminals (or tmux sessions):

### Odin machine (supervisor)
```bash
scripts/autonomy_supervisor_loop.sh
```

### Salomon machine
```bash
scripts/autonomy_agent_loop.sh salomon
```

### Stormforge machine
```bash
scripts/autonomy_agent_loop.sh stormforge
```

### Kari machine
```bash
scripts/autonomy_agent_loop.sh kari
```

## Submit a Job (Odin)
1. Copy and edit a spec:
```bash
cp .tasks/autonomy/specs/job-template.json .tasks/autonomy/specs/my-job.json
```
2. Submit:
```bash
scripts/autonomy_submit.sh .tasks/autonomy/specs/my-job.json
```

The system creates one job issue plus child task issues.

## Ask Workers By Mention (No Spec File)
You can ask workers a direct question without creating a job spec:

1. Open a normal issue (for example title starts with `[QUESTION]`).
2. Mention one or more worker accounts in the issue body or comments:
   - `@salomon-shdow`
   - `@stormforge1`
   - `@karikarikarikari`
3. Running worker loops auto-intake mentions and create per-worker autonomy tasks.
4. For question tasks, workers reply in the original source issue thread (no PR required).

## Job Spec Format
`depends_on` references prior task indices in the same file.

```json
{
  "title": "Example",
  "brief": "What Odin wants done",
  "priority": "P2",
  "tasks": [
    {
      "owner": "kari",
      "title": "Task A",
      "objective": "...",
      "deliverables": ["docs/a.md"],
      "depends_on": []
    },
    {
      "owner": "salomon",
      "title": "Task B",
      "objective": "...",
      "deliverables": ["docs/b.md"],
      "depends_on": [1]
    }
  ]
}
```

## Operational Commands
```bash
python3 scripts/autonomy.py status
python3 scripts/autonomy.py requeue-stale
python3 scripts/autonomy.py sync-board
```

## Recovery Playbook
- If a worker crashes, supervisor requeues expired leases automatically.
- If a task fails repeatedly, it transitions to `autonomy:dead`.
- Odin can inspect dead-letter tasks and relaunch with a new task issue.

## Security Notes
- Keep `GITHUB_TOKEN`/`GH_TOKEN` scoped minimally (`repo` scope only when needed).
- Do not store secrets in issue text.
- Keep machine-specific runner commands in `.tasks/autonomy/local.json` (gitignored).
