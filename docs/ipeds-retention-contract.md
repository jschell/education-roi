# Fall 2023 first-year retention source contract

**Reviewed:** 2026-09-24. NCES [2023 complete data inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=2)
lists the Fall Enrollment component. The paired archives are
[`EF2023D.zip`](https://nces.ed.gov/ipeds/complete-data-files/EF2023D.zip) and
[`EF2023D_Dict.zip`](https://nces.ed.gov/ipeds/complete-data-files/EF2023D_Dict.zip).
The data archive contains both `ef2023d.csv` and `ef2023d_rv.csv`. The dictionary
introduces the workbook as a final/revised release, and the catalog explicitly
selects the revised member. Observed SHA-256s at review:

| Official ZIP | SHA-256 |
| --- | --- |
| `EF2023D.zip` | `21026ba9838e013e5202a64c3486889b1404405a16022a1826b7f4c4897262b6` |
| `EF2023D_Dict.zip` | `9377ca916e6d802d98baa92e249e5f086b0ddd09d3df37275ca53df9ac469207` |

The workbook's `Varlist` defines the selected full-time fields:

| Field | Workbook meaning | Paired status |
| --- | --- | --- |
| `RRFTCTA` | Full-time adjusted fall 2022 cohort | `XRRFTCTA` |
| `RET_NMF` | Members of that adjusted cohort enrolled in fall 2023 | `XRET_NMF` |
| `RET_PCF` | Full-time retention rate, 2023, reported as a percent | `XRET_PCF` |

The workbook introduction describes first-year persistence or completion and
allowable cohort exclusions and inclusions. Its `Varlist` labels `RET_NMF` as
*enrolled* the next fall. The implementation preserves that exact count meaning
and the separately reported, rounded rate; it does not equate the count divided
by the cohort with the published percent or infer how many completed. The
release dates in the workbook's Introduction label the revised member under a
second “Provisional release” row despite the final/revised heading. This
inconsistency is recorded here; the selected member and status are explicit.

`edu-roi ipeds register-retention --catalog data/manifests/ipeds-release-catalog.json`
validates and stores the two exact source ZIPs. `edu-roi ipeds resolve-retention
UNITID --catalog data/manifests/ipeds-release-catalog.json` returns the source
cells, statuses, entry cohort and observation years, publication status, and
both artifact IDs. Missing, blank, negative-sentinel, or zero-denominator
observations remain insufficient data. This is an institution-level historical
first-year retention observation, not a bachelor's graduation rate or a
probability for any individual scenario branch. Program-level applicability,
and cross-release comparisons remain future work.

`edu-roi ipeds build-retention --catalog data/manifests/ipeds-release-catalog.json`
builds a source-paired, zstd Parquet table from the validated final ZIP pair. The
content-addressed directory includes both input hashes and the transformation
version; its sidecar records the output hash, artifact IDs, source member,
population, cohort and observation years, and table schema. Rows retain each
raw source cell, paired source status, adjusted cohort, next-fall enrolled count,
and the separately reported percentage. Missing and zero-cohort records carry
an explicit unavailable reason. An identical rerun reuses the manifest; changed
output bytes or metadata fail rather than replacing the published table.

This table is historical institution-level evidence. It does not supply a
program-specific graduation probability or a scenario transition probability.
Cross-release comparisons remain future work.

`edu-roi ipeds resolve-retention-table TABLE.parquet UNITID` verifies the
processing manifest, full-table hash, schema, population, release, input
artifact IDs, and row-level source/parsed cells before returning an observation.
Absent UNITIDs and unavailable source cells return `INSUFFICIENT_DATA`. The
report includes both table and manifest SHA-256 values. It is an observed
historical retention result, with no scenario completion interpretation.
