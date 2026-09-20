# Scenario definitions

Scenario files use YAML schema version `1.0`. The schema describes unresolved intent rather than
pretending every dataset value is already available. Every monetary or probability input is marked
`PROVIDED`, `RESOLVE_FROM_DATA`, or `INSUFFICIENT_DATA`. A provided zero must be written explicitly;
missing values never become zero.

Validate a connected scenario set with:

```console
edu-roi scenario validate \
  scenarios/examples/workforce-high-school.yaml \
  scenarios/examples/example-bachelors.yaml
```

The command validates each document, checks counterfactual and graduate-school references, rejects
cycles and incompatible money bases, and emits deterministic scenario and graph hashes. Caller file
order does not affect the output. Print the formal JSON Schema with:

```console
edu-roi scenario schema
```

## Contract boundaries

The initial contract covers scenario identity, education or workforce configuration, institution,
CIP and classification version, completion states, costs, financing, earnings quantiles,
counterfactuals, graduate-school references, monetary assumptions, horizon, and dataset pins.

Graph resolution confirms that definitions form a coherent dependency graph. It does not download
datasets or turn unresolved values into calculated cash flows. The next boundary resolves numeric
inputs through an explicit provider:

```console
edu-roi scenario resolve scenarios/examples/*.yaml --fixture-values values.yaml
```

The current provider is deliberately fixture-backed for deterministic development and integration
testing. Each returned data value must identify the requested source and exact pinned vintage, an
artifact ID, and any transformation IDs. A missing value becomes `INSUFFICIENT_DATA`; a provider may
not substitute a newer or different release. Explicit `PROVIDED` values retain their source,
including zero. Earnings remain a validated pinned dataset reference until the earnings-profile
provider is connected; this command does not invent an earnings curve.

Resolved scenarios are emitted in counterfactual-first order with canonical per-scenario and graph
hashes. Until the Plan 07 evidence gate is resolved, scenario output remains provisional and must
not be labeled decision-grade.

## Synthetic analysis boundary

`edu-roi scenario analyze` combines the resolved-value fixture with a separate, explicit
age-earnings fixture. The latter identifies source, exact vintage, artifact and transformation IDs,
quantile, enrollment duration, and one earnings value for every modeled age. Conditional-graduate
analysis requires an on-time-graduate profile. Enrollment-return analysis requires a distinct
profile and enrollment duration for every completion outcome whose probability is nonzero.

The command constructs annual component cash flows, applies the disclosed selection adjustment,
subtracts the referenced counterfactual, and reports NPV, IRR, lifetime values, and break-even age.
If any cost, financing, completion, timing, or earnings input is unresolved, it returns a structured
`INSUFFICIENT_DATA` result instead of calculating partial metrics. Fixtures are synthetic test
infrastructure, not institution-level evidence.

## Comparison run bundles

`edu-roi compare` accepts two or more education scenario IDs that share an explicit counterfactual,
money basis, horizon, and earnings quantile. It reports each scenario against the common baseline
and every pairwise education-option comparison. Different quantiles are rejected rather than being
presented as comparable.

Each invocation writes a new immutable run directory containing the original scenario YAML,
resolved inputs, earnings fixture, assumptions, dataset references, validation findings, full JSON
comparison, and CSV metric table. `manifest.json` records byte sizes and SHA-256 hashes. Existing
run directories are never overwritten, and `edu-roi scenario verify-bundle RUN_DIRECTORY` detects
missing or altered artifacts. All fixture-backed bundles are visibly marked provisional.
