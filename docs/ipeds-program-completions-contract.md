# C2023_A program awards source review

**Reviewed:** 2026-09-25. The [NCES 2023 Completions inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=3)
lists awards/degrees conferred by six-digit CIP, award level, race/ethnicity,
and gender for July 1, 2022 through June 30, 2023. The official
[data ZIP](https://nces.ed.gov/ipeds/datacenter/data/C2023_A.zip) and
[dictionary ZIP](https://nces.ed.gov/ipeds/datacenter/data/C2023_A_Dict.zip)
were inspected together.

| Archive | SHA-256 observed | Pinned member |
| --- | --- | --- |
| `C2023_A.zip` | `651d95b6405bb86c6c14884ed54225a27492199d21d8acd63cda2581aa60838a` | `C2023_a_RV.csv` |
| `C2023_A_Dict.zip` | `2738d0a2675f475e1c2bc92a63e7cea92b3caf5210d80f19eaf6a5523919f2e2` | `C2023_a_dict.xlsx` |

The data archive also contains the initial `C2023_a.csv`. The dictionary's
Introduction identifies the revised file as final and describes **CIP 2020**.
Its `Varlist` defines `UNITID` (institution), `CIPCODE` (CIP 2020 code),
`MAJORNUM` (first or second major), `AWLEVEL` (award level), and `CTOTALT`
(grand total), paired with source status `XCTOTALT`. The final `FrequenciesRV`
sheet labels `MAJORNUM=1` as first major and `AWLEVEL=5` as bachelor's degree.

The revised member has 303,460 rows with no duplicate
`(UNITID, CIPCODE, MAJORNUM, AWLEVEL)` keys in this review. It includes both
major values 1 and 2, multiple award levels, and 20,582 aggregate `CIPCODE=99`
rows. A program-level first-major bachelor's query must select the exact
`MAJORNUM=1`, `AWLEVEL=5`, six-digit CIP row and exclude aggregate CIP 99.
It must keep the raw count and status, exact release and CIP version, and
both source artifact IDs. No sum across first and second majors or CIP aggregate
rows should be called unique graduates.

This source counts **awards**, not distinct people and not entrants into a
program. It provides neither a program completion probability nor earnings.
The separate C2023_B file reports students receiving awards, with a different
population and aggregation. Program award counts must not be divided by a
GR/EF institutional cohort to make a program completion rate.

`edu-roi ipeds register-program-awards --catalog data/manifests/ipeds-release-catalog.json`
validates all revised-member keys and the paired workbook definitions before
immutably registering both ZIPs. `edu-roi ipeds resolve-program-awards UNITID
CIPCODE MAJORNUM AWLEVEL --catalog ...` verifies both artifact manifests and
source hashes, rechecks the full archive and dictionary, then returns one exact
count with its raw cell, source status, period, CIP version, and both artifact
IDs. Absent or negative-sentinel cells return `INSUFFICIENT_DATA`; zero remains
an observed zero. The CLI rejects aggregate CIP 99 as a lookup key.

An isolated full-source registration yielded `VALIDATED` for both archives.
UNITID 236948, CIP `03.0103`, first major, bachelor's level returned 93
awards with source status `R`. No government ZIPs are committed.

An immutable analytical table, source-status interpretation, cross-release
comparison, and connections to scenario program evidence remain future work.
