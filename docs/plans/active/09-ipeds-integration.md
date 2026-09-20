# Plan 09 — IPEDS Integration

**Status:** ACTIVE

## Objective

Add versioned institution-level costs, characteristics, program production, aid, retention, completion, and graduation evidence.

## Implemented first slice

- explicit official-URL registration for an exact academic-year charges release;
- immutable artifact storage with schema validation before `VALIDATED` state;
- strict `UNITID`, `CHG2AY3`, and `CHG4AY3` archive contract;
- registry-backed scenario provider with hash/size verification;
- exact-release and exact-UNITID resolution with machine-readable lineage;
- unavailable/sentinel values preserved as insufficient data;
- deterministic ZIP fixtures and opt-in official-host smoke test.
- strict reviewed release-catalog contract pairing data and dictionary URLs;
- component-scoped newest-final selection and explicit nonfinal opt-in.
- reviewed `IC2023_AY` data/dictionary URL pair and corrected provisional labeling.

This slice intentionally does not claim that IPEDS charges are net price or program-specific cost.

## Remaining implementation tasks

1. Implement resilient inventory change detection without guessing download paths.
2. Acquire and validate the paired dictionary artifact.
4. Interpret and retain IPEDS imputation/status fields.
5. Add residency and attendance-basis policies, including out-of-state charges.
6. Normalize estimated expenses, aid, enrollment, retention, completion, and program production.
7. Preserve reported basis and population definitions.
8. Map programs using versioned CIP and handle institution identity changes.
9. Generate institution/year analytical Parquet tables.
10. Add scenario completion resolution and release comparisons.
11. Wire validated registry providers into production CLI commands.

## Tests still required

- live exact-release download and dictionary pairing;
- final/provisional selection;
- CIP-version mismatch and UNITID history;
- residency/attendance-basis policy;
- completion cohort definitions;
- cross-release anomaly review.

## Acceptance criteria

- Scenario resolution can retrieve institution costs and completion evidence with exact vintage/status.
- Definitions and populations are disclosed.
- Final releases are preferred by default.
- Provisional releases require explicit opt-in/warnings.
- Missing evidence does not become zero.
