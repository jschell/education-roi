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
cross-release comparisons, and analytical Parquet tables remain future work.
