#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/autonomy_agent_loop.sh <salomon|stormforge|kari>" >&2
  exit 2
fi

AGENT="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

python3 scripts/autonomy.py run-agent --agent "$AGENT" --loop
