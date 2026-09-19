# Plan 10 — College Scorecard Integration

## Objective

Add institution- and field-level earnings, net price, debt, repayment, completion, and institutional characteristics as scenario inputs and cross-source evidence.

## Prerequisites

- Verified Scorecard documentation and acquisition
- Provenance and scenario engines
- IPEDS institution identity handling
- ACS earnings outputs

## Methodological constraints

Scorecard and ACS populations are not interchangeable. Preserve:

- cohort and aid-recipient definitions;
- measurement horizon;
- institution/field coverage;
- aggregation level;
- suppression rules;
- sample sizes where supplied;
- dollar year;
- credential and CIP version.

## Implementation tasks

1. Implement version discovery and downloads/API snapshotting.
2. Register raw snapshots with query/request metadata where applicable.
3. Validate field dictionaries and release identifiers.
4. Normalize institution, credential, field, earnings, debt, repayment, completion, and net-price fields.
5. Preserve suppression and privacy states.
6. Map institution identity and CIP versions.
7. Create institution × field analytical tables.
8. Implement scenario resolution policies for net price, debt, and outcomes.
9. Compare Scorecard evidence with ACS without automatically averaging.
10. Produce a difference/explanation report.
11. Flag small, suppressed, stale, or incompatible cohorts.
12. Document coverage gaps.

## Tests

- API/download fixture equivalence;
- suppression handling;
- cohort/horizon alignment;
- dollar-year conversion;
- UNITID and CIP mapping;
- missing sample sizes;
- ACS comparison logic;
- stale-release selection;
- field-definition changes.

## Acceptance criteria

- Exact Scorecard vintage and cohort definitions accompany every value.
- Suppressed/missing data remain explicit.
- Cross-source differences are surfaced with likely explanations.
- Scenario use of Scorecard data follows visible, configurable policies.
