# Education Path ROI — Project Plan

## 1. Objective

Build an open-source, reproducible framework for comparing the financial outcomes of post-secondary education and career paths, including:

- institutions and majors;
- four-year college;
- community college and transfer;
- immediate workforce entry;
- registered apprenticeships and earn-while-learning pathways;
- technical education;
- later extensions for military and certification pathways.

The system must support arbitrary scenario comparisons without changes to calculation code. It must not reduce decisions to a proprietary score or universal ranking. It must expose the evidence, assumptions, tradeoffs, uncertainty, and distribution of plausible outcomes.

Every published result must be traceable:

`output → calculation → transformed data → original authoritative dataset`

A result without machine-readable provenance is invalid.

## 2. Research foundation

The initial methodological target is:

Zhang, Liu & Hu (2024), “Degrees of Return: Estimating Internal Rates of Return for College Majors Using Quantile Regression,” *American Educational Research Journal* 61(3), 577–609.

Preserve and independently verify:

- education as an investment;
- education costs and foregone earnings;
- age-earnings profiles;
- counterfactual earnings paths;
- IRR;
- heterogeneous returns by major;
- quantile regression and earnings distributions;
- explicit selection adjustment;
- sensitivity testing.

Before institution-level results are trusted, selected published results must be reproduced within documented tolerances. Discrepancies must be investigated and documented, never tuned away merely to force equality.

## 3. Three distinct analyses

### A. Return to education

Compare education with a no-college counterfactual. This supports research reproduction.

### B. Return to institution/program

Compare a specific institution and major with a workforce counterfactual, incorporating actual costs, completion, and time-to-degree.

### C. Incremental decision value

Compare Option A directly with Option B. A scenario may reference another education scenario as its counterfactual.

Examples:

- UW CS vs. WSU CS;
- UW four years vs. community college → UW transfer;
- college vs. apprenticeship;
- one major vs. another.

## 4. Core model

Model the decision as:

`education costs + foregone earnings + financing costs + completion probability + time to completion + earnings trajectory + employment risk + graduate education + alternative-path earnings → financial return`

The primary unit is a **scenario**.

The engine must separately model:

- tuition, fees, books, supplies, transportation, and other expenses;
- sticker price, net price, and incremental living cost;
- aid, scholarships, family contribution, and student contribution;
- federal/private loans, origination fees, interest, and repayment;
- graduate on time, graduate late, transfer, and leave without a degree;
- conditional-graduate return and enrollment return;
- optional or mandatory graduate-school branches;
- counterfactual earnings, including other scenarios.

## 5. Authoritative data sources

Prefer original government sources over commercial aggregators. Verify current official documentation and download methods before implementation.

### ACS PUMS

Primary source for earnings distributions and age-earnings profiles. Candidate variables include age, attainment, bachelor’s field, earnings, employment, geography, occupation, industry, sex, and person weights.

Requirements:

- support ACS 1-year and 5-year;
- use Census weights correctly;
- prefer downloadable files over repeated live API calls;
- retain vintage, geography, sample details, and exact variable definitions;
- use 5-year data when sample size requires it.

### College Scorecard

Use for institution/field earnings, debt, repayment, completion, net price, and institution characteristics. Treat as an independent cross-check rather than assuming equivalence with ACS.

Retain cohort definition, reporting period, suppression status, and sample size where available.

### IPEDS

Use for tuition, fees, enrollment, characteristics, retention, completions, graduation, aid, and program production.

Retain publication status: preliminary, provisional, or final. Default to the newest statistically appropriate validated final release. Provisional data require visible warnings.

### BLS OEWS

Use for occupation wage context and validation at national, state, metropolitan, and nonmetropolitan levels. Do not equate degree with occupation.

### BLS Employment Projections

Use for employment levels, growth, replacement needs, and occupational outlook. Keep forecasts distinct from observed historical earnings.

### BLS CPI

Normalize monetary values to a common target dollar year. Record nominal source year, CPI series, target year, and conversion factor. Model internally in real dollars where practical.

### Federal Student Aid

Use official loan rates, borrowing limits, repayment rules, and program definitions. Version financing assumptions; never permanently hard-code current rates.

### NCES CIP and SOC

CIP is the canonical program taxonomy. SOC is the occupation taxonomy.

Always retain:

