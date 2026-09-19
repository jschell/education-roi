# ACS PUMS Pipeline

## Initial contract

The ACS pipeline uses the downloadable person CSV as its analytical source. Source archives and
their dictionaries are registered through the immutable provenance system before transformation.
The current official Census release is 2024; release selection remains explicit and never aliases
`latest` to a changing artifact.

An ACS release is identified by vintage, product (`1-Year` or `5-Year`), and geography. The source
adapter constructs the official `www2.census.gov` archive URL and the matching Census API variable
dictionary URL. Both are covered by the provenance domain policy for `census.gov`.

## Required person fields

The first transformation contract requires `SERIALNO`, `SPORDER`, `ADJINC`, `PWGTP`, `AGEP`,
`NATIVITY`, `SCH`, `SCHL`, `WAGP`, and `FOD1P`. The required set was checked against the downloadable
2024 one-year Washington person archive as well as the official 2024 API dictionary.

The initial named sample transformation implements restrictions verified from the Zhang, Liu, and
Hu main article:

- native-born (`NATIVITY = 1`);
- ages 18 through 65, inclusive;
- not enrolled during the prior three months (`SCH = 1`);
- exactly a regular high-school diploma (`SCHL = 16`) or bachelor's degree (`SCHL = 21`);
- positive wage and salary income (`WAGP > 0`);
- positive person weight (`PWGTP > 0`); and
- a reported first field of degree for bachelor's observations.

Raw Census columns are retained. Added columns identify education level, field code, person weight,
age band, the income adjustment factor, and adjusted wage/salary income. The adjustment is
`WAGP * ADJINC / 1,000,000`; it places observations on the source release's constant-dollar basis.
Conversion to a shared target dollar year is a distinct CPI transformation and must record its CPI
series and factor.

## Product and statistical decisions

- Reproduction uses annual one-year PUMS files for the paper's 2009–2021 window.
- Five-year PUMS is supported for later estimates needing more geographic or major-level support;
  one- and five-year observations must never be pooled silently.
- The person file is sufficient for this initial earnings sample. Household fields may be added only
  through an explicit keyed join with its own validation.
- Person estimates use `PWGTP`. Replicate weights and the variance estimator remain required before
  uncertainty intervals are reported.
- Weighted quantiles use the first ordered value whose cumulative positive weight reaches the target
  fraction of total weight. Outputs retain both unweighted and weighted sample sizes.
- Zero, negative, missing, and not-applicable wage values are excluded by the named positive-wage
  restriction. The original field remains available for audit before filtering.
- Age bands are 18–24, five-year bands from 25–29 through 55–59, and 60–65. Exact age is preserved.
- Graduate-degree holders are excluded from the paper-reproduction sample because `SCHL` must equal
  16 or 21. Later decision scenarios must model graduate education separately.

## Crosswalk gate

The exact mapping of 173 ACS field codes into the paper's ten major groups depends on supplemental
Table A1. Any reconstruction is marked `PROVISIONAL`. The code rejects provisional crosswalks when
asked to certify a Zhang reproduction; a `VERIFIED` status requires the publisher supplement or an
equivalent authoritative artifact.

## Deferred portions of Plan 05

The ingestion layer validates ZIP integrity, rejects traversal, encryption, ambiguous person files,
and configured expansion limits, and streams only the person CSV into an isolated temporary
directory. Polars lazily selects the contract columns instead of retaining the full source schema.

The first processing pipeline writes a content-addressed, release- and transformation-specific
Parquet path. Every row includes the source artifact ID, exact ACS release, transformation version,
and source-dollar basis.
An adjacent manifest records the raw artifact ID, output hash, parameters, row count, and schema.
Regeneration is idempotent; different bytes at an existing stable path cause a conflict rather than
silent replacement.

Automatic release discovery and dictionary registration, replicate-weight uncertainty,
hierarchical fallback, and cross-release anomaly checks remain active Plan 05 work.
