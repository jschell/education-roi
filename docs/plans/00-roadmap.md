# Implementation Roadmap

## Purpose

This is the execution index for Education Path ROI. The governing requirements remain in [../project-plan.md](../project-plan.md).

Plans move between:

- `active/` — currently being researched or implemented;
- `complete/` — acceptance criteria satisfied;
- `queue/` — approved future work.

Only this roadmap remains directly in `docs/plans/`.

## Current sequence

| Plan | Stage | Depends on | Gate | Status |
|---|---|---|---|---|
| [01](active/01-methodology-research.md) | Methodology research | None | Milestone 0 hard gate | **ACTIVE — supplement required** |
| [02](complete/02-data-source-inventory.md) | Source inventory | None | Milestone 0 hard gate | **COMPLETE** |
| [03](queue/03-project-foundation.md) | Project foundation | 01–02 | — | QUEUED |
| [04](queue/04-data-provenance.md) | Provenance system | 02–03 | — | QUEUED |
| [05](queue/05-acs-pums-pipeline.md) | ACS pipeline | 01–04 | — | QUEUED |
| [06](queue/06-financial-engine.md) | Financial engine | 01, 03–05 | — | QUEUED |
| [07](queue/07-zhang-reproduction.md) | Zhang reproduction | 01, 05–06 | Reproduction hard gate | QUEUED |
| [08](queue/08-scenario-engine.md) | Scenario engine | 04, 06–07 | — | QUEUED |
| [09](queue/09-ipeds-integration.md) | IPEDS | 02, 04, 08 | — | QUEUED |
| [10](queue/10-scorecard-integration.md) | College Scorecard | 02, 04, 08–09 | — | QUEUED |
| [11](queue/11-bls-validation.md) | BLS validation | 02, 04–08 | — | QUEUED |
| [12](queue/12-alternative-pathways.md) | Alternative pathways | 08–11 | — | QUEUED |
| [13](queue/13-uncertainty-analysis.md) | Sensitivity/simulation | 06–12 | Deterministic gate | QUEUED |
| [14](queue/14-reporting-maintenance-ui.md) | Reporting, maintenance, UI | 04–13 | UI gate | QUEUED |

## Milestone 0 results

Plan 02 produced:

- [dataset inventory](../datasets.md);
- [validation specification](../validation.md);
- current official acquisition/update strategies.

Plan 01 produced:

- [verified main-paper methodology](../methodology.md);
- [reproduction plan](../reproduction-plan.md);
- [research log](../research-log.md).

The supplied main article resolved Equations 1–6, sample construction, costs, opportunity costs, quantile regression, and selection adjustment.

### Remaining Plan 01 blocker

Obtain the publisher supplemental PDF and transcribe Table A1’s exact mapping of 173 ACS fields into ten major categories. Confirm any supplement details concerning weights, variance, and additional deciles. Until this is resolved, the Milestone 0 methodology gate remains open.

## Hard gates

### Gate A — Research target

Plan 01 must move to `complete/` before substantial paper-labeled analytical implementation. Plan 02 is complete.

### Gate B — Reproduction

Plan 07 must reproduce selected Zhang results within predeclared tolerances—or document an accepted evidence-based discrepancy—before institution-specific conclusions are decision-grade.

### Gate C — Deterministic model

Deterministic calculations and sensitivity tests must be validated before Monte Carlo simulation.

### Gate D — Interface

No significant web-interface work begins until calculation, provenance, scenario, and report contracts are stable.

## Cross-cutting completion rules

Every plan must preserve immutable raw data, deterministic calculations, explicit insufficient-data states, tests, documentation, dataset/model provenance, visible schema/assumption changes, and reviewable commits.

## Next action

Acquire the supplementary PDF. Then complete Plan 01 and activate Plan 03.
