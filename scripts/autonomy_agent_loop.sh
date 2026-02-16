#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/autonomy_agent_loop.sh <salomon|stormforge|kari>" >&2
  exit 2
fi

AGENT="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

while true; do
  if python3 -u scripts/autonomy.py run-agent --agent "$AGENT" --loop; then
    printf '[%s] [autonomy] run-agent loop for %s exited cleanly; restarting\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$AGENT" >&2
  else
    status=$?
    printf '[%s] [autonomy] run-agent loop for %s exited with code %s; restarting\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$AGENT" "$status" >&2
  fi
  sleep 5
done
