# EF2022D fall retention source review

**Reviewed:** 2026-09-24. The [NCES 2022 complete data inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2022&surveyNumber=2)
identifies the Fall Enrollment retention component. The official data and dictionary ZIPs
were downloaded from the [NCES data archive](https://nces.ed.gov/ipeds/datacenter/data/EF2022D.zip)
and [paired dictionary archive](https://nces.ed.gov/ipeds/datacenter/data/EF2022D_Dict.zip).

| Source | SHA-256 at review | Exact member |
| --- | --- | --- |
| `EF2022D.zip` | `fb040f5ae6b54653e9bb048d9417dd636a7cd9467eaa251811647adb93a1bf70` | `ef2022d_rv.csv` |
| `EF2022D_Dict.zip` | `c7c367a2ac6196deb88ae482e72f3e49e25fa6bcce94f4f4a67afa509b9926d0` | `ef2022d.xlsx` |

The data ZIP also contains the earlier `ef2022d.csv`; the catalog pins the revised
member. Both CSV members have 5,706 institution rows. The workbook Introduction
identifies a final/revised release, and its variable worksheet is named lowercase
`varlist` (unlike the `Varlist` worksheet in the reviewed EF2023D dictionary).

| Field | Exact reviewed workbook definition | Status field |
| --- | --- | --- |
| `RRFTCTA` | Full-time adjusted fall 2021 cohort | `XRRFTCTA` |
| `RET_NMF` | Students from the full-time adjusted fall 2021 cohort enrolled in fall 2022 | `XRET_NMF` |
| `RET_PCF` | Full-time retention rate, 2022 | `XRET_PCF` |

An exact revised-member spot check for University of Washington (UNITID 236948)
returned adjusted cohort 7,165, next-fall enrolled 6,707, and reported retention
94%. The separately published percentage must remain distinct from enrolled/count
division; retention may include completers and rounded values.

`edu-roi ipeds register-retention --catalog data/manifests/ipeds-release-catalog.json
--release-id 2022-23-final` validates the release-specific revised member and lowercase
worksheet before registering the exact paired sources. `resolve-retention` and
`build-retention` accept the same release option; the default remains 2023-24 final.
The resulting table has a distinct transformation version, explicit 2021/2022 years,
and an immutable paired-source manifest. `resolve-retention-table` verifies it before
lookup. An isolated official-source build produced 5,706 institution rows and UW
7,165 adjusted cohort, 6,707 enrolled, and published 94%.

`edu-roi ipeds compare-retention PREVIOUS.parquet CURRENT.parquet` verifies both
full tables and processing manifests before comparing the distinct 2021 and 2022
entry cohorts. It preserves both source and dictionary artifact IDs, table and
manifest hashes, published percentages separately from the adjusted-cohort and
next-fall-enrolled counts, and each raw source status. The default review thresholds
are 10 reported percentage points and 25% relative count change. Missing and
changed UNITIDs go through the directional institution pairing report; a supplied
history file can resolve unique changes, with optional `--history-source` hash
verification. `--fail-on-review` returns exit 1 for a review-required report.

An isolated comparison of both official archives returned 5,706 and 5,646 source
rows, 5,578 paired UNITIDs, and 196 identity/coverage findings. These findings
need review before interpreting institution-level trends. The rate is historical
first-year retention, not a causal effect or individual completion probability.
