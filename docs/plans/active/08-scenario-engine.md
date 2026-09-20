# Plan 08 — Scenario and Comparison Engine

**Status:** ACTIVE — resolved configuration implementation

## Objective

Allow arbitrary education/workforce pathways to be defined in validated YAML and compared without changing calculation code.

## Prerequisite exception

The Plan 07 software infrastructure is complete, but authoritative evidence remains blocked. Plan 08
contract engineering may proceed because it does not certify or publish institution-level results.
All scenario outputs remain provisional and non-decision-grade until the reproduction gate is
accepted.

## Schema areas

- scenario identity and description;
- institution and program;
- credential and CIP;
- duration and completion branches;
- costs and living-cost treatment;
- aid, family/student contribution, and financing;
- earnings source and quantiles;
- counterfactual scenario reference;
- graduate-school branches;
- assumptions and horizon;
- data-vintage pins or selection policy.

## Implementation tasks

1. Define versioned Pydantic models and JSON Schema.
2. Define defaults explicitly and keep them minimal.
3. Validate cross-field constraints.
4. Resolve scenario references and detect cycles.
5. Separate scenario definition from resolved dataset values.
6. Produce a fully resolved run configuration.
7. Add analyze and compare CLI commands.
8. Run conditional-graduate and enrollment-return modes.
9. Compare scenario cash flows incrementally.
10. Produce JSON and CSV outputs with provenance.
11. Add structured insufficient-data behavior.
12. Preserve input scenario files with each run.

## Current implementation record

- YAML schema version `1.0` is represented by strict, frozen Pydantic contracts.
- Inputs distinguish provided, data-resolved, and insufficient states; a missing value never becomes
  zero.
- Education/workforce kind constraints, completion probabilities, CIP/SOC versions, money basis,
  horizons, quantiles, graduate-school references, and dataset pins are validated.
- Reference graphs reject missing targets, cycles, duplicate IDs, and incompatible money bases.
- Scenario and graph hashes are canonical and independent of caller file ordering.
- `edu-roi scenario validate` validates a connected file set; `edu-roi scenario schema` emits the
  formal JSON Schema.
- Example workforce and bachelor's scenarios and unit/integration tests are included.
- Numeric scenario inputs resolve through an explicit provider into immutable resolved values.
- Resolution enforces exact scenario dataset pins and rejects source or vintage substitution.
- Every data-resolved value records artifact and transformation identifiers; provider misses and
  declared gaps remain `INSUFFICIENT_DATA` rather than becoming zero.
- Resolved scenarios and graphs are counterfactual-first, canonical, and deterministically hashed.
- `edu-roi scenario resolve` supports an explicitly fixture-backed provider for integration tests;
  live IPEDS and Scorecard providers remain a later slice.
- `edu-roi scenario analyze` now builds annual option and counterfactual cash flows from complete
  synthetic fixtures and produces deterministic NPV, IRR, lifetime-value, and break-even results.
- Conditional-graduate and enrollment-return perspectives remain separate. Enrollment analysis
  requires outcome-specific earnings and timing for every nonzero completion state.
- Incomplete numeric, earnings, timing, or outcome evidence produces a structured
  `INSUFFICIENT_DATA` result; partial metrics are not published.
- `edu-roi compare` validates common counterfactual, money basis, horizon, and earnings quantile,
  then emits side-by-side and pairwise results for two or more options.
- Comparison runs preserve source scenarios, resolved inputs, earnings, assumptions, dataset
  references, cash flows, results, and validation findings in a new immutable directory.
- JSON and CSV outputs are covered by a SHA-256 manifest; deterministic reruns and tamper detection
  are tested through `edu-roi scenario verify-bundle`.

## Validation rules

Reject or flag:

- incompatible credential/duration;
- missing counterfactual;
- cyclic references;
- incompatible real/nominal bases;
- unavailable dataset version;
- invalid quantiles;
- silently inferred debt/aid;
- classification mismatch;
- unsupported graduate-school pathway.

## Tests

- schema examples and failures;
- backward schema-version handling;
- reference resolution;
- cycle detection;
- direct workforce counterfactual;
- education-vs-education comparison;
- missing-data propagation;
- stable resolved configuration;
- reproducible output directory.

## Acceptance criteria

- New scenarios require configuration, not model-code changes.
- Every default and resolved value is visible.
- Scenario comparisons use incremental cash flows correctly.
- Inputs, outputs, datasets, assumptions, and validation findings are saved together.
