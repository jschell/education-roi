# C2022_A prior-year program awards source review

The [NCES 2022 Completions inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2022&surveyNumber=3)
lists C2022_A awards/degrees conferred by six-digit CIP and award level for
July 1, 2021 through June 30, 2022, revised August 2024. The official
[data ZIP](https://nces.ed.gov/ipeds/datacenter/data/C2022_A.zip) and
[dictionary ZIP](https://nces.ed.gov/ipeds/datacenter/data/C2022_A_Dict.zip)
were inspected together.

| Archive | SHA-256 observed | Reviewed member |
| --- | --- | --- |
| `C2022_A.zip` | `f81b8390d1758ac710b85a1d5a7af51372770335a02c0d06802a46d3a068126c` | `c2022_a_rv.csv` |
| `C2022_A_Dict.zip` | `6451fa19021036beee3eb80973483b76b3624ac3defd1b6f7eb4692f40395a85` | `c2022_a.xlsx` |

The data archive also contains `c2022_a.csv`; the catalog pins only the
revised member. It contains 301,055 rows and 301,055 distinct
`(UNITID, CIPCODE, MAJORNUM, AWLEVEL)` keys. The workbook introduction
identifies CIP 2020 and awards between July 2021 and June 2022. Its variable
list defines `CTOTALT` (grand total) and paired `XCTOTALT` imputation flag;
the frequency sheet identifies `MAJORNUM=1` as first major and `AWLEVEL=5`
as bachelor's degree. Observed `XCTOTALT` flags are 301,045 `R` (reported)
and 10 `C` (analyst corrected reported value).

The older workbook names its variable sheet `varlist` rather than `Varlist`.
Its imputation values sheet adds a heading row and labels `Z` as “Implied
zero;” instead of the C2023_A wording “Implied zero.” The revised CSV uses
zero-padded award levels (for example `05`) and legacy text encoding. These
are release-specific parsing and validation requirements. Paired registration
and exact-key raw lookup now validate this release using separate dataset IDs,
the lowercase workbook member and sheet, the reviewed imputation labels,
legacy CSV decoding, and the July 2021–June 2022 reporting period. An isolated
official-archive registration verified both ZIP hashes and a lookup of
`UNITID=100654`, CIP `01.0999`, first major, bachelor's level: nine awards
with reported `XCTOTALT=R`. The nonrevised member has 300,877 rows compared
with 301,055 revised rows; both report nine for this specific key. The raw
ZIPs are not committed.

Use `edu-roi ipeds register-program-awards --catalog
data/manifests/ipeds-release-catalog.json --release-id 2022-23-final` and
`edu-roi ipeds resolve-program-awards 100654 01.0999 1 5 --catalog
data/manifests/ipeds-release-catalog.json --release-id 2022-23-final`.
`edu-roi ipeds build-program-awards --catalog
data/manifests/ipeds-release-catalog.json --release-id 2022-23-final` now
produces an immutable release-specific Parquet table and processing manifest.
The official 301,055-row build produced a 1,077,717-byte Parquet artifact
with SHA-256 `fd228fae423f06be6fe02545b3f7c92e23df9017f4ae994e2e96a231ecf9ef5e`;
an isolated rerun returned the same manifest. `edu-roi ipeds
resolve-program-awards-table TABLE.parquet UNITID CIPCODE MAJORNUM AWLEVEL`
now verifies the complete C2022_A table, sidecar hash, release period,
transformation version, exact keys, source cells, and paired artifact IDs.
The official table lookup for UNITID 100654, CIP `01.0999`, first major,
bachelor's level returned nine reported awards with the matching table hash.
Cross-release comparison remains gated.
