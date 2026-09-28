# GR2023 two-year cohort source review

The reviewed [NCES 2023 GR inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=8)
describes the 2020 two-year entry cohort at 150% of normal time. The catalog's
`/ipeds/complete-data-files/GR2023.zip` and `GR2023_Dict.zip` retained their
previously observed SHA-256 values on 2026-09-27:

| Archive | SHA-256 |
| --- | --- |
| GR2023.zip | `59b69f36561aec769695cd5bad9478c53084641c2df36835f13e78c6bd28b6ea` |
| GR2023_Dict.zip | `dd6d5786b2f88eaeb6cfc59fcf4dfe6d8aa995d966b5caf6c5ac67d16dc86dcb` |

The final revised CSV member is `gr2023_RV.csv`. Its workbook's final-member
frequency labels identify `GRTYPE=27` as two-year degree/certificate seekers,
`29` as their adjusted cohort, and `30` as any award within 150% of normal
time. The exact total-count rows use `COHORT=4`, `SECTION=4`,
`CHRTSTAT=12`, `LINE=50` for the denominator and `CHRTSTAT=13`,
`LINE=29A` for the numerator. Both use `GRTOTLT` and its `XGRTOTLT` source
status. This is a distinct 2020 entry cohort and award scope from the 2017
four-year bachelor's mapping (`GRTYPE=8` and `12`).

The final archive has 1,454 institutions with the adjusted two-year cohort
row; 1,445 also have the selected award row. Missing award rows remain
insufficient data. An official paired registration and exact lookup for
`UNITID=100760` yielded 225 adjusted entrants and 54 any-award completers,
both reported (`R`), for an observed rate of 24%. A four-year institution
(`UNITID=236948`) has no two-year mapping and returns insufficient data.

```sh
edu-roi ipeds resolve-gr2023 100760 \
  --catalog data/manifests/ipeds-release-catalog.json --two-year
```

The resolver verifies paired artifact hashes and release, checks the workbook
labels, scans the selected final member for unique exact keys and compatible
row codes, preserves source statuses, and rejects counts above the cohort.
`edu-roi ipeds build-gr2023-two-year --catalog
data/manifests/ipeds-release-catalog.json` produces a separate immutable
Parquet table and processing manifest. The official build produced 1,454
institution rows: 1,445 observed rates and nine missing award rows with
explicit unavailable reasons. The Parquet SHA-256 was
`aab6c92ef105688581fb39e4904b9a75e0d62aa359ffdf8e70e1bd7ec95edf45`;
an isolated rerun returned the same manifest and bytes. The table preserves
both original count cells, source statuses, row keys, release, cohort scope,
and paired artifact IDs without using the bachelor-specific award column.

`edu-roi ipeds resolve-gr2023-two-year-table TABLE.parquet UNITID` verifies
the complete processed table and adjacent manifest before returning one
institution. It checks the exact 2020 two-year any-award definition, source
lineage, ordered UNITIDs, raw-to-numeric counts, row keys, statuses,
availability, and computed rate. Missing institutions and the nine missing
award rows remain explicit insufficient-data results.

This 150% any-award rate is an institutional historical observation, not an
associate degree rate or an individual completion probability. Cross-release
comparison and scenario outcome mapping remain separate tasks.
