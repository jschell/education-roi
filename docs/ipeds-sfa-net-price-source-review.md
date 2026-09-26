# SFA2223 aid and net-price source review

**Reviewed:** 2026-09-25. The [NCES 2023 complete data inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023)
lists Student Financial Aid and Net Price for academic year 2022–23, revised
December 2025. The reviewed [data ZIP](https://nces.ed.gov/ipeds/complete-data-files/SFA2223.zip)
and [dictionary ZIP](https://nces.ed.gov/ipeds/complete-data-files/SFA2223_Dict.zip)
are pinned together in the release catalog.

| Archive | SHA-256 observed | Pinned member |
| --- | --- | --- |
| `SFA2223.zip` | `46b46de12765f0ff91767ccf0de3473db0116c0cb962359cfd0326204f6a25a5` | `sfa2223_RV.csv` |
| `SFA2223_Dict.zip` | `328a4b371ced9676ac8bc3aea904ad06772902e65a4030f9de9b7cef265a6d12` | `sfa2223.xlsx` |

The data ZIP also includes initial `sfa2223.csv`; the catalog selects the
revised member. Its workbook Introduction says **Final/revised release** and
the definition sheet is `Varlist`. The older `datacenter/data/SFA2223.zip`
pair observed during review contains only a provisional member and a workbook
labeled provisional; it must not substitute for the pinned pair. The final
revised CSV has 5,653 unique institution `UNITID` rows.

The same workbook defines several distinct net-price populations. Initial
reviewed fields for the 2022–23 period include:

| Field | Population and basis | Paired source status |
| --- | --- | --- |
| `NPIST2` | Full-time, first-time degree/certificate-seeking students paying public in-state/in-district tuition and awarded qualifying grants or scholarships | `XNPIST2` |
| `NPIS412` | Same public residency basis; Title IV aid recipients with income $0–30,000 | `XNPIS412` |
| `NPGRN2` | Grant/scholarship recipients at private institutions with standard calendars, and specified other reporting structures | `XNPGRN2` |
| `NPT412` | Title IV recipients with income $0–30,000 at those other reporting structures | `XNPT412` |

The dictionary's longer `Description` entries, not just the short `Varlist`
labels, establish these differences. For University of Washington, UNITID
236948, `NPIST2=11023` with status `R`, `NPIS412=6398` with status `R`, while
`NPGRN2` and `NPT412` are blank with status `A`. These are historical averages
for selected aid-recipient groups, not an offer to a particular student.

**Implementation gate:** This PR catalogs the source only. A subsequent slice
must validate the exact workbook descriptions, preserve raw cells and status
codes, and return a population-labeled observation. Public and other reporting
bases must not silently substitute for each other. Do not subtract grant aid
again from a net-price observation, combine it with a separately reported
cost-of-attendance total as if it were tuition alone, or infer a student's
aid award from an institutional average. Scenario use remains unresolved.
