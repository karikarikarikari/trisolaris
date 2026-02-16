#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: scripts/autonomy_submit.sh <spec.json>" >&2
  exit 2
fi

SPEC="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

python3 scripts/autonomy.py submit --spec "$SPEC" --creator odin
