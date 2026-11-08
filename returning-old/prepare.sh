#!/usr/bin/env bash
# Export the two pinned upstream revisions and install offline test helpers.
set -euo pipefail
if [[ $# != 2 ]]; then
    printf 'Usage: bash prepare.sh POSTGRES_GIT_CHECKOUT NEW_WORK_DIR\n' >&2
    exit 2
fi
package=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$1
work=$2
. "$package/revisions.env"
test "$(git -C "$repo" rev-parse "$FIXED^")" = "$BEFORE"
umask 077
mkdir -- "$work"
mkdir -- "$work/evidence" "$work/judge-helpers"
git -C "$repo" archive --format=tar "$BEFORE" >"$work/before.tar"
git -C "$repo" archive --format=tar "$FIXED" >"$work/fixed.tar"
cp "$package/"{repro.py,run-pg.sh,judge.py,check-replication.sh,check-fdw.py,check-fdw.sh} "$work/judge-helpers/"
upstream="$work/judge-helpers/upstream-isolation"
mkdir -p "$upstream/specs" "$upstream/expected"
for test in eval-plan-qual-trigger merge-match-recheck; do
    git -C "$repo" show "$FIXED:src/test/isolation/specs/$test.spec" >"$upstream/specs/$test.spec"
    git -C "$repo" show "$FIXED:src/test/isolation/expected/$test.out" >"$upstream/expected/$test.out"
done
git -C "$repo" show --format=fuller --no-ext-diff "$FIXED" >"$work/evidence/upstream-fix.patch"
printf 'Prepared pinned sources and offline helpers in %s\n' "$work"
