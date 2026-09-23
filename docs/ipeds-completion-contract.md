# IPEDS graduation cohort contract (Plan 09)

**Research snapshot:** 2026-09-23. **Status:** cohort contract only; no release-specific GR
dictionary mapping or completion probability is approved.

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

## Gate before ingestion or scenario use

1. Download an exact NCES GR/GR200 archive and its paired dictionary from a reviewed inventory;
   retain their URLs, hashes, release status, and retrieval time.
2. Identify and record the dictionary's variable codes and allowed values for adjusted cohort,
   completers, award scope, cohort year, race/sex and aid subgroups, exclusions, transfers,
   imputation and source statuses. Reject unknown code mappings.
3. Verify applicable 4-year/2-year cohorts and reported horizons against the survey form for that
   collection year. Preserve raw count cells, their denominator, and source row key.
4. Recompute selected published institution-level rates; compare to NCES reported values and
   document discrepancies. Only then connect a validated institutional observation to a scenario
   with explicit applicability and sensitivity assumptions.

The repository does not yet include a reviewed GR/GR200 release pair or its exact variable mapping.
The URLs and labels above are discovery references, not an approved data release. Missing or
inapplicable completion evidence remains insufficient data.
