# Plan 01 — Methodology Research

## Objective

Create an independently verified, implementation-ready specification of Zhang, Liu & Hu (2024). This is a hard gate before substantial analytical code.

## Non-goals

- Do not implement the financial engine.
- Do not substitute interpretations from secondary summaries for the paper.
- Do not tune assumptions to force agreement with reported values.

## Prerequisites

- Legally accessible paper text.
- Supplementary materials, appendices, replication artifacts, and cited source definitions where available.
- A research log recording access date and source.

## Work packages

### 1. Research inventory

Record publication metadata, corrections, appendices, supplements, replication code/data availability, and access restrictions.

### 2. Equation catalog

Transcribe and explain every equation needed for:

- age-earnings profiles;
- education costs;
- foregone earnings;
- cash flows;
- IRR;
- quantile regression;
- selection adjustment;
- sensitivity analyses.

Assign stable equation identifiers and connect each term to a proposed code variable.

### 3. Sample construction

Document:

- ACS products and vintages;
- population universe;
- age restrictions;
- employment and earnings restrictions;
- educational-attainment filters;
- major/field coding;
- treatment of zero and negative earnings;
- graduate degrees;
- geography;
- survey weights;
- pooling and inflation treatment;
- missing-data treatment.

### 4. Statistical specification

Document dependent variables, covariates, quantiles, functional form, standard-error treatment, weighting behavior, and any smoothing/interpolation.

### 5. Cost and counterfactual construction

Document direct education costs, duration, foregone earnings, living costs, counterfactual population, timing conventions, and terminal age.

### 6. Selection adjustment

Identify its conceptual basis, formula, timing, preferred value, and sensitivity range. Clearly separate author choices from project extensions.

### 7. Reproduction targets

Select a small set of aggregate and major-level published results. Define absolute and relative tolerances before implementation.

### 8. Ambiguity register

For every unresolved item, record:

- question;
- evidence found;
- plausible interpretations;
- effect on results;
- proposed experiment or author-contact need;
- decision status.

## Deliverables

- `docs/methodology.md`
- `docs/reproduction-plan.md`
- research bibliography/source log
- equation-to-code mapping
- ACS variable candidate table
- ambiguity register
- reproduction target table

## Tests and review

- Every implemented term must trace to an equation or documented extension.
- A second review should be able to reconstruct the proposed algorithm.
- Project extensions must be visually distinct from the published method.
- Copyright restrictions must be respected; summarize rather than reproduce protected text excessively.

## Acceptance criteria

- All model-critical equations are documented.
- Exact or best-supported sample rules are stated.
- Weighting and quantile behavior are explicit.
- Cost and selection assumptions are explicit.
- Reproduction targets and tolerances are approved.
- Unresolved ambiguities are visible and do not masquerade as settled facts.

## Exit gate

Move to analytical implementation only after methodology artifacts receive `REVIEW_REQUIRED → COMPLETE`.
