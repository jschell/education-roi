# Zhang Reproduction Plan

**Status:** READY EXCEPT SUPPLEMENTAL CROSSWALK/DETAILS  
**Plan:** 01 — Methodology Research

## Goal

Reproduce selected results in Zhang, Liu, and Hu (2024), DOI https://doi.org/10.3102/00028312241231512, using immutable ACS 2009–2021 inputs, documented NPSAS-derived costs, and the verified Equations 1–6.

## Remaining entry blockers

Before coding the paper-labeled reproduction:

1. Obtain supplemental `sj-pdf-1-aer-10.3102_00028312241231512.pdf`.
2. Transcribe Table A1’s exact 173-field-to-10-major crosswalk.
3. Check the supplement for survey-weighting, variance, and additional-decile details.
4. Resolve whether Equation 2 estimates all covariate slopes separately by group.
5. Decide how to reproduce restricted NPSAS cost cells if restricted-use data are unavailable.

The article PDF resolves the prior full-text blocker.

## Pinned research specification

- ACS annual 1-year PUMS: 2009–2021.
- U.S.-born, ages 18–65.
- Highest education exactly high-school diploma or bachelor’s.
- Bachelor’s graduates must report first major.
- Exclude enrolled persons, advanced degrees, associate/some-college, and nonpositive earnings.
- Primary outcome: annual wage/salary earnings.
- Apply ACS income adjustment then BLS CPI to 2021 dollars.
- Covariates: sex, race/ethnicity, marital status, Census region; age and age squared.
- Separate log-earnings profiles for high school and ten major groups.
- Standardize with pooled bachelor’s-graduate covariate means.
- Predict ages 18–65.
- College attendance ages 18–21.
- Preferred cost case: tuition/fees + $1,000 books + 50% other nontuition costs, net of grants.
- Add student earnings of $3,268/year in 2021 dollars.
- Preferred selection adjustment: 25%; opportunity-cost counterfactual is 15% above observed same-age high-school earnings.
- Quantile regressions at deciles with rank invariance.
- IRR solves verified Equation 5.

## Work packages

### R1 — Supplemental extraction

Transcribe:

- detailed ACS field crosswalk;
- additional decile results;
- robustness tables;
- weighting/estimation notes;
- any target values absent from the main paper.

Hash the supplement and record its provenance; do not commit copyrighted full text.

### R2 — Source acquisition

Download and register all 13 ACS person files, dictionaries, code lists, and the selected BLS CPI series. Pin exact revisions and SHA-256 values.

NPSAS:18-AC is restricted-use. For strict reproduction, determine whether authors’ published aggregate cells can be transcribed from article/supplement or whether licensed restricted-use access is required. Never manufacture missing cost cells.

### R3 — Variable mapping

Confirm vintage-specific codes/fields for:

- birthplace/U.S.-born;
- `AGEP`;
- `SEX`;
- race and Hispanic origin;
- marital status;
- region derived from state;
- `SCHL`;
- school enrollment;
- employment status;
- first field of degree;
- wage/salary income;
- total earnings robustness;
- income adjustment;
- person/replicate weights.

Create a per-vintage schema table rather than assuming names/codes are invariant.

### R4 — Sample-flow test

Emit unweighted and weighted counts after each restriction. Target final unweighted N is 5,835,917. Approximate 2.9M/2.9M group counts are descriptive; exact counts should come from the reproduction.

### R5 — Earnings models

Implement Equations 1–4 and generate profiles. Run both plausible Equation 2 interpretations if the supplement does not resolve group-specific covariate slopes. Save coefficients, standardized covariates, and annual predicted earnings.

### R6 — Quantile models

Implement Equation 6 at deciles. Validate against a second quantile-regression implementation on fixtures. Preserve solver, tolerance, weighting, and convergence metadata.

### R7 — Costs and opportunity costs

Reconstruct:

- race/major average NPSAS net costs;
- $1,000 books;
- 0/50/100% other nontuition cases;
- $3,268 student earnings;
- high-school foregone earnings ages 18–21;
- 0/25/50% selection cases and the corresponding opportunity-cost adjustment.

### R8 — IRR

Solve Equation 5 robustly, report no-root/multiple-root cases, and retain complete cash flows. Do not round until presentation.

### R9 — Targets

Minimum target set:

- overall preferred IRR: women 9.88%, men 9.06%;
- at least three Table 3 assumption combinations;
- computer science and engineering preferred results;
- education and humanities results;
- median and at least two nonmedian deciles;
- one sex and one race/ethnicity comparison;
- one time-trend result if fully specified.

## Tolerances

Declare before inspecting calculated targets:

- printed IRR: ±0.10 percentage point when source inputs are identical;
- sample count: exact for same ACS inputs/rules;
- annual profile: ±0.5% relative unless published rounding dominates;
- coefficient/quantile solver: independently tested numerical tolerance.

Restricted-data approximations must be labeled and cannot pass strict reproduction merely by matching a rounded IRR.

## Required outputs

- sample-flow CSV/JSON;
- coefficient tables;
- age profiles;
- annual cash flows;
- target comparison report;
- manifest bundle;
- ambiguity/discrepancy report;
- deterministic test command.

## Exit gate

Plan 01 completes only after the supplement/crosswalk and weighting ambiguities are resolved or a reviewer explicitly approves a bounded substitute. Plan 07 completes only when selected published results pass predeclared tolerances or discrepancies have accepted evidence-based explanations.
