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
- deterministic cross-release charge comparison with configurable anomaly thresholds, availability
  changes, raw-status changes, and unresolved UNITID additions/removals routed to manual review.
- production CLI commands for exact-release charge-table construction and scheduled cross-release
  review, including explicit nonfinal opt-in and machine-readable exit states.
- immutable directional CIP crosswalk contracts with official-source hashes, explicit many-to-many
  selection, confidence, and no silent cross-version or reverse mapping.
- directional, source-hashed UNITID history contracts for continuation, ID changes, mergers, splits,
  and explicit closures, with ambiguity and all non-continuation events routed to review.
- deterministic cross-release UNITID pairing that refuses automatic split/merge aggregation and
  emits explicit findings for closures, additions, missing targets, and missing history.
- history-aware charge comparison that follows unique UNITID changes while preserving both IDs and
  refuses numeric comparison for closures, splits, collisions, or unresolved history.
- optional directional UNITID history input on the production charge-comparison CLI, with explicit
  invalid-input states and machine-readable history provenance.
- optional verification of the history source artifact against its declared SHA-256, with explicit
  verified/unverified states; authoritative mapping rows remain a separate review task.
- reviewed final GR2023 data/dictionary pair with explicit `gr2023_RV.csv` selection and the
  four-year bachelor's-seeking adjusted cohort versus bachelor's-award row mapping.
- paired immutable final GR2023 registration with final-member cohort-key validation and a
  production `ipeds register-gr2023` command; other cohorts remain unvalidated.
- registry-backed `ipeds resolve-gr2023` command with exact validated data/dictionary artifacts,
  population labeling, and explicit insufficient/invalid states; no probability inference.
- immutable final GR2023 bachelor's cohort Parquet table with input-paired lineage, original
  count/status cells, explicit unavailable reasons, and `ipeds build-gr2023` CLI; no estimates
  are invented for absent cohort rows.
- cross-release graduation cohort comparison with population compatibility, table hashes,
  source IDs, configurable rate/count review thresholds, and identity-aware coverage findings;
  newer GR releases still require authoritative dictionary review before production use.
- reviewed final GR2022 source URL pair and exact revised member, dictionary cohort semantics,
  and a documented compatibility gate for padded legacy CSV codes and older workbook layout;
  GR2022's release-specific registration and table transformation now pass live source validation.
- official GR2022-to-GR2023 cohort table comparison in an isolated run with exact final archives;
  cross-cohort differences and unresolved UNITIDs require manual review before interpretation.

This slice intentionally does not claim that IPEDS charges are net price or program-specific cost.

## Remaining implementation tasks

1. Extend official workbook validation beyond the final four-year bachelor's mapping.
2. Interpret documented IPEDS imputation/status fields when authoritative definitions are available.
3. Normalize estimated expenses, aid, enrollment, retention, completion, and program production.
4. Preserve reported basis and population definitions.
5. Register authoritative CIP mapping and UNITID history rows, then connect CIP mappings and
   institution history to program production.
6. Extend institution/year analytical Parquet tables beyond academic-year charges.
7. Add scenario completion resolution and extend release comparisons beyond charges.

## Tests still required

- live exact-release download and dictionary pairing;
- final/provisional selection;
- residency/attendance-basis policy;
- completion cohort definitions;

## Acceptance criteria

- Scenario resolution can retrieve institution costs and completion evidence with exact vintage/status.
- Definitions and populations are disclosed.
- Final releases are preferred by default.
- Provisional releases require explicit opt-in/warnings.
- Missing evidence does not become zero.
