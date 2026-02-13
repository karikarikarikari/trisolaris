#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv_local import load_dotenv_file


REPO_URL = "https://github.com/welttowelt/yggdrasil-runner.git"
DEST_DIR = "yggdrasil-runner"


ASKPASS_PY = """#!/usr/bin/env python3
import os
import sys

prompt = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
token = os.environ.get("GITHUB_TOKEN", "")
if not token:
    sys.exit(1)

if "username" in prompt:
    # GitHub accepts any non-empty username for PAT auth; this is a common convention.
    sys.stdout.write("x-access-token")
else:
    sys.stdout.write(token)
"""


def main() -> int:
    load_dotenv_file(".env.local")

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("Cannot clone: missing GITHUB_TOKEN in .env.local")
        print('Add a GitHub Personal Access Token to ".env.local" as GITHUB_TOKEN=... (do not paste it into chat).')
        print("Alternatively, make the repo public or clone it yourself into ./yggdrasil-runner.")
        return 2

    dest = Path(DEST_DIR)
    if dest.exists() and any(dest.iterdir()):
        print(f"Already exists: {DEST_DIR} (not cloning).")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    try:
        dest.rmdir()
    except OSError:
        pass

    with tempfile.TemporaryDirectory(prefix="git-askpass-") as td:
        askpass_path = Path(td) / "askpass.py"
        askpass_path.write_text(ASKPASS_PY, encoding="utf-8")
        askpass_path.chmod(askpass_path.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = str(askpass_path)

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, DEST_DIR],
                check=True,
                env=env,
            )
        except subprocess.CalledProcessError as e:
            print("git clone failed.")
            print(f"exit={e.returncode}")
            return e.returncode or 1

    print(f"Cloned into ./{DEST_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

