# Plan 07 — Zhang Reproduction

**Status:** ACTIVE — provisional pending supplement

## Objective

Reproduce selected aggregate and major-level results from Zhang, Liu & Hu (2024) before trusting institution-specific extensions.

## Hard-gate rule

If results materially miss predeclared tolerances, stop expansion and investigate. Do not tune undocumented parameters merely to match published values.

## Prerequisites

- Plan 01 approved methodology and target table
- Plan 05 validated ACS pipeline
- Plan 06 validated financial engine
- Exact available source vintages and CPI series registered

## Implementation tasks

1. Encode the published-method configuration separately from project-default extensions.
2. Implement the exact sample restrictions supported by the evidence.
3. Produce a sample-flow table after every restriction.
4. Reconstruct age-earnings profiles.
5. Reproduce direct-cost and foregone-earnings construction.
6. Apply the specified selection adjustment.
7. Reproduce quantile-regression outputs.
8. Calculate target IRRs and related intermediate values.
9. Compare with published tables using predeclared tolerances.
10. Run alternative interpretations for unresolved ambiguities.
11. Attribute discrepancies to data vintage, sample, variables, weighting, inflation, numerical implementation, or unavailable details.
12. Generate a machine-readable and human-readable reproduction report.

## Reproduction record

For each target retain:

- paper table/figure reference;
- published value;
- reproduced value;
- absolute and relative difference;
- tolerance;
- pass/fail/review status;
- configuration hash;
- dataset hashes;
- ambiguity notes.

## Tests

- sample-flow regression;
- fixed-profile regression;
- published target comparisons;
- configuration immutability;
- deterministic rerun;
- sensitivity to documented ambiguous interpretations;
- clean-environment reproduction.

## Deliverables

- `docs/reproduction.md`
- reproducible configuration files
- automated reproduction test suite
- intermediate sample/profile artifacts
- comparison report
- discrepancy log

## Current implementation record

- Aggregate quadratic earnings profiles and financial-engine integration are implemented with
  provisional fixtures.
- Decile definitions, rank-invariance labeling, quantile profile and solver contracts, independent
  fixed-fixture validation, median/nonmedian IRRs, and deterministic JSON/Markdown reporting are
  implemented.
- Immutable deterministic run bundles now split sample-flow, profile, validation, cash-flow, and
  comparison artifacts; a SHA-256 manifest and CLI verifier detect tampering and metadata drift.
- A typed end-to-end runner now connects ACS sample flow, quantile fitting, independent fixture
  validation, profile-linked cash flows, target comparisons, reports, and immutable bundles in one
  deterministic execution.
- An explicitly synthetic installed-CLI smoke run and subprocess integration test now cover the
  clean-environment reproduction path without weakening the paper-data evidence gate.
- Actual paper-level quantile and major estimates remain provisional pending authoritative ACS
  inputs, exact coefficients, public cost-substitute implementation, and supplemental Table A1.
- Per [Decision 0001](../../decisions/0001-proceed-without-restricted-npsas.md), restricted NPSAS
  microdata will not be pursued. Public substitutes require provenance, fallback disclosure, and
  sensitivity bounds; they can support a methodologically aligned reproduction but not an
  exact-input replication.
- Public cost contracts, deterministic fallback selection, explicit insufficient-data handling,
  low/base/high NPV and IRR sensitivity, report provenance, and immutable bundle output are
  implemented with fixed fixtures. Live source adapters remain in Plans 09 and 10.
- The provisional runner now selects public cost inputs and emits low/base/high target comparisons,
  including the IRR and NPV change attributable to each cost case. An unavailable fallback remains
  an explicit `INSUFFICIENT_DATA` analysis and `REVIEW` comparison rather than a zero-cost result.

## Acceptance criteria

One of the following is approved:

1. Selected results reproduce within tolerance; or
2. Remaining differences have strong documented explanations, sensitivity bounds, and reviewer acceptance.

No institution-level output may be labeled decision-grade before this gate passes.