- classification version;
- source and target codes;
- crosswalk version;
- mapping confidence.

Never silently combine or reinterpret incompatible classification versions.

### Additional pathways

Design for later ingestion of Department of Labor apprenticeship data, official military compensation/benefit schedules, and technical programs. Certification estimates require explicit evidence-quality limits.

## 6. Immutable data and manifests

Do not commit large government datasets to Git.

```text
data/
├── raw/
│   ├── census/
│   ├── ipeds/
│   ├── scorecard/
│   ├── bls/
│   └── fsa/
├── processed/
├── crosswalks/
└── manifests/
```

Raw artifacts are immutable. Processed datasets must be fully regenerable.

Each source artifact receives a manifest containing at least:

```yaml
source:
dataset:
publisher:
release:
vintage:
retrieved_at:
source_url:
sha256:
file_size:
publication_status:
schema_version:
```

A new release never overwrites an earlier release.

## 7. Update and approval workflow

```text
DISCOVERED → DOWNLOADED → VALIDATED → APPROVED
                               └──────→ REVIEW_REQUIRED
                                          ├──→ APPROVED
                                          └──→ REJECTED
```

For every update:

1. Check the authoritative source.
2. Identify the latest release.
3. Compare it with manifests.
4. Download the artifact.
5. calculate SHA-256.
6. Validate transport and schema.
7. Run statistical quality tests.
8. Transform the data.
9. Compare against the previous release.
10. Run reproduction tests.
11. Generate a validation report.
12. Require review for suspicious changes.

Default data policy: use the latest statistically appropriate, validated, final dataset. A `--latest` option may allow provisional/newer data with warnings.

## 8. Validation

### Transport

Validate HTTPS source, expected government domain, completion, file size, checksum, and archive integrity.

### Schema

Validate expected columns, types, coding systems, ranges, required fields, and classification versions.

### Statistical

Validate record counts, weighted population, null rates, earnings distributions, ages, degrees, and geography. Compare releases and require review for anomalous changes.

### Cross-source

Compare ACS major earnings against Scorecard institution/field outcomes and OEWS occupational wages. Investigate differences; do not average them automatically.

Potential explanations include population, age, geography, cohort timing, graduate education, occupation-vs-degree definitions, inflation basis, suppression, sample size, and selection effects.

## 9. Sample reliability and fallback

Every estimate should retain, where available:

- unweighted N;
- weighted N;
- standard error;
- confidence interval;
- dataset and vintage;
- geography;
- age band;
- major level.

Implement transparent hierarchical fallback, such as:

`Seattle CS age 32 → Seattle CS age 30–34 → Washington CS age 30–34`

Record and disclose the level actually used.

## 10. Earnings and counterfactuals

Construct age-earnings curves for approximately ages 18–65, configurable by run.

Support P10, P25, P50, P75, and P90. These are observed positions in an earnings distribution, not probabilities assigned to an individual.

Initially reproduce the paper’s quantile-regression approach. Evaluate alternatives only after reproduction is validated.

Foregone earnings are never assumed to be zero. Counterfactuals may be high-school workforce, some college, associate degree, apprenticeship, another university, another major, or another arbitrary scenario.

## 11. Selection adjustment

Observed earnings differences are not purely causal. Implement a visible configurable selection adjustment.

Initial sensitivity values:

- 0%;
- 10%;
- 25%;
- 40%;
- 50%.

Use 25% only where justified for reproducing the paper’s preferred specification. Never hide or silently replace this assumption.

## 12. Completion and time-to-degree

Support 2, 4, 5, 6, and custom durations. Additional time changes tuition, living cost, foregone earnings, debt, and the start of post-completion earnings.

Model transitions:

- graduate on time;
- graduate late;
- transfer;
- leave without degree.

Calculate both conditional-graduate return and expected enrollment return.

## 13. Cash-flow and financial metrics

For each modeled year:

`cash flow = earnings - educational expenses - incremental living expenses - financing expenses`

Default horizon: age 18–65, configurable.

Calculate:

- IRR;
- NPV;
- lifetime earnings;
- lifetime net financial value;
- break-even age;
- total education cost;
- total financing cost;
- debt at graduation;
- years to debt payoff.

Support real discount-rate sensitivity at 2%, 3%, 4%, 5%, and 6%.

## 14. Distribution and sensitivity

