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
datasets or turn unresolved values into calculated cash flows. Dataset resolution and calculation
orchestration are later Plan 08 slices. Until the Plan 07 evidence gate is resolved, scenario output
remains provisional and must not be labeled decision-grade.
