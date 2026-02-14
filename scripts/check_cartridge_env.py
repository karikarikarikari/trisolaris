#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

from dotenv_local import load_dotenv_file


def _mask(s: str) -> str:
    if not s:
        return ""
    return "[set]"


def main() -> int:
    env_path = Path(".env.local")
    load_dotenv_file(env_path)

    user = os.environ.get("CARTRIDGE_USERNAME", "")
    pw = os.environ.get("CARTRIDGE_PASSWORD", "")

    ok = True
    if not user:
        print("Missing CARTRIDGE_USERNAME in .env.local")
        ok = False
    if not pw:
        print("Missing CARTRIDGE_PASSWORD in .env.local")
        ok = False

    if ok:
        print(f"CARTRIDGE_USERNAME={user}")
        print(f"CARTRIDGE_PASSWORD={_mask(pw)}")
        return 0

    print('Tip: edit ".env.local" (it is gitignored) to add the missing values.')
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
