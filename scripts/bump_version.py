#!/usr/bin/env python3
"""Bump the package version following SemVer.

Usage:
    python scripts/bump_version.py patch           # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor           # 0.1.0 -> 0.2.0
    python scripts/bump_version.py major           # 0.1.0 -> 1.0.0
    python scripts/bump_version.py set 1.2.3       # pin to a literal
    python scripts/bump_version.py show            # print current
    python scripts/bump_version.py patch --commit  # also git add + commit + tag

The canonical version lives in `claude_pdf2md/__init__.py`; `pyproject.toml`
reads it dynamically via hatch. This script rewrites only that one file.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = ROOT / "claude_pdf2md" / "__init__.py"
VERSION_RE = re.compile(r'^(__version__\s*=\s*")(\d+)\.(\d+)\.(\d+)(")\s*$', re.MULTILINE)


def _read_version() -> tuple[int, int, int]:
    text = INIT_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        sys.exit(f"error: could not find __version__ in {INIT_FILE}")
    return int(match.group(2)), int(match.group(3)), int(match.group(4))


def _write_version(major: int, minor: int, patch: int) -> str:
    new_version = f"{major}.{minor}.{patch}"
    text = INIT_FILE.read_text(encoding="utf-8")
    replaced, count = VERSION_RE.subn(rf'\g<1>{new_version}\g<5>', text)
    if count != 1:
        sys.exit(f"error: regex substitution failed in {INIT_FILE}")
    INIT_FILE.write_text(replaced, encoding="utf-8")
    return new_version


def _commit_and_tag(old: str, new: str) -> None:
    subprocess.run(["git", "add", str(INIT_FILE)], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: Bump version {old} → {new}"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["git", "tag", f"v{new}"], cwd=ROOT, check=True)
    print(f"  committed and tagged v{new}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "action",
        choices=("major", "minor", "patch", "show", "set"),
        help="Which component to bump, 'show' to print, or 'set' to pin an explicit version.",
    )
    parser.add_argument("value", nargs="?", help="Explicit version when action=set, e.g. 1.2.3")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="After bumping, stage + commit the change and create a vX.Y.Z git tag.",
    )
    args = parser.parse_args(argv)

    major, minor, patch = _read_version()
    current = f"{major}.{minor}.{patch}"

    if args.action == "show":
        print(current)
        return 0

    if args.action == "set":
        if not args.value:
            parser.error("set requires a VALUE argument (e.g. 1.2.3)")
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.value):
            parser.error(f"not a valid X.Y.Z version: {args.value!r}")
        new_major, new_minor, new_patch = (int(x) for x in args.value.split("."))
    elif args.action == "major":
        new_major, new_minor, new_patch = major + 1, 0, 0
    elif args.action == "minor":
        new_major, new_minor, new_patch = major, minor + 1, 0
    else:  # patch
        new_major, new_minor, new_patch = major, minor, patch + 1

    new = _write_version(new_major, new_minor, new_patch)
    print(f"{current} -> {new}")
    if args.commit:
        _commit_and_tag(current, new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
