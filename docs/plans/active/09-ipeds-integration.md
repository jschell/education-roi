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
- live official `IC2023_AY` pair registration and table build after restricting workbook
  definition validation to the `Varlist` worksheet; repeated names on other sheets are valid.
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
- comparison CLI verification of both immutable processing manifests and table hashes by default;
  fixture-only bypass is visibly marked as unverified.
- exact-UNITID lookup of processed GR cohort evidence with verified manifest lineage and
  explicit insufficient-data states; scenario completion probabilities remain unresolved.
- exact-UNITID lookup of five verified IC2023 living-expense estimates by arrangement with
  source status and provisional opt-in; incremental living cost remains unresolved.
- immutable, source-paired IC2023 expense table with the five distinct living-basis cells,
  source-status/raw cells, population and release metadata, and explicit provisional opt-in.
- pinned final revised EF2023D data/dictionary pair, validated registration, and exact-UNITID
  first-year retention lookup preserving entry cohort, source rate and status cells; no conversion
  into a graduation or scenario probability.
- immutable, source-paired final revised EF2023D analytical retention table with separate
  reported percentage and next-fall count, original status cells, and cohort year metadata.
- verified processed retention-table lookup with full-table hash and manifest checks,
  exact-UNITID evidence, and explicit unavailable states; official 5,646-row build verified.
- retention dictionary validation requires each reviewed variable exactly once; malformed CSV
  rows with missing or extra cells fail with an explicit source-validation error.
- reviewed final revised EF2022D source pair and cohort definitions are cataloged for a
  prior-year retention comparison; release-specific paired registration, immutable table,
  source and verified table lookups now preserve its distinct 2021/2022 cohort years.
- verified cross-release retention comparison of the distinct EF2022D and EF2023D cohorts
  with reported-percent and count thresholds, source statuses, paired provenance, and
  review-required UNITID identity/coverage findings; official pair tested in isolation.
- reviewed final revised C2023_A program awards source pair, exact key and CIP 2020
  definition cataloged; paired immutable registration and verified exact-key award
  lookup preserve status and distinguish zero from unavailable counts.

This slice intentionally does not claim that IPEDS charges are net price or program-specific cost.

## Remaining implementation tasks

1. Extend official workbook validation beyond the final four-year bachelor's mapping.
2. Interpret documented IPEDS imputation/status fields when authoritative definitions are available.
3. Add aid, enrollment, other completion cohorts, and program production. Expense
   estimates have a pinned 2023–24 table but no cross-release series or scenario integration.
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
