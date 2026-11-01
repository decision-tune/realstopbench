#!/bin/bash
# Build a fresh single-commit public repository from the files tracked at HEAD.
#
#   scripts/export_public.sh DEST [--force]
#
# The tracked file list at HEAD is the allowlist (git archive): no history, no .git, no untracked or ignored
# files. The export must pass its own scripts/leak_check.py, its tests and MANIFEST.sha256 before it is
# committed as one commit, "RealStopBench preview", with the configured git identity. Nothing is pushed and
# no remote is added. --force replaces DEST only when it is an earlier export (one commit with that subject).
set -euo pipefail

usage() { echo "usage: $0 DEST [--force]" >&2; exit 2; }
[ $# -ge 1 ] || usage
DEST=$1
FORCE=${2:-}
[ -z "$FORCE" ] || [ "$FORCE" = "--force" ] || usage
SUBJECT="RealStopBench preview"
SRC=$(cd "$(dirname "$0")/.." && pwd)

if [ -n "$(git -C "$SRC" status --porcelain --untracked-files=no)" ]; then
    echo "export: tracked files have uncommitted changes; commit them first" >&2
    exit 1
fi

if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST")" ]; then
    if [ "$FORCE" != "--force" ]; then
        echo "export: $DEST is not empty (pass --force to replace an earlier export)" >&2
        exit 1
    fi
    if [ ! -d "$DEST/.git" ] ||
       [ "$(git -C "$DEST" rev-list --count HEAD 2>/dev/null)" != "1" ] ||
       [ "$(git -C "$DEST" log -1 --format=%s 2>/dev/null)" != "$SUBJECT" ]; then
        echo "export: $DEST does not look like an earlier export; refusing to replace it" >&2
        exit 1
    fi
    rm -rf "$DEST"
fi

mkdir -p "$DEST"
git -C "$SRC" archive --format=tar HEAD | tar -xf - -C "$DEST"

cd "$DEST"
git init -q -b main
git add -A
python3 -I scripts/leak_check.py --root "$DEST"
python3 -I -m unittest discover -s tests -q
grep -v '^#' MANIFEST.sha256 | shasum -a 256 -c --quiet
git commit -q -m "$SUBJECT"
if [ -n "$(git remote)" ]; then
    echo "export: unexpected remote in $DEST" >&2
    exit 1
fi
echo "export: $DEST at $(git rev-parse HEAD) ($(git rev-list --count HEAD) commit, $(git ls-files | wc -l | tr -d ' ') files)"