Return distributional tables across P10/P25/P50/P75/P90 for earnings, lifetime earnings, NPV, IRR, and break-even age.

Sensitivity analysis is mandatory. Vary:

- net price;
- completion probability;
- time-to-degree;
- selection adjustment;
- earnings quantile;
- discount rate;
- aid;
- debt;
- graduate-school probability;
- real wage growth.

Report the range and the assumptions that materially drive the result. Avoid false precision.

## 15. Monte Carlo

Implement only after deterministic calculations are validated.

Potential stochastic variables include completion, time-to-degree, earnings, employment gaps, aid, graduate school, debt, and wage growth.

Default target: 10,000 simulations per scenario.

Potential outputs:

- median/P10/P90 NPV;
- median/P10/P90 IRR;
- probability NPV > 0;
- probability IRR > discount rate;
- median break-even age.

Do not assign distributions without empirical or documented justification.

## 16. Scenario schema

Use human-readable YAML validated against a formal schema.

```yaml
scenario:
  name: "UW Computer Science"
institution:
  unitid: 236948
education:
  credential: bachelors
  cip: "11"
  expected_duration_years: 4
costs:
  tuition_source: ipeds
  net_price_source: scorecard
  incremental_living_cost: auto
financing:
  family_contribution: 10000
  student_debt: 20000
earnings:
  source: acs
  quantiles: [0.10, 0.25, 0.50, 0.75, 0.90]
counterfactual:
  scenario: workforce-high-school
assumptions:
  selection_adjustment: 0.25
  real_discount_rate: 0.04
  terminal_age: 65
```

No model assumption may change silently when data is unavailable.

## 17. Provenance and evidence quality

Every result includes a machine-readable provenance object with the metric, value, model version, exact dataset releases, and assumptions.

Evidence quality is exposed by component, with explanations, rather than collapsed into a mysterious confidence score.

Example components:

- earnings;
- institution costs;
- completion;
- financial aid;
- local labor-market validation;
- selection adjustment;
- graduate-school probability.

Valid ratings may include HIGH, MEDIUM, LOW, MODEL ASSUMPTION, and INSUFFICIENT DATA.

## 18. Reproducible outputs

Each run creates:

```text
results/
└── run-<timestamp-or-id>/
    ├── scenarios/
    ├── results.json
    ├── results.csv
    ├── assumptions.json
    ├── datasets.json
    ├── validation.json
    └── report.html
```

A run must be reproducible from model version, scenario definitions, dataset manifests, and assumptions.

## 19. Technical direction

Prefer straightforward components:

- Python;
- uv;
- DuckDB and/or Polars;
- Pandas only where compatibility helps;
- SQLite for persistent metadata;
- Parquet for analytical data;
- YAML;
- Pydantic or equivalent validation;
- pytest;
- Typer or argparse;
- static HTML and plots initially;
- Docker-compatible from the beginning, without requiring Docker locally.

A later optional interface should prefer vanilla JavaScript, HTML, and CSS. React/Vue require a concrete justification. The CLI and Python library remain fully usable without a UI.

## 20. Target repository structure

```text
education-roi/
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── compose.yaml
├── docs/
│   ├── project-plan.md
│   ├── methodology.md
│   ├── reproduction-plan.md
│   ├── datasets.md
│   ├── assumptions.md
│   ├── validation.md
│   └── reproduction.md
├── data/
│   ├── raw/
│   ├── processed/
│   ├── crosswalks/
│   └── manifests/
├── scenarios/
│   ├── examples/
│   └── schema.json
├── src/education_roi/
│   ├── cli/
│   ├── config/
│   ├── ingest/
│   ├── validation/
│   ├── crosswalks/
│   ├── earnings/
│   ├── costs/
│   ├── completion/
│   ├── financing/
│   ├── cashflow/
│   ├── simulation/
│   ├── provenance/
│   └── reports/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── data/
│   └── reproduction/
└── results/
```

## 21. Intended CLI

```shell
edu-roi data check
edu-roi data update acs
edu-roi data validate
edu-roi reproduce zhang
edu-roi analyze scenarios/uw-cs.yaml
edu-roi compare scenarios/uw-cs.yaml scenarios/wsu-cs.yaml scenarios/bellevue-transfer.yaml
edu-roi simulate scenarios/uw-cs.yaml
```

