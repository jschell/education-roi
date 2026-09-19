# Implementation Roadmap

## Purpose

This is the execution index for Education Path ROI. The governing requirements remain in [../project-plan.md](../project-plan.md). Each linked plan is small enough to implement and review independently.

## Status vocabulary

- `NOT_STARTED`
- `RESEARCHING`
- `IMPLEMENTING`
- `BLOCKED`
- `REVIEW_REQUIRED`
- `COMPLETE`

A plan is not complete until its acceptance criteria and tests pass and its documentation is updated.

## Plan sequence

| Plan | Stage | Depends on | Gate | Initial status |
|---|---|---|---|---|
| [01](01-methodology-research.md) | Methodology research | None | Hard gate | NOT_STARTED |
| [02](02-data-source-inventory.md) | Source inventory | None | Hard gate | NOT_STARTED |
| [03](03-project-foundation.md) | Project foundation | 01–02 research direction | — | NOT_STARTED |
| [04](04-data-provenance.md) | Provenance system | 02–03 | — | NOT_STARTED |
| [05](05-acs-pums-pipeline.md) | ACS pipeline | 01–04 | — | NOT_STARTED |
| [06](06-financial-engine.md) | Financial engine | 01, 03–05 | — | NOT_STARTED |
| [07](07-zhang-reproduction.md) | Zhang reproduction | 01, 05–06 | Hard gate | NOT_STARTED |
| [08](08-scenario-engine.md) | Scenario engine | 04, 06–07 | — | NOT_STARTED |
| [09](09-ipeds-integration.md) | IPEDS | 02, 04, 08 | — | NOT_STARTED |
| [10](10-scorecard-integration.md) | College Scorecard | 02, 04, 08–09 | — | NOT_STARTED |
| [11](11-bls-validation.md) | BLS validation | 02, 04–08 | — | NOT_STARTED |
| [12](12-alternative-pathways.md) | Alternative pathways | 08–11 | — | NOT_STARTED |
| [13](13-uncertainty-analysis.md) | Sensitivity and simulation | 06–12 | Deterministic gate | NOT_STARTED |
| [14](14-reporting-maintenance-ui.md) | Reporting, maintenance, UI | 04–13 | UI gate | NOT_STARTED |

## Hard gates

### Gate A — Research target

Plans 01 and 02 must establish a reviewable methodology, source inventory, exact candidate variables, unresolved ambiguities, and reproduction tolerances before substantial analytical implementation.

### Gate B — Reproduction

Plan 07 must reproduce selected Zhang results within approved tolerances—or document an accepted explanation for discrepancies—before institution-specific conclusions are described as trustworthy.

### Gate C — Deterministic model

Deterministic calculations and sensitivity tests must be validated before Monte Carlo work begins.

### Gate D — Interface

No significant web-interface work begins until the calculation library, provenance, scenarios, and reporting contracts are stable.

## Cross-cutting completion rules

Every plan must:

1. Preserve immutable raw data.
2. Keep calculations deterministic unless explicitly simulating.
3. Return insufficient-data states rather than invent values.
4. Add tests appropriate to its risk.
5. Update methodology, dataset, assumptions, or validation documentation.
6. Preserve dataset and model version provenance.
7. Avoid silent schema, crosswalk, or assumption changes.
8. Produce reviewable commits.

## Immediate work

Start Plans 01 and 02 together. Their combined deliverables form Milestone 0.
