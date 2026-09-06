#!/usr/bin/env python3
"""Run the real analyzer against bundled cases before it is trusted with your code.

The assertions that prove this analyzer works live on the author's machine, where nobody
running the play can see them. This feeds the shipped blast.py its own bundled trees at
run time, and the presentation withholds its verdict if any case fails.

Two things a naive self-check misses, both because a green check above a broken analyzer
is worse than no check at all:

  every verdict needs a POSITIVE case. A rule with only negative cases can be deleted and
  the check still passes.

  DISCOVERY is checked, not only analysis. A comparison that finds no changed file at all
  reports a clean refactor, and no analysis case would notice.

    selfcheck.py  ->  JSON {passed, total, failures}
"""
import json
import os
import os, os, subprocess, sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
BLAST = os.path.join(HERE, "blast.py")

# file, symbol, verdict: exactly what the bundled trees must produce
EXPECTED = [
    ("src/admin.py", "cancel_order", "REMOVED_SYMBOL_STILL_CALLED"),
    ("src/reports.py", "archive_order", "REMOVED_SYMBOL_STILL_CALLED"),
    ("src/billing.py", "apply_discount", "ORPHANED_CALL_SITE"),
    ("src/carts.py", "Cart.add", "ORPHANED_CALL_SITE"),
    ("src/worker.py", "place_order", "ORPHANED_CALL_SITE"),
    ("src/dynamic.py", "place_order", "INDETERMINATE"),
]
# These must produce nothing. api.py was updated along with the signature, and
# other/consumer.py calls a different place_order in an unrelated module.
MUST_BE_SILENT = ["src/api.py", "other/consumer.py"]
MUST_COVER = {"REMOVED_SYMBOL_STILL_CALLED", "ORPHANED_CALL_SITE", "INDETERMINATE"}
# the deleted module is the case a filename-only diff cannot see
MUST_DISCOVER = {"src/archive.py", "src/orders.py"}


def run_json(args):
    # spawned as a literal so the command can be checked against deps.toml
    p = subprocess.run(["python3"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or "").strip()[:200] or "exit %d" % p.returncode)
    return json.loads(p.stdout)


def main():
    failures, total = [], 0
    seen = set()
    sigs = None
    found = None

    try:
        sigs = run_json([BLAST, "signatures", "demo", "demo"])
        out = run_json([BLAST, "callers", "demo", "demo", json.dumps(sigs)])
        found = {(f["file"], f["symbol"]): f["verdict"] for f in out.get("findings", [])}
    except Exception as e:
        total += len(EXPECTED) + len(MUST_BE_SILENT)
        failures.append({"case": "analyzer-runs", "detail": str(e)})

    if found is not None:
        for path, symbol, verdict in EXPECTED:
            total += 1
            seen.add(verdict)
            actual = found.get((path, symbol))
            if actual is None:
                failures.append({"case": "%s::%s" % (path, symbol),
                                 "detail": "expected %s, produced no finding" % verdict})
            elif actual != verdict:
                failures.append({"case": "%s::%s" % (path, symbol),
                                 "detail": "expected %s, produced %s" % (verdict, actual)})
        for path in MUST_BE_SILENT:
            total += 1
            hits = [k for k in found if k[0] == path]
            if hits:
                failures.append({"case": "silent:%s" % path,
                                 "detail": "must produce nothing, produced %d finding(s)"
                                           % len(hits)})

    # a rule with no positive case is a rule nothing protects
    for verdict in sorted(MUST_COVER - seen):
        total += 1
        failures.append({"case": "coverage:%s" % verdict,
                         "detail": "no bundled case asserts this verdict, so removing the "
                                   "rule that produces it would not be noticed"})

    # discovery: a comparison that sees nothing changed reports a clean refactor, and
    # every analysis case above would still pass on an empty finding set
    for want in sorted(MUST_DISCOVER):
        total += 1
        changed = set((sigs or {}).get("changed_files") or [])
        if want not in changed:
            failures.append({
                "case": "discovery:%s" % want,
                "detail": "the comparison did not report this file as changed, so nothing "
                          "downstream could have judged it"})


    # ---- git escapes non-ASCII paths before printing them, so a wrapper without
    # core.quotePath=false reads back a filename that does not exist. On a repository
    # with an accented filename this made blast-radius report no changes at all.
    total += 1
    try:
        _src = open(os.path.join(HERE, "blast.py"), encoding="utf-8").read()
        if "core.quotePath=false" not in _src:
            failures.append({
                "case": "paths:non-ascii-are-not-escaped",
                "detail": "the git wrapper does not pass core.quotePath=false, so a path "
                          "with a non-ASCII character comes back as an escaped string "
                          "and every file named that way is silently missed"})
    except OSError as _e:
        failures.append({"case": "paths:non-ascii-are-not-escaped",
                         "detail": "could not read the analyzer: %s" % _e})


    # ---- the play must run with no arguments at all
    #
    # A reviewer pulled all nine and found three that did not: two declared required
    # parameters and refused, and one defaulted to the reader's real history instead of
    # the bundled example. No self-check looked at the frontmatter, so nothing caught it.
    total += 1
    try:
        _mt = open(os.path.join(HERE, "..", "main.ts"), encoding="utf-8").read()
        _params = _mt.split("* parameters:")[1].split("* metadata:")[0] if "* parameters:" in _mt else ""
        _required = [ln for ln in _params.split(chr(10)) if "required: true" in ln]
        if _required:
            failures.append({
                "case": "runs-bare:no-required-parameters",
                "detail": "%d parameter(s) are declared required, so `rote play run "
                          "<this>` refuses instead of showing the bundled example"
                          % len(_required)})
    except Exception as _e:
        failures.append({"case": "runs-bare:no-required-parameters",
                         "detail": "could not read the frontmatter: %s" % _e})

    print(json.dumps({"passed": total - len(failures), "total": total,
                      "failures": failures[:10]}, separators=(",", ":")))


if __name__ == "__main__":
    main()
