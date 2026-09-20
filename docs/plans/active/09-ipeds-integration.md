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

This slice intentionally does not claim that IPEDS charges are net price or program-specific cost.

## Remaining implementation tasks

1. Verify and implement authoritative release-page discovery and dictionary acquisition.
2. Add explicit final/provisional selection policy and warnings.
3. Interpret and retain IPEDS imputation/status fields.
4. Add residency and attendance-basis policies, including out-of-state charges.
5. Normalize estimated expenses, aid, enrollment, retention, completion, and program production.
6. Preserve reported basis and population definitions.
7. Map programs using versioned CIP and handle institution identity changes.
8. Generate institution/year analytical Parquet tables.
9. Add scenario completion resolution and release comparisons.
10. Wire validated registry providers into production CLI commands.

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