## 22. Testing strategy

### Unit tests

CPI conversion, NPV, IRR, debt amortization, earnings interpolation, quantile extraction, selection adjustment, sample fallback, and crosswalks.

### Data tests

Schemas, code ranges, null rates, counts, weighted populations, and duplicates.

### Regression tests

A known dataset and configuration must produce the same result.

### Cross-release tests

Flag unexpected changes between vintages.

### Reproduction tests

Published Zhang results must be reproduced within documented tolerances.

Example:

```text
Published:     9.06%
Reproduction:  9.12%
Difference:    0.06 percentage points
Tolerance:     PASS
```

## 23. Phases and hard gates

### Milestone 0 — Methodology (hard gate)

Before substantial code:

1. Obtain the paper and supplementary materials where available.
2. Document every equation.
3. Identify exact ACS variables and vintages.
4. Document sample restrictions.
5. Document weighting and quantile specification.
6. Document education-cost and foregone-earnings construction.
7. Document selection adjustment.
8. Define reproduction targets and tolerances.
9. Verify current official data sources and download mechanisms.
10. Identify methodological ambiguities explicitly.

Deliver:

- `docs/methodology.md`
- `docs/reproduction-plan.md`
- `docs/datasets.md`
- `docs/validation.md`

**Exit criterion:** an independently verified, testable research target exists. No calculation engine work begins before review of these artifacts.

### Milestone 1 — Project skeleton

Python project, uv, CLI shell, tests, Dockerfile, directories, and CI.

### Milestone 2 — Data provenance

Downloader abstraction, immutable raw storage, SHA-256, manifests, dataset registry, and source metadata.

### Milestone 3 — ACS

Ingestion, filtering, weighting, major classification, age cohorts, and earnings distributions.

### Milestone 4 — Financial engine

Cash flows, education and opportunity cost, CPI, NPV, IRR, lifetime metrics, and break-even.

### Milestone 5 — Zhang reproduction (hard gate)

Reproduce selected aggregate and major-level results. Stop and investigate material failure.

### Milestone 6 — Scenarios

Formal YAML schema, validation, scenario references, analysis, and comparison.

### Milestone 7 — IPEDS

Institution costs and completion.

### Milestone 8 — College Scorecard

Institution × field outcomes, net price, debt, repayment, and cross-validation.

### Milestone 9 — BLS

OEWS/contextual labor-market validation and clearly separated projections.

### Milestone 10 — Uncertainty

Sensitivity analysis, then Monte Carlo.

### Later phases

Alternative pathways, regional labor markets, graduate-school branches, and finally an optional web interface.

## 24. MVP boundary

MVP data:

- ACS PUMS;
- IPEDS;
- BLS CPI;
- optionally OEWS for validation.

MVP capabilities:

- versioned downloads and manifests;
- SHA-256 and schema validation;
- CPI normalization;
- age-earnings curves and earnings quantiles;
- costs and foregone earnings;
- selection adjustment;
- IRR, NPV, lifetime earnings, and break-even;
- YAML scenarios;
- JSON/CSV outputs;
- provenance;
- rigorous automated tests;
- selected Zhang reproduction.

Do not build the web interface in the MVP.

## 25. Definition of success

A user can compare scenario files and receive a report that answers:

- Where did this number come from?
- Which dataset and release produced it?
- What was the underlying sample?
- What assumptions affected it?
- Which alternative assumptions were tested?
- Can another researcher reproduce it?
- How sensitive is it?
- Is the available evidence sufficient?

If the framework cannot answer these questions, the result is not decision-grade.

## 26. Immediate next task

Research and document Milestone 0:

1. Verify Zhang et al. against the original paper and supplements.
2. Identify exact equations, ACS variables, vintages, sample construction, weighting, quantile specification, cost assumptions, and selection adjustment.
3. Define reproduction targets and tolerances.
4. Verify current authoritative source documentation and download mechanisms for ACS PUMS, IPEDS, College Scorecard, BLS OEWS/CPI, NCES CIP, and Federal Student Aid.
5. Create a source inventory with URLs, cadence, formats, versioning, licensing/usage restrictions, expected size, and update strategy.
6. Record unresolved ambiguities instead of selecting interpretations silently.
7. Produce the methodology and data-source specifications before writing the calculation engine.
