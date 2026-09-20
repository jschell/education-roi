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
- paired validation and separate immutable data/dictionary manifests;
- required-variable dictionary validation with retained definition rows.
- raw `XCHG2AY3`/`XCHG4AY3` source-status propagation without undocumented interpretation.
- explicit in-district/in-state/out-of-state tuition basis with no residency fallback.
- deterministic inventory snapshot comparison with discovered/changed/missing review states and no
  guessed URLs or automatic promotion.
- deterministic `ipeds compare-inventory` CLI output with optional CI failure on review-required
  changes.
- production `scenario resolve-ipeds` CLI resolution from validated immutable registry artifacts.
- explicit full-time/part-time attendance basis with full-time-only annual charge resolution and no
  part-time conversion or fallback.
- immutable institution/release charge Parquet tables retaining reporting basis, residency cells,
  raw status cells, publication status, raw artifact lineage, and transformation version.

This slice intentionally does not claim that IPEDS charges are net price or program-specific cost.

## Remaining implementation tasks

1. Verify dictionary parsing against official workbook bytes in an enabled live environment.
2. Interpret documented IPEDS imputation/status fields when authoritative definitions are available.
3. Normalize estimated expenses, aid, enrollment, retention, completion, and program production.
4. Preserve reported basis and population definitions.
5. Map programs using versioned CIP and handle institution identity changes.
6. Extend institution/year analytical Parquet tables beyond academic-year charges.
7. Add scenario completion resolution and release comparisons.

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
