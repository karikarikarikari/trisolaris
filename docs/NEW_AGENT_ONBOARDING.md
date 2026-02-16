# New Worker Onboarding

Use this guide to bring a new worker machine online for `stormforge1/trisolaris`.

This repo supports two collaboration modes:
- Autonomous mode (recommended): Odin submits jobs, workers self-coordinate through GitHub Issues.
- Manual mode (fallback): workers update markdown task board files and use PR handoffs.

## Team Identity Map
- Odin (human coordinator): `welttowelt`
- Salomon (Codex worker): `salomon-shdow`
- Stormforge (Codex worker): `stormforge1`
- Kari (Claude worker): `karikarikarikari`

## Canonical References
- GitHub account + SSH setup: `docs/GITHUB_SETUP.md`
- Autonomous operations: `docs/AUTONOMY.md`
- Manual workflow fallback: `docs/COLLAB_WORKFLOW.md`
- Task board conventions: `.tasks/README.md`

## 1) Machine Prerequisites
Install and verify:

```bash
git --version
gh --version
python3 --version
screen --version
```

## 2) Clone and Sync Repository
Use SSH when possible:

```bash
cd ~/Documents
git clone git@github.com:stormforge1/trisolaris.git Trisolaris
cd ~/Documents/Trisolaris
git checkout main
git pull --rebase
cp .mcp.template.json .mcp.json
```

If SSH is not ready yet, use HTTPS temporarily:

```bash
git clone https://github.com/stormforge1/trisolaris.git Trisolaris
```

## 3) Configure GitHub Account and Access
Follow `docs/GITHUB_SETUP.md` for multi-account setup, then verify:

```bash
gh auth status
gh repo view stormforge1/trisolaris --json nameWithOwner,viewerPermission
```

Expected:
- active `gh` user matches machine role
- `viewerPermission` is `WRITE` for worker machines

## 4) Bootstrap Autonomy Runtime

```bash
cd ~/Documents/Trisolaris
scripts/autonomy_bootstrap.sh
python3 scripts/autonomy.py status
```

## 5) Start Persistent Loops (Autonomous Mode)
Use detached `screen` sessions so loops survive terminal close.

### Odin Machine (`welttowelt`) Supervisor

```bash
cd ~/Documents/Trisolaris
gh auth switch --hostname github.com --user welttowelt
ODIN_TOKEN="$(gh auth token)"

mkdir -p .tasks/autonomy/runtime/daemon
cat > .tasks/autonomy/runtime/daemon/odin.env <<EOF
GH_TOKEN=$ODIN_TOKEN
EOF
chmod 600 .tasks/autonomy/runtime/daemon/odin.env

screen -S odin-supervisor -X quit >/dev/null 2>&1 || true
screen -dmS odin-supervisor bash -lc "cd $HOME/Documents/Trisolaris && set -a && source .tasks/autonomy/runtime/daemon/odin.env && set +a && exec scripts/autonomy_supervisor_loop.sh >> .tasks/autonomy/runtime/daemon/odin-supervisor.log 2>&1"
```

### Salomon Worker (`salomon-shdow`)

```bash
cd ~/Documents/Trisolaris
gh auth switch --hostname github.com --user salomon-shdow
SALOMON_TOKEN="$(gh auth token)"

mkdir -p .tasks/autonomy/runtime/daemon
cat > .tasks/autonomy/runtime/daemon/salomon.env <<EOF
GH_TOKEN=$SALOMON_TOKEN
EOF
chmod 600 .tasks/autonomy/runtime/daemon/salomon.env

screen -S salomon-worker -X quit >/dev/null 2>&1 || true
screen -dmS salomon-worker bash -lc "cd $HOME/Documents/Trisolaris && set -a && source .tasks/autonomy/runtime/daemon/salomon.env && set +a && exec scripts/autonomy_agent_loop.sh salomon >> .tasks/autonomy/runtime/daemon/salomon-worker.log 2>&1"
```

### Stormforge Worker (`stormforge1`)

