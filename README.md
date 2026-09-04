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
cd fixture && git init -q && git add -A && git commit -qm base && git branch -M main
# then apply the refactor in EXPECT.md and run against main
```

The bundled fixture covers an arity increase, an arity decrease, a removed symbol, a
changed method on a class, argument unpacking, a call site the refactor did update, and a
same-named function in an unrelated module. The last two must produce nothing.

## Licence

MIT
