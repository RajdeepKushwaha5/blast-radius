#!/usr/bin/env python3
"""Blast-radius guard: after a signature change, which callers did nobody update?

    blast.py signatures <root> <base_ref>
    blast.py callers    <root> <base_ref> <signatures-json>

Pass root=demo to compare the two bundled trees instead of two git revisions, so the play
can be tried on a machine with nothing set up.

Compares a repository at two git revisions with ast, then resolves call sites across the
whole tree. A symbol is only matched through an import that actually binds it, including
relative imports, so an unrelated function of the same name elsewhere is never blamed.
Anything that cannot be resolved statically is INDETERMINATE, never assumed correct.
Never executes the code it reads: only ast.parse and git touch it.
"""
import ast, json, os, subprocess, sys

sys.dont_write_bytecode = True
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", ".mypy_cache"}


def git(args, cwd):
    try:
        p = subprocess.run(["git", "-c", "core.quotePath=false"] + args, cwd=cwd, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def modname(rel):
    return rel[:-3].replace(os.sep, ".").replace("/", ".")


def signatures(src):
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out

    def sig(fn, drop_self=0):
        a = fn.args
        pos = len(a.posonlyargs) + len(a.args) - drop_self
        return [pos - len(a.defaults), None if a.vararg else pos]

    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[n.name] = sig(n)
        elif isinstance(n, ast.ClassDef):
            for m in n.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[n.name + "." + m.name] = sig(m, drop_self=1)
    return out


def resolve_relative(pkg, module, level):
    """A relative import inside a package resolves against that package.
    Missing them makes the whole scan silently find nothing, which is worse
    than finding nothing loudly."""
    if not level:
        return module
    parts = [p for p in (pkg.split(".") if pkg else []) if p]
    keep = parts[:len(parts) - (level - 1)] if level > 1 else parts
    return ".".join(keep + ([module] if module else []))


def bindings(tree, changed_mods, pkg):
    b = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod = resolve_relative(pkg, n.module, n.level)
            if mod in changed_mods:
                for a in n.names:
                    b[a.asname or a.name] = [mod, a.name]
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name in changed_mods:
                    b[a.asname or a.name] = [a.name, None]
    return b


def demo_trees():
    """The bundled demo, so the play can be tried on a machine with nothing set up."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "demo", "head"), os.path.join(here, "demo", "base")


def collect_changes_trees(head, base):
    """Compare two directory trees rather than two git revisions.

    Same question, one less prerequisite. A play that needs a repository and a resolvable
    base ref before it can show anything cannot be tried on a clean machine, and the first
    thing a reader wants is to see what the output looks like.
    """
    blocked = []

    def tree(d):
        out = {}

        # os.walk drops a directory it cannot open, and with no callback it drops it in
        # SILENCE -- the comparison then comes back looking complete. This is the path a
        # stranger on a clean machine hits first, which is exactly why it is the worst
        # place to be quiet. The git path below already passes onerror; this did not.
        def note(err):
            where = getattr(err, "filename", "") or "?"
            try:
                where = os.path.relpath(where, d)
            except ValueError:
                pass
            blocked.append({"path": where, "reason": type(err).__name__})

        for dirpath, dirnames, files in os.walk(d, onerror=note):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for fn in files:
                if fn.endswith(".py"):
                    full = os.path.join(dirpath, fn)
                    out[os.path.relpath(full, d)] = full
        return out

    b, h = tree(base), tree(head)
    # a directory neither tree could open belongs in the same list as a file that could
    # not be read: both mean this comparison saw less than it appears to have seen
    changed, affected, unreadable = [], {}, list(blocked)

    def read(path, rel):
        try:
            return open(path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as e:
            unreadable.append({"path": rel, "reason": type(e).__name__})
            return None

    for rel in sorted(b):
        old = read(b[rel], rel)
        if old is None:
            continue
        if rel in h:
            new = read(h[rel], rel)
            if new is None:
                continue
            if new == old:
                continue
        else:
            new = ""   # absent from head: deleted, exactly as in the git path
        changed.append(rel)
        oldsigs, newsigs = signatures(old), signatures(new)
        delta = {}
        for name, osig in oldsigs.items():
            if name not in newsigs:
                delta[name] = None
            elif newsigs[name] != osig:
                delta[name] = newsigs[name]
        if delta:
            affected[modname(rel)] = delta

    # a file the refactor added is part of the refactor, so it is not a missed call site
    changed.extend(sorted(rel for rel in h if rel not in b))
    return changed, affected, unreadable


def collect_changes(root, base):
    # --name-status, not --name-only: a deleted file is absent from the working tree for
    # a reason, and cannot be told apart from an unreadable one by the path alone.
    # --no-renames so a rename arrives as a delete plus an add, which is what a caller of
    # the old module actually experiences.
    raw = git(["diff", "--name-status", "--no-renames", base + "...HEAD", "--", "*.py"],
              root) or ""
    changed, deleted = [], set()
    for line in raw.splitlines():
        parts = [c for c in line.split("	") if c]
        if len(parts) < 2:
            continue
        status, path = parts[0].strip(), parts[-1].strip()
        if not path.endswith(".py"):
            continue
        changed.append(path)
        if status.startswith("D"):
            deleted.add(path)
    affected, unreadable = {}, []
    for f in changed:
        old = git(["show", base + ":" + f], root)
        if old is None:
            continue
        if f in deleted:
            # Every symbol a deleted file defined is a removed symbol, which is the
            # largest blast radius there is. Reporting it as unreadable cried wolf about
            # a complete scan and, worse, dropped the module from the caller search
            # entirely, so callers of a deleted module were never looked for.
            new = ""
        else:
            try:
                new = open(os.path.join(root, f), encoding="utf-8").read()
            except (OSError, UnicodeDecodeError) as e:
                unreadable.append({"path": f, "reason": type(e).__name__})
                continue
        o, n = signatures(old), signatures(new)
        delta = {}
        for name, osig in o.items():
            if name not in n:
                delta[name] = None
            elif n[name] != osig:
                delta[name] = n[name]
        if delta:
            affected[modname(f)] = delta
    return changed, affected, unreadable


def find_callers(root, base, changed, affected, unreadable, head="HEAD"):
    findings, changed_set = [], set(changed)
    if not affected:
        return findings

    def onerr(e):
        unreadable.append({"path": os.path.relpath(getattr(e, "filename", "?"), root),
                           "reason": type(e).__name__})

    for dirpath, dirnames, files in os.walk(root, onerror=onerr):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if rel in changed_set:
                continue
            try:
                tree = ast.parse(open(os.path.join(dirpath, fn), encoding="utf-8").read())
            except SyntaxError:
                continue
            except (OSError, UnicodeDecodeError) as e:
                unreadable.append({"path": rel, "reason": type(e).__name__})
                continue
            pkg = os.path.dirname(rel).replace(os.sep, ".").replace("/", ".")
            bound = bindings(tree, affected, pkg)
            if not bound:
                continue
            cls_bound = {k: v for k, v in bound.items() if v[1]}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                qual = None
                mod = None
                if isinstance(node.func, ast.Name) and node.func.id in bound:
                    mod, qual = bound[node.func.id]
                elif isinstance(node.func, ast.Attribute):
                    v = node.func.value
                    if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id in cls_bound:
                        mod, cls = cls_bound[v.func.id]
                        qual = cls + "." + node.func.attr
                    elif isinstance(v, ast.Name) and v.id in bound and bound[v.id][1] is None:
                        mod = bound[v.id][0]
                        qual = node.func.attr
                if qual is None or mod not in affected or qual not in affected[mod]:
                    continue
                sig = affected[mod][qual]
                given = len(node.args) + len(node.keywords)
                starred = any(isinstance(a, ast.Starred) for a in node.args)
                kwsplat = any(k.arg is None for k in node.keywords)
                if starred or kwsplat:
                    verdict = "INDETERMINATE"
                    why = "argument unpacking; arity not statically known"
                elif sig is None:
                    verdict = "REMOVED_SYMBOL_STILL_CALLED"
                    why = "defined at %s, absent at %s" % (base, head)
                elif given < sig[0]:
                    verdict = "ORPHANED_CALL_SITE"
                    why = "passes %d, now requires %d" % (given, sig[0])
                elif sig[1] is not None and given > sig[1]:
                    verdict = "ORPHANED_CALL_SITE"
                    why = "passes %d, now accepts at most %d" % (given, sig[1])
                else:
                    continue
                findings.append({"file": rel, "line": node.lineno, "symbol": qual,
                                 "module": mod, "verdict": verdict, "reason": why})
    return findings


def main():
    if len(sys.argv) < 4:
        sys.stderr.write("usage: blast.py signatures|callers <root> <base_ref> [json]\n")
        sys.exit(2)
    mode = sys.argv[1]
    demo = sys.argv[2] == "demo"
    if demo:
        root, base_tree = demo_trees()
        base = "the bundled base tree"
    else:
        if not os.path.isabs(sys.argv[2]):
            sys.stderr.write("root must be an ABSOLUTE path, or the word demo. Got: " + sys.argv[2] + chr(10) + "A step runs inside rote's own workspace, not the directory you were standing in, so a relative path silently scans the wrong tree. There is no correct fallback: the step cannot see your shell directory." + chr(10))
            sys.exit(2)
        root = os.path.abspath(sys.argv[2])
        base_tree = None
        base = sys.argv[3]
    if not os.path.isdir(root):
        sys.stderr.write("error: no such directory: %s\n" % root)
        sys.exit(1)
    if not demo and git(["rev-parse", "--verify", "--quiet", base + "^{commit}"],
                        root) is None:
        sys.stderr.write("error: cannot resolve base ref %r in %s\n" % (base, root))
        sys.exit(1)

    if mode == "signatures":
        changed, affected, unreadable = (collect_changes_trees(root, base_tree) if demo
                                         else collect_changes(root, base))
        print(json.dumps({"base": base, "changed_files": changed, "affected": affected,
                          "unreadable": unreadable}, separators=(",", ":")))
        return

    up = json.loads(sys.argv[4])
    changed = up.get("changed_files", [])
    affected = up.get("affected", {})
    unreadable = list(up.get("unreadable", []))
    findings = find_callers(root, base, changed, affected, unreadable,
                            head="the bundled head tree" if demo else "HEAD")
    symbols = sorted(s for d in affected.values() for s in d)
    print(json.dumps({"base": base, "changed_files": changed, "affected_symbols": symbols,
                      "unreadable": unreadable,
                      "findings": sorted(findings, key=lambda f: (f["file"], f["line"]))},
                     separators=(",", ":")))


if __name__ == "__main__":
    main()