```bash
cd ~/Documents/Trisolaris
gh auth switch --hostname github.com --user stormforge1
STORMFORGE_TOKEN="$(gh auth token)"

mkdir -p .tasks/autonomy/runtime/daemon
cat > .tasks/autonomy/runtime/daemon/stormforge.env <<EOF
GH_TOKEN=$STORMFORGE_TOKEN
EOF
chmod 600 .tasks/autonomy/runtime/daemon/stormforge.env

screen -S stormforge-worker -X quit >/dev/null 2>&1 || true
screen -dmS stormforge-worker bash -lc "cd $HOME/Documents/Trisolaris && set -a && source .tasks/autonomy/runtime/daemon/stormforge.env && set +a && exec scripts/autonomy_agent_loop.sh stormforge >> .tasks/autonomy/runtime/daemon/stormforge-worker.log 2>&1"
```

### Kari Worker (`karikarikarikari`)

```bash
cd ~/Documents/Trisolaris
gh auth switch --hostname github.com --user karikarikarikari
KARI_TOKEN="$(gh auth token)"

mkdir -p .tasks/autonomy/runtime/daemon
cat > .tasks/autonomy/runtime/daemon/kari.env <<EOF
GH_TOKEN=$KARI_TOKEN
EOF
chmod 600 .tasks/autonomy/runtime/daemon/kari.env

screen -S kari-worker -X quit >/dev/null 2>&1 || true
screen -dmS kari-worker bash -lc "cd $HOME/Documents/Trisolaris && set -a && source .tasks/autonomy/runtime/daemon/kari.env && set +a && exec scripts/autonomy_agent_loop.sh kari >> .tasks/autonomy/runtime/daemon/kari-worker.log 2>&1"
```

## 6) Submit Jobs (Odin Only)

```bash
cd ~/Documents/Trisolaris
cp .tasks/autonomy/specs/job-template.json .tasks/autonomy/specs/my-job.json
# edit my-job.json
scripts/autonomy_submit.sh .tasks/autonomy/specs/my-job.json
```

## 7) Monitor and Operate
Check sessions:

```bash
screen -ls
```

Tail logs:

```bash
tail -f ~/Documents/Trisolaris/.tasks/autonomy/runtime/daemon/odin-supervisor.log
tail -f ~/Documents/Trisolaris/.tasks/autonomy/runtime/daemon/salomon-worker.log
tail -f ~/Documents/Trisolaris/.tasks/autonomy/runtime/daemon/stormforge-worker.log
tail -f ~/Documents/Trisolaris/.tasks/autonomy/runtime/daemon/kari-worker.log
```

Check queue state:

```bash
cd ~/Documents/Trisolaris
python3 scripts/autonomy.py status
python3 scripts/autonomy.py sync-board
```

Stop a loop:

```bash
screen -S odin-supervisor -X quit
screen -S salomon-worker -X quit
screen -S stormforge-worker -X quit
screen -S kari-worker -X quit
```

## 8) Daily Start for Existing Worker Machines

```bash
cd ~/Documents/Trisolaris
git checkout main
git pull --rebase
python3 scripts/autonomy.py status
screen -ls
```

## 9) Manual Fallback Mode
If autonomous loops are paused:
- use `.tasks/backlog.md`, `.tasks/in-progress.md`, `.tasks/done.md`
- use `.tasks/templates/task.md` and `.tasks/templates/handoff.md`
- follow `docs/COLLAB_WORKFLOW.md`

## 10) Troubleshooting
- `gh` account mismatch:
  - `gh auth switch --hostname github.com --user <expected-user>`
- SSH identity mismatch:
  - verify remote URL and `ssh -T` output per `docs/GITHUB_SETUP.md`
- worker not picking tasks:
  - confirm owner label (`agent:<owner>`) and state label (`autonomy:queued`) on task issue
  - run `python3 scripts/autonomy.py requeue-stale`
- stale/empty logs:
  - verify session exists with `screen -ls`
  - restart specific worker session
