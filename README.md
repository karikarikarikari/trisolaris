# Trisolaris

This repo contains small utilities plus a multi-agent collaboration scaffold.

## Utilities

Current utilities include:
- generating new account names in the same style as `account_names_seed.txt`
- managing local (gitignored) secrets via `.env.local`
- cloning `welttowelt/yggdrasil-runner` once you have GitHub access

### Local secrets

Your real creds should live in `.env.local` (gitignored).

Start from:
- `.env.local.example`

### Generate names

```sh
python3 scripts/spin_up_names.py --count 40
```

Output:
- `generated_account_names_YYYY-MM-DD.txt`

### Check cartridge env

```sh
python3 scripts/check_cartridge_env.py
```

This prints the username and a masked password (never the full password).

### Clone yggdrasil-runner

If the GitHub repo is private, add a PAT (fine-grained token) to `.env.local`:

```dotenv
GITHUB_TOKEN=...
```

Then:

```sh
python3 scripts/clone_yggdrasil_runner.py
```

You can also point it at a different repo:

```sh
python3 scripts/clone_yggdrasil_runner.py --repo owner/name
```

## Multi-Agent Collaboration Scaffold

### Team Mapping
- `Odin`: human coordinator.
- `Salomon`: Codex worker.
- `Stormforge`: Codex worker.
- `Kari`: Claude worker.

### Key Files
- `/AGENTS.md`
- `/CLAUDE.md`
- `/.tasks/README.md`
- `/docs/COLLAB_WORKFLOW.md`
- `/docs/AUTONOMY.md`
- `/docs/GITHUB_SETUP.md`
- `/.mcp.template.json`

### Quick Start
1. Copy `/.mcp.template.json` to local `.mcp.json` and fill machine-specific values.
2. Keep `.mcp.json` untracked.
3. Create tasks from `/.tasks/templates/task.md`.
4. Track active work in `/.tasks/in-progress.md`.
5. Use handoff notes from `/.tasks/templates/handoff.md` when changing owner.

## Autonomous Mode (No Manual Relay)

Use GitHub Issues as the control plane so agents coordinate without editing shared board files directly.

1. Bootstrap labels and config:
```sh
scripts/autonomy_bootstrap.sh
```
2. Start supervisor loop on Odin machine:
```sh
scripts/autonomy_supervisor_loop.sh
```
3. Start worker loops:
```sh
scripts/autonomy_agent_loop.sh salomon
scripts/autonomy_agent_loop.sh stormforge
scripts/autonomy_agent_loop.sh kari
```
4. Submit a job from JSON spec:
```sh
scripts/autonomy_submit.sh .tasks/autonomy/specs/job-template.json
```

Full runbook: `/docs/AUTONOMY.md`

GitHub multi-account setup: `/docs/GITHUB_SETUP.md`

## License

MIT -- see [LICENSE](LICENSE).
