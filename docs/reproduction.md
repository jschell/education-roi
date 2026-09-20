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

Current aggregate and quantile comparisons remain provisional fixtures until authoritative ACS
inputs, exact coefficients, CPI observations, and restricted cost cells are registered. Paper-level
major reproduction remains blocked until supplemental Table A1 is verified.
