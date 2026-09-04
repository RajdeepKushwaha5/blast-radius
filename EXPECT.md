# Expected findings

```sh
./build-fixture.sh                 # prints the fixture path and its base commit
rote play run https://play.modiqo.ai/rajdeepkushwaha/blast-radius \
  root=/tmp/blast-fixture base_ref=<the base commit it printed>
```

The base commit hash differs on every build, because the fixture is constructed locally.
The script prints it.

| file | line | symbol | expected |
|---|---|---|---|
| src/worker.py | 3 | place_order | ORPHANED_CALL_SITE (2 given, 3 required) |
| src/admin.py | 3 | cancel_order | REMOVED_SYMBOL_STILL_CALLED |
| src/reports.py | 3 | archive_order | REMOVED_SYMBOL_STILL_CALLED (whole module deleted, relative import) |
| src/billing.py | 3 | apply_discount | ORPHANED_CALL_SITE (3 given, max 2) |
| src/carts.py | 3 | Cart.add | ORPHANED_CALL_SITE (1 given, 2 required) |
| src/dynamic.py | 3 | place_order | INDETERMINATE (argument unpacking) |

Six findings, and nothing else.

## Negative controls

| file | expected |
|---|---|
| src/api.py | none — the call site was updated along with the signature |
| other/consumer.py | none — a different `place_order`, same name, different module |

If either of these ever appears in the output, the play is guessing.

## What src/reports.py covers

Its module, `src/archive.py`, is deleted in the refactor. `git diff --name-only` cannot
tell a deleted file from an unreadable one, so the deletion was reported as a gap in the
scan and its symbols never entered the caller search at all. A whole module disappearing
is the largest blast radius there is, and it was the one case that produced nothing. Its
import is relative, so this case covers relative-import resolution at the same time.
