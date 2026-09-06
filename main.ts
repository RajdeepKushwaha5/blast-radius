#!/usr/bin/env -S rote play run
/**
 * blast-radius
 *
 * After a signature change, which callers did nobody update?
 *
 * @rote-frontmatter
 * ---
 * name: blast-radius
 * source_url: https://github.com/RajdeepKushwaha5/blast-radius
 * tags:
 * - refactoring
 * - static-analysis
 * - python
 * - code-review
 * - effect-read-only
 * output:
 *   format: json
 * description: You change a function, update the callers you can see, and miss one. This finds the one you missed. It reads your repository at two git revisions, finds every function, method and class whose signature changed or that got deleted, then checks every call to them. ORPHANED_CALL_SITE means the call passes the wrong number of arguments now. REMOVED_SYMBOL_STILL_CALLED means the call points at something that no longer exists, including whole files the refactor deleted. INDETERMINATE means the call uses argument unpacking, so the count cannot be known by reading it, and that is reported rather than assumed fine. It only blames a call if that file actually imports the thing, so a function with the same name in another module is left alone. Relative imports count too. Files the refactor already changed are skipped, because the question is what it missed. Pass root=demo base_ref=demo to try it with nothing set up, on two folders shipped with the play, so you do not even need a repository. Before it reads your code it runs its own test cases through the same analyzer and prints the result. If those fail it shows you that instead of findings. It never runs or imports your code. Read-only, no credentials, no network. Needs python3 and git.
 * provenance:
 *   author: rajdeepkushwaha
 * parameters:
 * - name: root
 *   param_type: string
 *   required: false
 *   default: demo
 *   description: Absolute path to the git repository to scan, or `demo` for the bundled trees
 * - name: base_ref
 *   param_type: string
 *   required: false
 *   default: demo
 *   description: The revision to compare against, such as origin/main; `demo` with root=demo
 * metadata:
 *   rote_version: 0.79.0
 *   version: 0.3.6
 *   status: released
 *   kind: atomic
 *   flow_type: sequential
 *   execution_model: steps_with_presentation
 *   format: typescript
 *   requires_sessions: false
 * presentation_fixtures:
 *   selfcheck: resources/presentation-fixtures/selfcheck/fixture.yaml
 *   signatures: resources/presentation-fixtures/signatures/fixture.yaml
 *   callers: resources/presentation-fixtures/callers/fixture.yaml
 * steps:
 *   selfcheck:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - python3
 *     - '@resource{selfcheck.py}'
 *   signatures:
 *     type: process.exec
 *     timeout_ms: 120000
 *     argv:
 *     - python3
 *     - '@resource{blast.py}'
 *     - signatures
 *     - $root
 *     - $base_ref
 *   callers:
 *     type: process.exec
 *     timeout_ms: 120000
 *     depends_on:
 *     - signatures
 *     argv:
 *     - python3
 *     - '@resource{blast.py}'
 *     - callers
 *     - $root
 *     - $base_ref
 *     - '@signatures{.stdout.text}'
 * ---
 */

const { FlowOutput, loadPresentationContext, stepName } =
  await import("__ROTE_PRESENTATION_SDK__");

const out = new FlowOutput();
const ctx = await loadPresentationContext();

type Finding = {
  file: string;
  line: number;
  symbol: string;
  module: string;
  verdict: string;
  reason: string;
};

// Every step is inspected, not just the one carrying the payload. A step that was
// blocked, skipped, failed or cut at rote's 64 KiB stdout preview must be named:
// a report built from a partial document is not a shorter report, it is a wrong one.
type Degraded = { step: string; state: string; detail: string };
const degraded: Degraded[] = [];

// Takes the handle, not the name, so every stepName("...") stays a literal lint can verify.
function checkStep(name: string, step: ReturnType<typeof ctx.step>) {
  const o = step.outcome as { status: string; output?: Record<string, unknown> };
  if (o.status !== "completed" && o.status !== "restored") {
    degraded.push({
      step: name,
      state: o.status,
      detail: String(o.output?.reason ?? o.output?.message ?? "no detail recorded"),
    });
    return null;
  }
  return (o.output ?? {}) as { body?: Record<string, unknown> };
}

const selfStep = checkStep("selfcheck", ctx.step(stepName("selfcheck")));
const sigStep = checkStep("signatures", ctx.step(stepName("signatures")));
const callStep = checkStep("callers", ctx.step(stepName("callers")));

for (const [name, st] of [["selfcheck", selfStep], ["signatures", sigStep], ["callers", callStep]] as const) {
  if (!st) continue;
  const body = (st.body ?? {}) as { stdout?: { truncated?: boolean; bytes?: number } };
  if (body.stdout?.truncated === true) {
    degraded.push({
      step: name,
      state: "truncated",
      detail: `stdout was cut at rote's 64 KiB preview ceiling (${body.stdout?.bytes ?? "?"} bytes produced)`,
    });
  }
}

