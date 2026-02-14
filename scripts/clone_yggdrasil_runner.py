#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from dotenv_local import load_dotenv_file


DEFAULT_REPO = "welttowelt/yggdrasil-runner"
DEFAULT_DEST_DIR = "yggdrasil-runner"


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

def _parse_repo_input(repo_input: str) -> tuple[str, str | None]:
    """
    Returns (repo_url, owner_repo_if_github).

    - If repo_input looks like "owner/name", treat it as GitHub and build a https URL.
    - If it looks like a URL/SSH remote, use it as-is and skip API existence checks.
    """
    repo_input = repo_input.strip()
    if not repo_input:
        raise ValueError("repo input is empty")

    if "://" in repo_input or repo_input.startswith("git@"):
        return repo_input, None

    if repo_input.count("/") != 1:
        raise ValueError('repo must be "owner/name" or a full git remote URL')

    return f"https://github.com/{repo_input}.git", repo_input


def _github_repo_check(owner_repo: str, token: str) -> tuple[int, str]:
    url = f"https://api.github.com/repos/{owner_repo}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "new-project-utils",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            msg = json.loads(body.decode("utf-8")).get("message") or ""
        except Exception:
            msg = ""
        return e.code, msg


def main() -> int:
    ap = argparse.ArgumentParser(description="Clone a GitHub repo using GITHUB_TOKEN from .env.local.")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f'repo "owner/name" (default: {DEFAULT_REPO})')
    ap.add_argument("--dest", default="", help=f'destination folder (default: {DEFAULT_DEST_DIR} or repo name)')
    args = ap.parse_args()

    load_dotenv_file(".env.local")

    token = os.environ.get("GITHUB_TOKEN", "")
    repo_url, owner_repo = _parse_repo_input(args.repo)

    # Derive a reasonable default destination.
    dest_dir = args.dest.strip()
    if not dest_dir:
        if owner_repo:
            dest_dir = owner_repo.split("/", 1)[1]
        else:
            dest_dir = DEFAULT_DEST_DIR

    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()):
        print(f"Already exists: {dest_dir} (not cloning).")
        return 0

    # If we can, do an API existence/access check first so failures are clearer than git's 403/404 messages.
    if owner_repo and token:
        status, msg = _github_repo_check(owner_repo, token)
        if status != 200:
            print(f"GitHub API check failed for {owner_repo}: HTTP {status}" + (f" ({msg})" if msg else ""))
            print("Fix:")
            print("- Verify the repo path is correct")
            print('- Ensure your token has repo access to this repository and "Contents: Read" permission')
            return 2

    if not token:
        # Public clone attempt without auth. Also disable any credential helpers to avoid stale local creds.
        try:
            subprocess.run(
                ["git", "-c", "credential.helper=", "clone", "--depth", "1", repo_url, dest_dir],
                check=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
        except subprocess.CalledProcessError as e:
            print("git clone failed.")
            print(f"exit={e.returncode}")
            return e.returncode or 1
        print(f"Cloned into ./{dest_dir}")
        return 0

    # Authenticated clone using GIT_ASKPASS. Clone into a temp dir first so failures don't leave partial dirs.
    with tempfile.TemporaryDirectory(prefix=f".tmp-clone-{dest_dir}-", dir=str(Path.cwd())) as clone_td:
        tmp_dest = Path(clone_td) / dest_dir

        with tempfile.TemporaryDirectory(prefix="git-askpass-") as td:
            askpass_path = Path(td) / "askpass.py"
            askpass_path.write_text(ASKPASS_PY, encoding="utf-8")
            askpass_path.chmod(askpass_path.stat().st_mode | stat.S_IXUSR)

            env = dict(os.environ)
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["GIT_ASKPASS"] = str(askpass_path)

            try:
                subprocess.run(
                    # Disable any configured credential helpers (e.g. osxkeychain) so we
                    # don't accidentally reuse stale/bad stored GitHub creds.
                    ["git", "-c", "credential.helper=", "clone", "--depth", "1", repo_url, str(tmp_dest)],
                    check=True,
                    env=env,
                )
            except subprocess.CalledProcessError as e:
                print("git clone failed.")
                print(f"exit={e.returncode}")
                return e.returncode or 1

        tmp_dest.replace(dest)

    print(f"Cloned into ./{dest_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
