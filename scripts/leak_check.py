#!/usr/bin/env python3
"""Fail if a tracked file carries private or internal material.

  python3 -I scripts/leak_check.py [--root DIR]

Scans every file `git ls-files` lists under DIR (default: this repository), file paths included.
Exit 0 when clean, 1 with one `path:line: what` row per hit, 2 when DIR is not a git work tree.

Checks:
  - internal files tracked: any file ending in `_VERIFY.md`, any path with "notes" or "handoff" in its name;
  - private names (hashed below): the cloud decision model's provider and product names, an internal review
    tool, the owner's names and username, his personal email, a private repository name;
  - private context (plain patterns): a macOS home directory, the word for a portable computer, and references
    to internal log, scratch and verify files.

Allowlist (the only one): the provider's product name may appear in lowercase or uppercase identifier form in
.py and .sh files. These are code, which stays as written: the hook's `jev` function (patched off by the scorer)
and its `NO_QUIT_JEV` environment variable. The CLI forms `--judge jev` and `realstop judge jev` are allowed in
any file for the same reason. The capitalized product name is prose and always fails.

Sensitive terms are stored as sha256 of the lowercase token so this file does not print them. Short words are
trivially brute-forced from a hash, so this hides the terms from casual reading only; it is not a secret store.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys

HASHED = {
    "bc74d4c225d5b7d9149b370ab12c1f4aba41322dcb527d7ea1fa941028f176e8": "provider name",
    "9e66a118b9a0fb8cada5eb0f357806a21cc067fa4b9d9f76eb9773a24e022438": "provider product name",
    "693b286515bd1dd00865e7b60e4e53556537bbe4b1cc90ab608d94eb7c56fdc6": "internal review tool",
    "d81a65c1de02e17d9cfd88d68a8768fd1e3262f5e2fb859382fe33734b3f3ca8": "owner first name",
    "f8b003e0b309fd38ca34d66152b3f66a8bd7851166688a810ef51563b1140a65": "owner last name",
    "f7ca143516a7569fb234b7052c21929fbd1f1973971e4394db30395e8c8d7a74": "owner username",
    "3f0f5a0d949ebc15370766f62ef7b68260e837f18bece90b7119181c6b477c20": "owner username",
    "9c84563d433e6563b997fa8d7ac2b75da498720c9e72781606c179912b3f565a": "private repository name",
    "53a1c1c217dcde0d53666a89ea9f14122fb75806b35e903962d6eded90c06733": "owner personal email",
}
PRODUCT = "9e66a118b9a0fb8cada5eb0f357806a21cc067fa4b9d9f76eb9773a24e022438"
CODE_SUFFIXES = (".py", ".sh")
# Built from fragments so this file does not match itself.
PLAIN = [
    (re.compile("/" + "Users/"), "macOS home directory"),
    (re.compile("lap" + "top", re.I), "portable computer"),
    (re.compile("decision" + "-log", re.I), "internal log file"),
    (re.compile("scratch" + "pad", re.I), "scratch directory"),
    (re.compile("[A-Za-z0-9]+_" + "VERIFY" + r"\.md", re.I), "internal verify file"),
]
CLI_OK = re.compile(r"(--judge|realstop judge)\s+" + "j" + "ev" + r"\b")
WORD = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+")
INTERNAL_NAME = re.compile(r"(^|_)VERIFY\.md$|notes|handoff", re.I)


def _h(s):
    return hashlib.sha256(s.lower().encode("utf-8")).hexdigest()


def tokens(line):
    """Each word, each hyphen-joined run and each piece of it, and each email address."""
    for m in WORD.finditer(line):
        w = m.group(0)
        yield w
        if "-" in w:
            yield from w.split("-")
    for m in EMAIL.finditer(line):
        yield m.group(0)


def scan_line(path, line, hashed=HASHED):
    hits = []
    code = path.endswith(CODE_SUFFIXES)
    cli_free = CLI_OK.sub(" ", line)
    for tok in tokens(cli_free):
        h = _h(tok)
        if h not in hashed:
            continue
        if h == PRODUCT and code and (tok.islower() or tok.isupper()):
            continue
        hits.append(hashed[h])
    for rx, what in PLAIN:
        if rx.search(line):
            hits.append(what)
    return sorted(set(hits))


def tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit("leak check: %s is not a git work tree" % root)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def scan_tree(root, hashed=HASHED):
    hits = []
    files = tracked_files(root)
    for rel in files:
        if INTERNAL_NAME.search(os.path.basename(rel)):
            hits.append((rel, 0, "internal file is tracked"))
        for what in scan_line(rel, rel, hashed):
            hits.append((rel, 0, what + " in path"))
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            text = f.read().decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for what in scan_line(rel, line, hashed):
                hits.append((rel, n, what))
    return files, hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a = ap.parse_args(argv)
    try:
        files, hits = scan_tree(a.root)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    for rel, n, what in hits:
        print("%s:%d: %s" % (rel, n, what))
    print("leak check: %d tracked files, %d hits" % (len(files), len(hits)))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
