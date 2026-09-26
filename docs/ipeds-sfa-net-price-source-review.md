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

The paired registration validates the final revised workbook descriptions,
required source columns, every row's UNITID and selected net-price cells, and
stores immutable data and dictionary artifacts. An exact-UNITID lookup verifies
both artifact hashes and requires one of four explicit population bases. It
returns the raw cell and paired source status, with an insufficient-data result
for absent, blank, or negative cells. Zero remains an observed value. No public
field falls back to a private/other reporting field or vice versa.

```bash
education-roi ipeds register-net-price --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
education-roi ipeds resolve-net-price 236948 public_in_state_grant --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
education-roi ipeds build-net-price --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
```

The processed Parquet table has one sorted row per UNITID and separate
numeric, raw, and source-status columns for each of the four population bases.
Its deterministic path includes both raw artifact hashes and the transformation
version. An adjacent manifest records the paired artifact IDs, exact source
member, field mapping, year, row count, and table hash. Rebuilding the same
sources returns the existing immutable table; changed bytes at that path fail.
This table is not yet exposed through a verified processed-table lookup.

An isolated official-source run resolved University of Washington's public
grant average as 11023 and public $0–30,000 Title IV average as 6398; both
other reporting bases returned insufficient data with source status `A`.
The official 5,653-row processed build and identical rerun were verified in
isolation. These are historical institutional averages, already reflecting qualifying
grant aid, not a student-specific offer or tuition alone. Scenario use remains
unresolved; do not subtract aid again or infer a student's award.
