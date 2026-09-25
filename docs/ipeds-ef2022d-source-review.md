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

**Implementation gate:** This PR catalogs the reviewed source only. The existing
registration, dictionary validator, transformation, lookup, and CLI are pinned to
EF2023D. Extend them with an explicit EF2022D-specific definition and lowercase
worksheet check before accepting this release as validated input. Compare the
distinct 2021 and 2022 entering cohorts as historical observations, with UNITID
identity and coverage review. Neither rate is an individual completion probability.
