#!/bin/sh
# Builds the two-commit fixture repository the findings in EXPECT.md refer to, then runs
# the play against it. The two trees are checked in under fixture/base and fixture/head so
# the refactor is reviewable as a diff before you trust anything the play says about it.
set -e
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-/tmp/blast-fixture}

rm -rf "$out"; mkdir -p "$out"
cp -r "$here/fixture/base/." "$out/"
cd "$out"
git init -q .
git add -A
git -c user.email=fixture@example.invalid -c user.name=fixture commit -qm base
base=$(git rev-parse HEAD)

find "$out" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -r "$here/fixture/head/." "$out/"
git add -A
git -c user.email=fixture@example.invalid -c user.name=fixture commit -qm refactor

echo "fixture at $out, base commit $base"
echo
echo "  rote play run https://play.modiqo.ai/rajdeepkushwaha/blast-radius root=$out base_ref=$base"
