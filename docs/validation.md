# Data and Model Validation Specification

**Status:** Milestone 0 specification  
**Last reviewed:** 2026-09-19

## Principle

Validation is layered. A successful download is not a validated analytical dataset, and a valid schema is not evidence that estimates are statistically reliable.

## 1. Transport validation

For every source artifact:

- require HTTPS;
- allow only configured authoritative government domains and documented redirect hosts;
- record original and final URL;
- require successful complete transfer;
- record response metadata where available;
- calculate SHA-256;
- record byte size;
- test ZIP/GZIP/archive integrity;
- reject HTML/error pages masquerading as data;
- stage downloads before immutable registration.

A publisher-replaced file under the same apparent version must be retained as a distinct retrieval and flagged.

## 2. Manifest validation

Required fields:

```yaml
source:
dataset:
publisher:
release:
vintage:
retrieved_at:
source_url:
final_url:
sha256:
file_size:
publication_status:
schema_version:
license_or_notice:
```

Processed artifacts additionally require transformation version, code commit, parameters, raw input hashes, row count, schema fingerprint, and output hash.

## 3. Schema validation

Check:

- expected files and tables;
- required columns;
- names and types;
- valid code ranges;
- sentinel/missing-value codes;
- unique keys;
- classification versions;
- nominal/reference year;
- suppression fields;
- required dictionaries/code lists.

Schema drift enters `REVIEW_REQUIRED`; do not silently coerce renamed or redefined fields.

## 4. Source-specific checks

### ACS

- people-file identity and vintage;
- presence of `AGEP`, `SCHL`, `PWGTP`, earnings target, and field-of-degree variables when applicable;
- person-weight positivity/range;
- replicate-weight availability when required;
- valid age, attainment, field, state, and PUMA codes;
- income adjustment fields for pooled years;
- unweighted and weighted sample counts after every restriction.

### IPEDS

- UNITID/year/component uniqueness as defined by file;
- collection year and publication status;
- valid sector/control/level codes;
- tuition/fee and completion definitions;
- CIP edition alignment;
- provisional/final selection policy.

### College Scorecard

- release snapshot and dictionary alignment;
- institution vs. field-file distinction;
- OPEID/UNITID mapping;
- credential/CIP/cohort/horizon fields;
- suppression/null handling;
- prevent suppressed/unavailable values from becoming zero;
- dollar/reference year.

### BLS

- release/reference period;
- SOC version;
- area and ownership codes;
- suppression markers;
- observed OEWS vs. projected Employment Projections separation;
- CPI series/period/seasonal-adjustment status.

### FSA

- effective date;
- loan/program/borrower type;
- statutory maximums;
- origination-fee and interest-rate basis;
- repayment-rule version.

## 5. Statistical validation

For each release and major transformation, retain:

- raw and retained record counts;
- unweighted and weighted populations;
- missing/suppressed rates;
- age distribution;
- attainment/major distribution;
- earnings distribution;
- geography distribution;
- quantile monotonicity;
- impossible or extreme values;
- sample support per published estimate.

Compare against the previous approved release. Thresholds begin as review triggers, not automatic rejection.

Proposed initial triggers:

- total row count change >10%;
- weighted population change >5%;
- null/suppression-rate change >5 percentage points;
- median earnings change >15% after consistent dollar conversion;
- major/geography share change >5 percentage points;
- schema fingerprint change;
- new/deleted classification codes.

Source-specific historical volatility may justify different thresholds, documented before promotion.

## 6. Sample reliability and fallback

Every estimate retains:

- unweighted N;
- weighted N;
- standard error/variance method where available;
- confidence interval where supported;
- source/vintage;
- geography;
- age band;
- major aggregation;
- fallback path.

The initial minimum-N and precision rules remain unresolved until Plan 01 determines the estimator and variance method. Never publish a highly specific estimate merely because a point estimate can be calculated.

Fallback must be deterministic and disclosed, e.g.:

`Seattle × CS × age 32 → Seattle × CS × age 30–34 → Washington × CS × age 30–34`

## 7. Cross-source validation

Differences are findings, not values to average away.

Compare:

- ACS major earnings;
- Scorecard institution/field/cohort earnings;
- OEWS occupation wages;
- IPEDS and Scorecard costs/completion where definitions overlap.

Store likely explanations:

- population/universe;
- age;
- geography;
- cohort timing;
- graduate education;
- occupation vs. degree;
- dollar year;
- suppression/sample size;
- selection;
- differing outcome horizon.

## 8. Model validation

### Financial engine

Test CPI conversion, annual timing, education cost, foregone earnings, financing, NPV, IRR, lifetime values, break-even, and undefined/multiple IRR behavior against independent calculations.

### Earnings model

Test weights, quantiles, model specification, interpolation, extrapolation limits, and uncertainty on synthetic and fixed fixtures.

### Scenario engine

Test schema, defaults, reference resolution, cycle detection, incremental comparisons, insufficient-data propagation, and reproducible resolved configurations.

### Reproduction

Published targets use predeclared tolerances. Failures halt expansion or require explicit reviewed discrepancy acceptance.

## 9. Release state machine

```text
DISCOVERED
  → DOWNLOADED
  → VALIDATED
  → APPROVED
       or REVIEW_REQUIRED
            → APPROVED
            → REJECTED
```

Only `APPROVED` artifacts may become default inputs. `--latest` may select newer validated/provisional inputs only with explicit warnings and complete provenance.

## 10. Validation report

Each run emits `validation.json` containing:

- check ID/category;
- status;
- observed value;
- expected rule/range;
- severity;
- artifact IDs/hashes;
- comparison release;
- explanation;
- reviewer decision;
- timestamp and code version.

A human-readable report summarizes blockers and unusual changes without hiding passed checks.
