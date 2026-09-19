# Plan 06 — Financial and Cash-Flow Engine

## Objective

Implement deterministic, well-tested cash-flow calculations independent of specific data-source adapters and user interfaces.

## Prerequisites

- Verified equations from Plan 01
- Project foundation
- CPI and earnings input contracts
- Provenance conventions

## Domain model

Represent:

- annual timeline and age;
- education state;
- earnings;
- direct education costs;
- incremental living costs;
- aid and contributions;
- borrowing and financing costs;
- counterfactual cash flows;
- completion outcome;
- graduate-school branch;
- real/nominal dollar basis.

## Implementation tasks

1. Define typed input/output models.
2. Implement CPI conversion with explicit source and target years.
3. Implement education-cost schedules.
4. Implement foregone earnings using counterfactual cash flows.
5. Implement configurable selection adjustment.
6. Implement financing separately from education cost.
7. Implement federal/private loan amortization and origination fees.
8. Construct annual scenario and incremental cash-flow series.
9. Implement NPV using configurable real discount rates.
10. Implement IRR with documented multiple-root/no-root behavior.
11. Implement lifetime earnings and lifetime net value.
12. Implement break-even age and never-breaks-even state.
13. Support conditional-graduate and enrollment-return inputs.
14. Preserve computational provenance and assumption values.

## Numerical behavior

- Define timing conventions: beginning/end of year.
- Define rounding only at presentation boundaries.
- Detect invalid or non-unique IRR cases.
- Avoid silently coercing absent earnings or costs to zero.
- Return structured insufficient-data or undefined-metric states.
- Keep real and nominal values from being combined.

## Tests

- CPI identities and known conversions;
- NPV against independently calculated examples;
- IRR against known cash flows;
- multiple/no IRR cases;
- debt amortization;
- zero-debt scenario;
- foregone earnings;
- selection adjustments;
- break-even edge cases;
- late graduation;
- counterfactual scenario comparison;
- real/nominal mismatch rejection.

## Acceptance criteria

- Pure functions produce deterministic results.
- Metrics agree with independent reference calculations.
- Undefined financial metrics are represented explicitly.
- Financing costs remain distinct from education costs.
- Inputs and outputs contain sufficient provenance for reproduction.
