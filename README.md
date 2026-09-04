# blast-radius

**After a signature change, which callers did nobody update?**

An agent refactors a function, updates three call sites, says "done". CI breaks on the
fourth. This finds the fourth.

```bash
rote play run https://play.modiqo.ai/rajdeepkushwaha/blast-radius \
  root=/path/to/repo base_ref=origin/main
```

Zero credentials. Never imports or executes your code: only `ast.parse` and `git` touch it.

## Verdicts

| verdict | what is being claimed |
|---|---|
| `ORPHANED_CALL_SITE` | The call's arity no longer fits the new signature. |
| `REMOVED_SYMBOL_STILL_CALLED` | It calls something that existed at the base ref and is gone at HEAD. |
| `INDETERMINATE` | Arity cannot be established statically, for example argument unpacking. **Not a claim that the call is correct.** |

Files the refactor already touched are skipped: the question is what it *missed*.

## Why it does not blame the wrong function

A symbol is only matched through an import that actually binds it, **including relative
imports**. Two modules can both define `place_order`; only the one the caller actually
imported is ever reported.

That second half was not free. The first version handled absolute imports only. Run
against real Flask it found **nothing**, while a live caller sat at
`src/flask/sansio/scaffold.py:96` behind `from ..helpers import get_root_path`. Relative
imports are the normal shape inside a package, so a scan that ignores them reports a
clean refactor for almost every real repository.

## A deleted module used to be invisible

`git diff --name-only` lists a deleted file exactly like any other changed file, and the
only way the scan noticed was that opening it raised `FileNotFoundError`. That got recorded
as an unreadable path, with two consequences. A complete, correct scan was downgraded to
"incomplete scan, 1 path unreadable" — a warning that means something, spent on a file that
was *supposed* to be absent. And the module never entered the caller search at all, so
callers of a deleted module, the single largest blast radius there is, were the one thing
the play could not find.

It surfaced on `pallets/click`, comparing `HEAD` against `HEAD~50`:

```
## Incomplete scan (1 path(s) unreadable)
- tests/test_utils.py (FileNotFoundError)
```

That file was deleted upstream, not unreadable. Reading `--name-status --no-renames`
instead distinguishes the two, and a deleted file is now treated as what it is: every
symbol it defined is a removed symbol. Same repository, same two revisions, after the fix:

```
## No orphaned callers found
Every resolvable call site for 68 changed symbol(s) still fits its new signature.
```

`--no-renames` is deliberate. A rename arrives as a delete plus an add, which is what a
caller of the old module actually experiences.

## Where the idea comes from

*AI Agents in Depth*, section 7.5.2, lists **Incomplete edit** as a named failure class:

> "The function signature changed and three call sites were updated, but a fourth — a
> dynamic call, a binding in another language, a schema — was missed."
>
> "Take the set difference between the blast radius the Agent claimed and the real one."

That set difference is what this computes.

## Scope, stated plainly

Python only. Dynamic dispatch, `getattr`, cross-language bindings and schema definitions
are outside what a static reader can resolve, and calls it cannot resolve are reported as
`INDETERMINATE` rather than assumed fine. It reports any path it could not read, and shows
no findings at all when a step was blocked or truncated rather than passing a partial run
off as a clean one.

## Verify it

```bash
./build-fixture.sh
# prints the fixture path and its base commit, then the exact command to run
```

Both sides of the refactor are checked in, under `fixture/base` and `fixture/head`, so you
can read the change as a diff before trusting anything the play says about it. The script
builds them into a two-commit repository.

The fixture covers an arity increase, an arity decrease, a removed symbol, a whole deleted
module reached through a relative import, a changed method on a class, and argument
unpacking. Six findings, listed line by line in `EXPECT.md`.

It also covers two cases that must produce **nothing**: a call site the refactor did
update, and a same-named function in an unrelated module. If either shows up, the play is
guessing.

## Licence

MIT
