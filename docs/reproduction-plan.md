# Zhang Reproduction Plan

**Status:** BLOCKED ON FULL-TEXT METHOD VERIFICATION  
**Plan:** 01 — Methodology Research

## Purpose

Create an automated, auditable reproduction of selected Zhang, Liu, and Hu (2024) results. The reproduction must test the published method rather than an interpretation inferred from the abstract.

## Entry requirements

Do not begin paper-labeled reproduction calculations until all are available:

1. Full article methods and equations.
2. Tables/figures selected as targets.
3. Appendices and supplements, if published.
4. Exact ACS years/products.
5. Sample restrictions and major group definitions.
6. Earnings and cost definitions.
7. Selection-adjustment equation.
8. Quantile-regression specification.

If replication code or author-supplied data exist, archive only what licensing permits and record hashes/URLs.

## Verified starting facts

- ACS years span 2009–2021.
- The comparison is ten broad college-major groups versus high-school graduates.
- The paper estimates age-earnings trajectories and IRRs.
- Quantile regression evaluates heterogeneity across the earnings distribution.
- A selection adjustment is applied.

Everything more specific is pending full-text verification.

## Reproduction work packages

### R1 — Article extraction

Create a structured table with:

- equation ID;
- page/section;
- exact variable definitions;
- unit;
- timing;
- transformations;
- source dataset;
- paper assumption;
- code symbol;
- test implication.

Update `docs/methodology.md` and close ambiguities M-01 through M-10 where evidence permits.

### R2 — Data pinning

Identify exact ACS files and dictionaries. Download via Census, register immutable artifacts, calculate SHA-256, and retain retrieval metadata. Pin CPI/cost inputs to exact releases.

### R3 — Sample-flow reconstruction

Produce counts after each restriction:

1. raw persons;
2. age universe;
3. education groups;
4. employment/earnings restrictions;
5. major assignment;
6. missing-data exclusions;
7. any demographic/geographic restrictions.

Retain unweighted and weighted counts.

### R4 — Earnings profiles

Reproduce the paper’s mean/conditional/quantile profiles using its exact functional form and weights. Save model coefficients and generated age profiles.

### R5 — Cost and cash flow

Reproduce tuition/direct cost, foregone earnings, enrollment duration, timing, inflation, counterfactual, and terminal-age conventions exactly.

### R6 — Selection adjustment

Implement the verified paper formula as a separately named transformation. Test the preferred specification and paper sensitivity cases.

### R7 — IRR and published targets

Select targets only after the article is reviewed. Prefer:

- at least one aggregate IRR;
- at least three majors spanning low/middle/high returns;
- more than one earnings quantile;
- at least one selection-adjusted result;
- one sensitivity result.

### R8 — Discrepancy analysis

Attribute differences to:

- vintage/revision;
- sample construction;
- field mapping;
- weights;
- income adjustment/CPI;
- regression implementation;
- cost timing;
- root-finding;
- unavailable details.

Do not alter undocumented settings simply to obtain a match.

## Reproduction record schema

```yaml
target_id:
paper_reference:
published_value:
reproduced_value:
absolute_difference:
relative_difference:
tolerance:
status: PASS|FAIL|REVIEW_REQUIRED
configuration_hash:
dataset_manifests:
method_version:
ambiguities:
notes:
```

## Tolerance policy

Tolerances must be declared before examining reproduced target values.

Proposed initial bands, subject to scale:

- displayed percentage: ±0.10 percentage point when identical inputs/method are available;
- regression-derived profile value: ±0.5% relative or documented numerical tolerance;
- sample counts: exact if the same public-use files and rules are available;
- published rounded values: allow rounding interval.

If source revisions or undisclosed details prevent these tolerances, mark `REVIEW_REQUIRED`; do not broaden tolerances retroactively without justification and review.

## Automated tests

- fixture tests for every sample restriction;
- weighted-count tests;
- quantile-regression synthetic tests;
- profile-generation regression tests;
- cost and foregone-earnings tests;
- selection-adjustment tests;
- IRR edge cases;
- published-target comparisons;
- deterministic clean-run test;
- manifest/provenance completeness test.

## Exit decision

Plan 01 and the reproduction gate pass only when:

- paper methods are fully reviewed;
- critical ambiguities are closed or bounded;
- targets/tolerances are predeclared;
- selected results pass or discrepancies receive documented reviewer acceptance.

## Current blocker

The available indexed pages did not provide the full methods/supplements, and ResearchGate denied this automated browser access. Obtain the paper through a lawful accessible copy or user-provided PDF. Until then, Plan 01 remains `ACTIVE/BLOCKED`.
