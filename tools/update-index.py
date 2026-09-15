#!/usr/bin/env python3
"""
Refresh the version / last-updated labels in index.html.

Every PDF in this repo is published by sync-docs.sh, which commits it with the
subject "Update {type} {catalog} ({lang}) to v{X.Y.Z}". That commit is the
authority for both facts we want to show:

    version      parsed out of the commit subject
    last updated the commit date of the most recent change to that file

The PDF's own printed stamp is deliberately NOT used - it extracts unreliably
from letter-spaced artwork, and several documents yield nothing at all.

The labels are written into index.html as plain text, so the published page
needs no JavaScript and no manifest fetch. Run with no arguments to rebuild
from git alone:

    tools/update-index.py

During a publish the new PDF is not committed yet, so its facts are supplied
on the command line:

    tools/update-index.py --set protocols/protocol-ATC01-H-en.pdf=2.0.1

--check reports whether index.html is already current without writing to it.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "index.html")

# Matches the subject sync-docs.sh writes; the looser second form catches
# anything committed by hand before that convention settled.
SUBJECT_VERSION = re.compile(r"\bto v(\d+\.\d+\.\d+)\b")
ANY_VERSION = re.compile(r"\bv(\d+\.\d+\.\d+)\b")

LI = re.compile(r"[ \t]*<li\b[^>]*>.*?</li>\n", re.S)
HREF = re.compile(r'href="([^"]+\.pdf)"')
META = re.compile(r"[ \t]*<span class=\"doc-meta\">.*?</span>\n", re.S)


def git(*args):
    return subprocess.run(
        ["git", "-C", REPO, *args], capture_output=True, text=True
    ).stdout.strip()


def facts_from_git(path):
    """(version, iso_date) for the last commit touching path, or None."""
    out = git("log", "-1", "--format=%s%x00%ad", "--date=short", "--", path)
    if not out or "\0" not in out:
        return None
    subject, when = out.split("\0", 1)
    m = SUBJECT_VERSION.search(subject) or ANY_VERSION.search(subject)
    if not m:
        return None
    return m.group(1), when.strip()


def parse_override(text):
    """path=version or path=version,YYYY-MM-DD (date defaults to today)."""
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"expected path=version, got {text!r}")
    path, value = text.split("=", 1)
    version, _, when = value.partition(",")
    when = when or date.today().isoformat()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise argparse.ArgumentTypeError(f"not a version: {version!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
        raise argparse.ArgumentTypeError(f"not a date: {when!r}")
    return path.lstrip("./"), (version, when)


def render(html, overrides):
    """Rewrite the doc-meta span of every <li> that links to a PDF."""
    missing = []

    def fix(match):
        block = match.group(0)
        href = HREF.search(block)
        if not href:
            return block
        path = href.group(1)

        facts = overrides.get(path) or facts_from_git(path)
        indent = re.match(r"[ \t]*", block).group(0)
        block = META.sub("", block)
        if not facts:
            missing.append(path)
            return block

        version, when = facts
        span = (
            f'{indent}  <span class="doc-meta">v{version}'
            f' &middot; Updated {when}</span>\n'
        )
        return block.replace(f"{indent}</li>\n", span + f"{indent}</li>\n")

    return LI.sub(fix, html), missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--set",
        dest="overrides",
        metavar="PATH=VERSION[,DATE]",
        type=parse_override,
        action="append",
        default=[],
        help="facts for a PDF that is not committed yet (repeatable)",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if index.html is out of date; write nothing",
    )
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    with open(INDEX, encoding="utf-8") as fh:
        before = fh.read()

    after, missing = render(before, dict(args.overrides))

    for path in missing:
        print(f"warning: no version found in git history for {path}", file=sys.stderr)

    if args.check:
        if after != before:
            print("index.html is out of date - run tools/update-index.py")
            return 1
        if not args.quiet:
            print("index.html is up to date")
        return 0

    if after == before:
        if not args.quiet:
            print("index.html already current")
        return 0

    with open(INDEX, "w", encoding="utf-8") as fh:
        fh.write(after)
    if not args.quiet:
        print("index.html updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
