#!/usr/bin/env python3
"""Keep the manuscript's version, abstract page, and citations in sync."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re


def prepare_updates(root, part, today):
    current = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", current):
        raise ValueError("VERSION must contain a version such as 1.0.1")
    numbers = list(map(int, current.split(".")))
    index = ("major", "minor", "patch").index(part)
    numbers[index] += 1
    numbers[index + 1:] = [0] * (2 - index)
    updated = ".".join(map(str, numbers))
    paths = ("CITATION.cff", "CITATION.bib", "README.md")
    texts = {path: (root / path).read_text(encoding="utf-8") for path in paths}
    old = re.escape(current)
    for name, pattern, count in (
        ("CITATION.cff", rf'(?m)^(?:  )?version: "{old}"$', 2),
        ("CITATION.bib", rf'Version {old}\.', 1),
        ("README.md", rf'(?m)^\*\*Version:\*\* {old} · ', 1),
    ):
        if len(re.findall(pattern, texts[name])) != count:
            raise ValueError(f"{name} does not match VERSION; no files changed")
    for name in paths:
        texts[name] = texts[name].replace(current, updated)
    texts["CITATION.cff"], count = re.subn(
        r"(?m)^date-released: \d{4}-\d{2}-\d{2}$",
        f"date-released: {today.isoformat()}", texts["CITATION.cff"],
    )
    if count != 1:
        raise ValueError("CITATION.cff needs one date-released field; no files changed")
    texts["README.md"], count = re.subn(
        r"(?m)^(\*\*Version:\*\* [0-9.]+ · )[^·\n]+( · )",
        lambda match: match[1] + f"{today.day} {today.strftime('%B %Y')}" + match[2],
        texts["README.md"],
    )
    if count != 1:
        raise ValueError("README.md needs one dated version field; no files changed")
    texts["VERSION"] = updated + "\n"
    return current, updated, texts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=("major", "minor", "patch"), default="patch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        current, updated, texts = prepare_updates(root, args.part, datetime.now(timezone.utc).date())
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(f"Would update manuscript metadata: {current} -> {updated}")
        return
    for name, text in texts.items():
        (root / name).write_text(text, encoding="utf-8")
    print(f"Updated manuscript metadata: {current} -> {updated}")


if __name__ == "__main__":
    main()
