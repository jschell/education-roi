# Zhang Reproduction

Plan 07 is active. The initial implementation freezes the published-method configuration, emits an
auditable sample-flow table, and compares reproduced values with predeclared tolerances.

Aggregate targets may be evaluated when their inputs are available. Major-level targets are
mechanically `BLOCKED` while the field-of-degree crosswalk is provisional; matching a published
number cannot override that evidence gate. Missing calculated values are `REVIEW`, and completed
comparisons are `PASS` or `FAIL` without tuning assumptions after inspection.

Each comparison retains its paper reference, published and reproduced values, absolute and relative
differences, tolerance, configuration hash, dataset hashes, and ambiguity notes. The preferred
configuration pins ACS 2009–2021, ages 18–65, 2021 dollars, college ages 18–21, $1,000 books, $3,268
student earnings, 50% nontuition attribution, and 25% selection adjustment.

Age-earnings profiles now evaluate the documented quadratic log-earnings equation for ages 18–65
while preserving standardized covariates, the common-versus-group-specific slope interpretation,
coefficient source, and a deterministic coefficient hash. Aggregate integration applies the
selection adjustment to annual earnings, builds four years of college costs and student earnings,
and sends complete annual cash flows through the financial engine.

## Quantile-profile and reporting infrastructure

The supported distributional positions are the nine earnings deciles, P10 through P90. Every decile
definition carries the same visible warning: it is an observed position in an earnings distribution,
not an individual probability, and comparing the same position across education states invokes the
paper's rank-invariance assumption.

Quantile-profile inputs retain their coefficient source and hash. Fit results retain solver
algorithm, implementation and version, convergence state, iterations, tolerance, objective value,
and message. A failed solver cannot produce a profile. Converged profiles preserve unrounded annual
earnings and can be checked at every age against fixed outputs from a named independent
implementation.

Median and nonmedian incremental cash-flow series use the same deterministic IRR engine. Each result
retains the complete real/nominal basis, annual cash flows, profile hashes, cash-flow hash, bounded
IRR search metadata, roots, and the decile interpretation label. These fixture calculations validate
the infrastructure only; they are not estimates of the paper's results.

The reproduction report has canonical JSON and deterministic Markdown forms. JSON retains sample
flow, profile and convergence records, independent-profile checks, full cash flows, IRRs, and target
comparisons. Markdown highlights evidence blockers, distributional IRRs, discrepancies, and
methodological ambiguities. Provisional report construction requires at least one named blocker and
cannot silently become certified.

## Reproduction bundles

Each report can be written once to an immutable run directory. The bundle contains `report.json`,
`report.md`, and separate canonical JSON artifacts for sample flow, profiles, profile validations,
cash flows, and comparisons. `manifest.json` records the run ID, report schema, certification
status, configuration hash, dataset hashes, and SHA-256 plus byte size for every report artifact.

Writing is staged in a temporary sibling directory and refuses to replace an existing run. Identical
inputs and run IDs produce byte-identical bundles. Verification rejects missing or extra files,
symbolic links, noncanonical JSON, digest or size changes, report/manifest metadata drift, and split
artifacts that differ from the canonical report. Run verification with:

```console
edu-roi reproduce verify-bundle results/run-001
```

The command emits a machine-readable `VALID` result or exits nonzero with `INVALID`. Bundle
integrity does not elevate the evidence status: fixture-backed runs remain visibly `PROVISIONAL`.

## Deterministic run orchestration

`run_provisional_reproduction` joins the implemented stages behind one typed request. It applies the
documented ACS sample flow, builds quantile profiles, validates converged profiles against named
reference fixtures, checks that every cash flow references profiles produced by the same run,
calculates distributional IRRs, evaluates predeclared targets, creates the provisional report, and
writes its immutable bundle.

Profile cases and targets are sorted by stable identities before reporting, so caller order does not
change output bytes. Failed solvers remain visible without profiles or invented reference checks.
Cash flows with missing or failed profile dependencies stop the run before a result directory is
published. This orchestration is currently validated with synthetic fixtures; it does not bypass the
authoritative-input and Table A1 evidence gates.

Current aggregate and quantile comparisons remain provisional fixtures until authoritative ACS
inputs, exact coefficients, CPI observations, and restricted cost cells are registered. Paper-level
major reproduction remains blocked until supplemental Table A1 is verified.
