# Plan 12 — Alternative Education and Workforce Pathways

## Objective

Extend the scenario model beyond direct four-year enrollment while preserving comparable annual cash flows and evidence-quality disclosures.

## Initial pathways

- high-school workforce entry;
- some college;
- associate degree;
- community college → transfer;
- registered apprenticeship;
- technical/trade education;
- optional or mandatory graduate school.

Military and certification pathways remain later extensions unless evidence is sufficient.

## Prerequisites

- Scenario engine
- Institution data
- Earnings and financial engine
- Provenance and evidence-quality model

## Implementation tasks

1. Generalize scenarios into staged pathways.
2. Represent transitions, durations, credentials, and conditional branches.
3. Support earnings during training.
4. Support transfer credits, transfer loss, and destination admission/completion assumptions.
5. Support apprenticeship wages, step progression, fees, and completion.
6. Support graduate-school costs, duration, probability, and post-graduate earnings.
7. Define workforce-entry evidence and employment assumptions.
8. Implement pathway-specific counterfactuals.
9. Add completion/exit outcomes for each stage.
10. Surface evidence gaps and avoid synthetic precision.
11. Create example scenarios and comparison fixtures.
12. Document nonfinancial factors as out of scope for financial metrics, while allowing narrative disclosure.

## Data-quality rules

- Do not infer missing apprenticeship outcomes from unrelated occupations without disclosure.
- Do not assume all community-college students transfer.
- Do not assume transfer credits apply fully.
- Do not interpret bachelor’s-only earnings as complete outcomes for graduate-school-intensive fields.
- Do not invent certification wage premiums.

## Tests

- staged cash-flow timing;
- earn-while-learning;
- failed/late transfer;
- partial credit transfer;
- pathway exit;
- graduate-school branch;
- alternative scenario counterfactual;
- insufficient evidence propagation.

## Acceptance criteria

- Each pathway resolves to transparent annual states and cash flows.
- Transition and completion assumptions are visible.
- Earn-while-learning pathways are modeled without forcing college-only constructs.
- Weak evidence produces explicit limitations or insufficient-data results.
