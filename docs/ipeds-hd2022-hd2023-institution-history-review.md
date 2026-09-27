# NCES 2022→2023 institution history review

The [NCES IPEDS data files](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=1)
provide the 2022 and 2023 directory archives (`HD2022.zip` and `HD2023.zip`)
and the 2023 dictionary (`HD2023_Dict.zip`). Reviewed SHA-256 values:

| Archive | SHA-256 |
| --- | --- |
| HD2022.zip | `e36389b793741bf6886b8d85fa9b42614644162b0d0b1d024a663a9c1865c782` |
| HD2023.zip | `e11d35af6f50fbe2f51d8ddd5a9d4f49860abbab7d73beae1f8524f13ad8945b` |
| HD2023_Dict.zip | `131d8f2f56a71078ea453989384cce91985fa2a29a94f168a718dedc6a466e3b` |

The respective directory universes contain 6,256 and 6,163 distinct UNITIDs.
The 2023 dictionary defines `ACT=C` as “Combined with other institution,”
`ACT=D` as “Delete out of business,” and `NEWID` as the UNITID where data is
found for merged schools. The importer requires the event UNITID in the 2022
universe; `C` and `D` also require 2023 `CYACTIVE=3` and `DEATHYR=2023`.
All archives must match the reviewed hashes.

Of 18 `C` rows, 17 have a different valid target UNITID; these are recorded
as `merged` and always require review. One (`413972`, Mitchells Academy) has
`NEWID=413972`, a self-reference. It is marked unresolved pending source
clarification. All 56 `D` rows have no successor and are recorded as closed.
The 21 `M` rows (“closed in current year, active has data”) are marked
unresolved pending a separate assessment of reporting period and data
availability. These 22 unresolved entries prevent same-UNITID fallback in
cross-release comparisons. `G` child
campuses, restored institutions, and source-only missing rows are likewise
not assigned guessed identity events. Same-UNITID comparisons retain the
existing pairing behavior, while mergers cannot be automatically aggregated.

```sh
edu-roi ipeds build-institution-history HD2022.zip HD2023.zip \
  HD2023_Dict.zip --output data/crosswalks/nces-hd2022-to-hd2023-events.json
```

The history file uses the HD2023 archive as `source_url` and `source_sha256`;
the importer additionally pins the previous directory and dictionary. A
comparison CLI's `--history-source` may verify the HD2023 archive against
the history file. The 95-entry event set is intentionally incomplete for UNITIDs
whose transitions the directory does not unambiguously document.
