#!/usr/bin/env python3
"""Reject formula downgrades and pin the first package to the agreed release."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

VERSION = re.compile(r"/releases/download/v([0-9]+\.[0-9]+\.[0-9]+)/")
INITIAL_VERSION = "0.9.0"


def version_from(source: str) -> tuple[int, int, int]:
    matches = set(VERSION.findall(source))
    if len(matches) != 1:
        raise ValueError("formula release URLs must select one plain semantic version")
    return tuple(int(part) for part in next(iter(matches)).split("."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formula", type=Path)
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    try:
        candidate = version_from(args.formula.read_text(encoding="utf-8"))
        base_ref = subprocess.run(
            ["git", "rev-parse", "--verify", args.base_ref],
            text=True,
            capture_output=True,
            check=False,
        )
        if base_ref.returncode:
            raise ValueError(f"cannot resolve current default branch {args.base_ref}")
        base = subprocess.run(
            ["git", "show", f"{args.base_ref}:Formula/sotto.rb"],
            text=True,
            capture_output=True,
            check=False,
        )
        if base.returncode:
            if candidate != version_from(
                f'https://github.com/getsotto/sotto/releases/download/v{INITIAL_VERSION}/sotto.tar.gz'
            ):
                raise ValueError(f"the initial formula must select v{INITIAL_VERSION}")
            print(f"initial formula version v{INITIAL_VERSION} is admitted")
            return 0
        current = version_from(base.stdout)
        if candidate <= current:
            raise ValueError(
                f"candidate version {candidate} must be newer than current default-branch version {current}"
            )
        print(f"formula version {candidate} is newer than default-branch version {current}")
    except (OSError, ValueError) as error:
        print(f"formula version admission failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
