#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Iterable, List, Set


def _read_seed_names(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    out: Set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.add(s)
    return out


def _unique_in_order(items: Iterable[str], *, avoid: Set[str]) -> List[str]:
    out: List[str] = []
    avoid_lower = {x.lower() for x in avoid}
    seen_lower: Set[str] = set()
    for x in items:
        xl = x.lower()
        if xl in avoid_lower or xl in seen_lower:
            continue
        if not x.isascii():
            continue
        if any(ch.isspace() for ch in x):
            continue
        out.append(x)
        seen_lower.add(xl)
    return out


def generate_names(*, avoid: Set[str]) -> List[str]:
    # Handcrafted puns first (same vibe as your examples).
    handcrafted = [
        "Noamly",
        "Noaminal",
        "AriGato",
        "AriGorithm",
        "EliVator",
        "EliGator",
        "ShaiNing",
        "YaelLicious",
        "Tamarrow",
        "Eitanic",
        "GideonIt",
        "BenThere",
        "BenEvolent",
        "YossiTive",
        "MoisheVision",
        "Shloptimization",
        "DovahNice",
        "LeviTation",
        "YoniCorn",
        "Amitation",
        "ItzaPizza",
        "RuthBusted",
        "LeahpYear",
        "Miriamory",
        "EstherEgg",
        "Nadavantage",
        "Aviation",
        "ZoharGanic",
        "SimchaChing",
    ]

    bases = [
        "Noam",
        "Ari",
        "Eli",
        "Shai",
        "Yael",
        "Tamar",
        "Eitan",
        "Gideon",
        "Ben",
        "Yossi",
        "Moishe",
        "Shlomo",
        "Dov",
        "Levi",
        "Yoni",
        "Amit",
        "Itza",
        "Ruth",
        "Leah",
        "Miriam",
        "Esther",
        "Nadav",
        "Avi",
        "Zohar",
        "Simcha",
        "Chaim",
        "Yaakov",
        "Tzvi",
        "Oren",
        "Tal",
        "Lior",
        "Gal",
        "Dor",
        "Bar",
        "Eden",
        "Shira",
        "Omri",
        "Ilan",
        "Kobi",
        "Itai",
        "Neta",
    ]

    # Suffix fragments that keep the same portmanteau feel.
    suffixes = [
        "nom",
        "ly",
        "inal",
        "Gorithm",
        "Tmetic",
        "Matic",
        "Gible",
        "Fi",
        "ocity",
        "athon",
        "ternal",
        "jitsu",
        "ified",
        "code",
        "motion",
        "tail",
        "tated",
        "iverse",
        "tron",
        "abitz",
        "less",
        "zer",
        "mix",
        "oid",
        "ocado",
        "shift",
        "izon",
        "smash",
        "vator",
        "gator",
        "Tation",
        "Tastic",
        "Scope",
        "Stack",
        "Script",
        "Ware",
        "Bytes",
        "Logic",
    ]

    combos: List[str] = []
    for b in bases:
        for s in suffixes:
            combos.append(f"{b}{s}")

    return _unique_in_order(handcrafted + combos, avoid=avoid)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate new account names based on account_names_seed.txt style.")
    ap.add_argument("--count", type=int, default=40, help="how many names to generate (default: 40)")
    ap.add_argument("--seed-file", default="account_names_seed.txt", help="seed list file (default: account_names_seed.txt)")
    ap.add_argument(
        "--out",
        default="",
        help='output file path (default: write to "generated_account_names_YYYY-MM-DD.txt" in repo root)',
    )
    args = ap.parse_args()

    seed_file = Path(args.seed_file)
    avoid = _read_seed_names(seed_file)

    names = generate_names(avoid=avoid)
    if args.count <= 0:
        print("count must be > 0")
        return 2
    if args.count > len(names):
        print(f"Requested {args.count} names but only {len(names)} available.")
        return 2

    out_path = Path(args.out) if args.out else Path(f"generated_account_names_{dt.date.today().isoformat()}.txt")
    out_path.write_text("\n".join(names[: args.count]) + "\n", encoding="utf-8")
    print(f"Wrote {args.count} names to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
