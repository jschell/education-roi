# IPEDS graduation cohort contract (Plan 09)

**Research snapshot:** 2026-09-23. **Status:** final GR2023 four-year bachelor's observation
mapping implemented; institutional rates are not scenario completion probabilities.

## Authoritative source and population

NCES [Complete Data Files](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx) publishes
component files and dictionaries as downloadable CSV archives. The 2023 inventory separately
describes `GR2023` as 150%-of-normal-time graduation rates for 2017 four-year and 2020 two-year
entry cohorts; it also lists distinct 200%-of-normal-time and Outcome Measures files. These
collection, entry-cohort, and outcome years cannot be substituted for one another. The separate
[Access database page](https://nces.ed.gov/ipeds/use-the-data/download-access-database)
documents provisional and final release rules; availability must be determined per component.

NCES [survey methodology](https://nces.ed.gov/ipeds/survey-components/ipeds-survey-methodology)
defines the Graduation Rates population as first-time, full-time degree/certificate-seeking
entrants at an institution and tracks completion within 150% of normal time, transfers, and
allowable exclusions. [Student cohorts and subgroups](https://nces.ed.gov/ipeds/use-the-data/student-cohorts-and-subgroups)
and [measuring student success](https://nces.ed.gov/ipeds/use-the-data/measuring-student-success-in-ipeds)
explain why GR, GR200, and Outcome Measures have different cohorts and observation windows.

## Contract now implemented

An `IPEDSGraduationObservation` retains institution UNITID, exact release and publication status,
component (`GR` or `GR200`), entry-cohort year, bachelor's/other/all award scope, 150% or 200% of
normal time, adjusted cohort, completers, source artifact ID, and the exact source columns used.
Its observed rate is `completers / adjusted_cohort` only when the denominator is positive. A zero
denominator yields unavailable, while counts beyond the adjusted cohort are invalid. The release
catalog selects GR, GR200, and Outcome Measures independently. These observations are
institution-level descriptions of a defined cohort, not an individual's enrollment completion
probability or a program-specific graduation rate.

## Verified 2023–24 final Graduation Rates file

The NCES [2023 complete data inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=8)
links `GR2023.zip` and `GR2023_Dict.zip`. The data archive contains `gr2023.csv` (provisional)
and `gr2023_RV.csv` (final/revised). The dictionary (`gr2023.xlsx`) identifies the provisional
release as December 2024 and the final release as December 2025. The NCES
[release schedule](https://nces.ed.gov/ipeds/survey-components/data-release-schedule)
also lists the Winter 2023–24 collection's final release on December 9, 2025. The catalog
explicitly selects `gr2023_RV.csv` for `2023-24-final`; an archive path alone is insufficient.

The source ZIPs were inspected on 2026-09-23. Their observed SHA-256 hashes were:

| Artifact | SHA-256 at inspection |
| --- | --- |
| `GR2023.zip` | `59b69f36561aec769695cd5bad9478c53084641c2df36835f13e78c6bd28b6ea` |
| `GR2023_Dict.zip` | `dd6d5786b2f88eaeb6cfc59fcf4dfe6d8aa995d966b5caf6c5ac67d16dc86dcb` |

These are an observed snapshot, not permanent expected hashes. Acquisition registers the exact
downloaded bytes immutably, then validates their manifests and release selection. A changed ZIP
requires review before using its row meanings.

The dictionary's `gr2023_RV` frequency table defines this one mapping:

| Dimension | Adjusted cohort | Bachelor’s awards |
| --- | --- | --- |
| Entry cohort | 2017 four-year, full-time first-time bachelor's-seeking | Same |
| `COHORT`, `SECTION` | `2`, `2` | `2`, `2` |
| `GRTYPE`, `CHRTSTAT`, `LINE` | `8`, `12`, `50` | `12`, `16`, `18A` |
| Count cell | `GRTOTLT` | `GRTOTLT` |
| Source status | `XGRTOTLT` | `XGRTOTLT` |
| Meaning | Adjusted bachelor's-seeking cohort | Bachelor's or equivalent awards within 150% of normal time |

For example, the final file's `UNITID=236948` rows report an adjusted cohort of 6,713 and
5,619 bachelor's awards, an observed rate of about 83.7%. This is a source sanity check, not
a scenario result. The row code for **any award** in that cohort is `GRTYPE=9`; it is not used
as the bachelor's-award numerator. The resolver verifies the exact data member, source and
dictionary manifest hashes, dictionary row meanings, and unique row keys. It preserves the two
`XGRTOTLT` statuses; the official dictionary defines `R` as reported and `Z` as implied zero,
among other codes. A missing row or negative count yields explicit insufficient data. Unknown
or duplicate keys and counts above the adjusted cohort fail validation.

## Verified earlier final source: GR2022 (catalog only)

On 2026-09-23 NCES's [2022 complete data inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2022&surveyNumber=8)
was identified alongside directly downloadable official files at the older
`/ipeds/datacenter/data/` paths. `GR2022.zip` contains `gr2022.csv` and
`gr2022_rv.csv`; `GR2022_Dict.zip` contains `gr2022.xlsx`. The dictionary labels
the revised file final, dates that release September 2024, and describes the
2016 four-year entry cohort. The observed artifact hashes are:

| Artifact | SHA-256 at inspection |
| --- | --- |
| `GR2022.zip` | `c164e8706fce663ee1bfd382a6b21b0129dfaee977906bf730ca4b2b6f686bfe` |
| `GR2022_Dict.zip` | `05a6e3f181e510d80ef3fded0a9cd15caf7e4f3fa3f68ca1389afe7ed16cd7b4` |

The final workbook identifies the same bachelor's-seeking `COHORT=2`, `SECTION=2`
and selected count cells: adjusted cohort `GRTYPE=8`, `CHRTSTAT=12`, `LINE=50`,
versus bachelor's awards `GRTYPE=12`, `CHRTSTAT=16`, `LINE=18A`, both `GRTOTLT`
with `XGRTOTLT` source status. The final revised UW rows (`UNITID=236948`)
contain 6,411 and 5,409 respectively; these are different entrants from GR2023.

**Compatibility gate:** GR2022's revised CSV uses padded text in code cells
(for example `GRTYPE` is `" 8"`), lowercase `_rv` in the archive member, and an
older six-column workbook frequency layout. The GR2023 registration, resolver,
and transformer deliberately reject this release. The catalog records its
official source, but there is no validated GR2022 processed table yet. A future
slice must implement release-specific cell normalization, workbook validation,
and cohort-year handling before a live cross-release comparison can run. The
existing synthetic later-release comparison tests do not meet that gate.

## Gate before ingestion or scenario use

1. Run `edu-roi ipeds register-gr2023 --catalog data/manifests/ipeds-release-catalog.json`
   to download and validate the paired final data and dictionary into immutable raw storage.
   Registration checks the final CSV member, required columns, and all matching bachelor's
   cohort keys and duplicates, plus dictionary meanings. It does not validate all GR fields,
   statistical distributions, or every other cohort. Broaden validation before publication.
   `edu-roi ipeds resolve-gr2023 UNITID --catalog data/manifests/ipeds-release-catalog.json`
   reads the exact validated registry pair and returns the observed rate, population, source row
   keys, raw status codes, and both artifact IDs. It returns `INSUFFICIENT_DATA` for absent
   institution rows and `INVALID` for missing or ambiguous validated artifacts or failed hashes.
   `edu-roi ipeds build-gr2023 --catalog data/manifests/ipeds-release-catalog.json`
   builds an immutable, zstd-compressed bachelor’s cohort Parquet table and transformation
   manifest from that exact validated pair. It keeps raw count cells, imputation status codes,
   row keys, population definition, both artifact IDs, and an unavailable reason. It never
   converts blank, negative, or zero-denominator cells into a graduation rate. A rerun with
   identical inputs verifies the existing bytes and lineage; conflicting output fails.

   On 2026-09-23 the documented official ZIP hashes yielded 2,003 institution rows, of which
   1,926 had a computable rate and 77 were unavailable. UNITID 236948 yielded 5,619 / 6,713.
   These are validation observations for this release, not an estimate for every institution.

   `edu-roi ipeds compare-graduation PREVIOUS.parquet CURRENT.parquet --fail-on-review`
   compares two distinct final bachelor’s cohort tables with the same population and 150% window.
   It reports both table SHA-256 hashes and raw source artifact IDs, entry years, institution
   identity findings, availability/status changes, and absolute rate and relative count changes.
   The default review thresholds are 10 percentage points for the observed rate and 25% for
   cohort counts. An optional directional institution-history file can inform UNITID pairing;
   `--history-source` verifies its cited bytes. An unusual change requires manual investigation,
   not automatic rejection. These are different entry cohorts, so a rate change is not a causal
   treatment effect or a forecast for a student. Only GR2023 has a production transformer;
   GR2022 is source-reviewed but not yet ingested. Cross-release tests use synthetic 2024–25
   tables and do not certify that release.
2. Verify separate 2-year, any-award, GR200, aid subgroup, transfer, and imputation meanings
   against their own official files and survey forms before extending the mappings.
3. Recompute published institution rates, document discrepancies, and normalize rows to Parquet.
4. Connect a validated institutional observation to a scenario with explicit applicability and
   sensitivity assumptions; do not treat the raw cohort rate as causal or person-specific.

The repository catalogs the final GR2022 and GR2023 sources, but no government data ZIP is
committed. GR200 and other cohort definitions remain unimplemented. Missing or inapplicable
completion evidence remains insufficient data.
