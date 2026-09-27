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
are release-specific parsing and validation requirements, not evidence that
the current C2023_A pipeline supports C2022_A. Paired registration, processed
tables, and cross-release comparisons remain gated pending implementation and
live validation.
