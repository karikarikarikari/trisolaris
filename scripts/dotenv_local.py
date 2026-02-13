#!/usr/bin/env python3
"""
Minimal dotenv loader for ".env.local"-style files.

Goals:
- No external deps
- Safe around special chars (e.g. "!" in zsh) because we *parse*, we don't "source"
- Never prints secret values
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_dotenv_lines(lines: Iterable[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].lstrip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        # Drop inline comments for unquoted values: KEY=value # comment
        v = value.strip()
        if v and v[0] not in ("'", '"') and " #" in v:
            v = v.split(" #", 1)[0].rstrip()

        out[key] = _strip_quotes(v)
    return out


def parse_dotenv_file(path: str | os.PathLike) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    return parse_dotenv_lines(p.read_text(encoding="utf-8").splitlines())


def load_dotenv_file(path: str | os.PathLike, *, override: bool = False) -> Tuple[int, int]:
    """
    Loads KEY=VALUE pairs into os.environ.

    Returns (loaded, skipped) counts.
    """
    data = parse_dotenv_file(path)
    loaded = 0
    skipped = 0
    for k, v in data.items():
        if not override and k in os.environ:
            skipped += 1
            continue
        os.environ[k] = v
        loaded += 1
    return loaded, skipped


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Load .env.local into the current process (no secrets printed).")
    ap.add_argument("--path", default=".env.local", help="dotenv file path (default: .env.local)")
    ap.add_argument("--override", action="store_true", help="override existing env vars")
    args = ap.parse_args()

    loaded, skipped = load_dotenv_file(args.path, override=args.override)
    print(f"Loaded {loaded} vars (skipped {skipped}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