if (degraded.length > 0) {
  const rows = degraded.map((d) => `- ${d.step}: ${d.state} — ${d.detail}`).join("\n");
  out.human(
    `# Scan incomplete\n\nThis run did not produce a usable report, so no findings are shown. Treating a partial run as a clean refactor is the exact mistake this play exists to catch.\n\n${rows}`,
  );
  out.summary(`incomplete: ${degraded.map((d) => `${d.step} ${d.state}`).join(", ")}`);
  out.result({ status: "incomplete", degraded, findings: [] });
} else {
  const body = (callStep!.body ?? {}) as { stdout?: { text?: string } };
  const stdout = body.stdout?.text;
  if (stdout === undefined) throw new Error("callers captured no stdout");

  let findings: Finding[] = [];
  let changed: string[] = [];
  let symbols: string[] = [];
  let unreadable: { path: string; reason: string }[] = [];
  let baseRef = "";
  try {
    const parsed = JSON.parse(stdout) as {
      base: string;
      changed_files: string[];
      affected_symbols: string[];
      unreadable: { path: string; reason: string }[];
      findings: Finding[];
    };
    findings = parsed.findings;
    changed = parsed.changed_files;
    symbols = parsed.affected_symbols;
    unreadable = parsed.unreadable ?? [];
    baseRef = parsed.base;
  } catch (cause) {
    throw new Error("callers stdout was not valid JSON", { cause });
  }

  const orphaned = findings.filter((f) => f.verdict === "ORPHANED_CALL_SITE");
  const removed = findings.filter((f) => f.verdict === "REMOVED_SYMBOL_STILL_CALLED");
  const unknown = findings.filter((f) => f.verdict === "INDETERMINATE");

  function row(f: Finding): string {
    return `- ${f.file}:${f.line} \`${f.symbol}\` — ${f.reason}`;
  }

  const sections: string[] = [];
  if (symbols.length === 0) {
    sections.push(
      `## No signature changes\nNothing in the ${changed.length} changed Python file(s) altered a signature or removed a symbol, so there is no blast radius to check.`,
    );
  }
  if (removed.length > 0) {
    sections.push(`## REMOVED_SYMBOL_STILL_CALLED (${removed.length})\n${removed.map(row).join("\n")}`);
  }
  if (orphaned.length > 0) {
    sections.push(`## ORPHANED_CALL_SITE (${orphaned.length})\n${orphaned.map(row).join("\n")}`);
  }
  if (unknown.length > 0) {
    sections.push(
      `## INDETERMINATE (${unknown.length})\nArity could not be established statically. Not a claim that these are correct.\n${unknown.map(row).join("\n")}`,
    );
  }
  if (unreadable.length > 0) {
    const rows = unreadable.map((u) => `- ${u.path} (${u.reason})`).join("\n");
    sections.push(
      `## Incomplete scan (${unreadable.length} path(s) unreadable)\nThese were not read, so a low finding count does not mean a complete refactor.\n${rows}`,
    );
  }
  if (sections.length === 0) {
    sections.push(
      `## No orphaned callers found\nEvery resolvable call site for ${symbols.length} changed symbol(s) still fits its new signature.`,
    );
  }

  // The assertions that prove this analyzer works live on the author's machine,
  // where nobody running the play can see them. This is that same analyzer, fed its
  // own bundled trees at run time. A rule with no positive case could be deleted
  // without the check noticing, so coverage of every verdict is itself a case, and
  // so is discovery: a comparison that sees no changed file reports a clean refactor.
  type SelfCheck = { passed: number; total: number; failures: { case: string; detail: string }[] };
  let selfResult: SelfCheck | null = null;
  if (selfStep) {
    const sb = (selfStep.body ?? {}) as { stdout?: { text?: string } };
    try { selfResult = JSON.parse(sb.stdout?.text ?? '') as SelfCheck; } catch { selfResult = null; }
  }
  const selfFailed = selfResult === null || selfResult.failures.length > 0;
  const selfLine = selfResult === null
    ? 'Self-check: NOT RUN - this analyzer did not verify itself on this machine'
    : selfResult.failures.length === 0
      ? `Self-check: PASSED (${selfResult.passed}/${selfResult.total} bundled analyzer cases)`
      : `Self-check: FAILED (${selfResult.passed}/${selfResult.total}) - THIS ANALYZER IS NOT BEHAVING AS BUILT`;

  if (selfFailed) {
    const failRows = (selfResult?.failures ?? [])
      .map((f) => `  failed case  ${f.case}: ${f.detail}`).join('\n');
    out.human([selfLine,
      '# ANALYZER FAILED ITS OWN SELF-CHECK - THE FINDINGS BELOW CANNOT BE RELIED ON',
      'This is the same analyzer that would have read your repository. It was given its own bundled trees first and did not reproduce them, so nothing it reports about your refactor is trustworthy.',
      failRows].join('\n\n'));
    out.summary(selfLine);
    out.result({ self_check: selfResult, status: 'self-check-failed' });
  } else {
  out.human([selfLine, `# Blast radius vs ${baseRef}: ${findings.length} finding(s)`, ...sections].join("\n\n"));
  out.summary(
    `${findings.length} finding(s): ${orphaned.length} orphaned, ${removed.length} removed-but-called, ${unknown.length} indeterminate, across ${changed.length} changed file(s)`,
  );
  out.result({
    self_check: selfResult,
    // three views of one run. The listing is capped in the
    // human view, so which view is canonical is stated here
    // rather than left for a reader to discover.
    representations: {
      human: "complete: every finding with file, line, symbol and why the call no longer fits",
      json: "canonical superset: the same findings plus the self-check result, the changed file list and every affected symbol",
      summary: "intentionally lossy: counts by verdict and the number of changed files",
    },
    base_ref: baseRef,
    changed_files: changed,
    affected_symbols: symbols,
    orphaned,
    removed,
    indeterminate: unknown,
    unreadable,
  });
  }
}
