# Plan 09 — IPEDS Integration

**Status:** QUEUED

## Objective

Add versioned institution-level costs, characteristics, program production, aid, retention, completion, and graduation evidence.

## Prerequisites

- Verified IPEDS source inventory
- Provenance system
- Scenario engine
- Stable institution/program identifiers

## Key decisions

- survey components and years required;
- academic-year alignment;
- preliminary/provisional/final release policy;
- tuition residency and attendance-basis treatment;
- living-cost and off-campus/on-campus distinctions;
- cohort/completion definitions;
- institution changes, closures, and UNITID history;
- CIP version alignment.

## Implementation tasks

1. Implement IPEDS release discovery and artifact registration.
2. Ingest selected components and dictionaries.
3. Validate UNITID, year, component, and publication status.
4. Normalize tuition, fees, estimated expenses, aid, enrollment, retention, completion, and program-production fields.
5. Preserve reported basis and population definitions.
6. Map programs using versioned CIP.
7. Handle institution identity changes explicitly.
8. Generate institution/year analytical Parquet tables.
9. Add source-quality and missing/suppressed states.
10. Resolve scenario cost/completion inputs from explicit policies.
11. Compare releases and flag unusual changes.
12. Document where IPEDS cannot support requested specificity.

## Tests

- component schema fixtures;
- final/provisional selection;
- UNITID joins;
- CIP-version mismatch;
- in-state/out-of-state tuition;
- academic-year alignment;
- missing and suppressed values;
- institution identity changes;
- release comparison anomalies.

## Acceptance criteria

- Scenario resolution can retrieve institution costs and completion evidence with exact vintage/status.
- Definitions and populations are disclosed.
- Final releases are preferred by default.
- Provisional releases require explicit opt-in/warnings.
- Missing evidence does not become zero.
