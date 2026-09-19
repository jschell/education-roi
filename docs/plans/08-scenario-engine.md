# Plan 08 — Scenario and Comparison Engine

## Objective

Allow arbitrary education/workforce pathways to be defined in validated YAML and compared without changing calculation code.

## Prerequisites

- Stable deterministic financial engine
- Reproduction gate completed
- Provenance contracts
- Initial dataset interfaces

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
