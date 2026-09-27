# Official C2022_A to C2023_A program awards universe review

The batch comparison was run on the final revised C2022_A and final C2023_A
NCES archives with the reviewed HD2022→HD2023 institution event file. The
2022 and 2023 data and dictionary ZIP hashes match the pinned source reviews;
the HD2023 archive matches the history file's SHA-256. The paired builders
produced 301,055 and 303,460 exact program award rows, respectively.

| Verified input | SHA-256 |
| --- | --- |
| C2022_A processed Parquet | `fd228fae423f06be6fe02545b3f7c92e23df9017f4ae994e2e96a231ecf9ef5e` |
| C2022_A processing manifest | `2057fc6d17398e772872d154c95181345dc58520c4b9a5922444ad8b314be27f` |
| C2023_A processed Parquet | `52297e47f307653cbf34f64c56e5b90171d9bc77f6bb912ad0a868d513d5732e` |
| C2023_A processing manifest | `3ce8b9d1b9d1fa8582fc7efba624f6428f2e179c4effa8eacd5cd3a86b49e166` |
| HD2023 identity source | `e11d35af6f50fbe2f51d8ddd5a9d4f49860abbab7d73beae1f8524f13ad8945b` |
| Immutable findings JSONL | `2b170fd4c77aa7dbb1a60182e8651e4ef9714ee35bb0addbfa243de350c3faed` |

At the default relative threshold of 25%, 5,865 of 6,042 source institutions
were comparable continuing identities. The target table had 5,960 institutions.
The command compared 282,921 exact `(UNITID, CIPCODE, MAJORNUM, AWLEVEL)` keys
within those continuing identities. It emitted 187,645 findings:

| Finding type | Count |
| --- | ---: |
| Count change meeting threshold | 152,630 |
| Program key added | 19,531 |
| Program key removed | 15,205 |
| Institution added | 95 |
| Institution missing history | 77 |
| Institution closed | 56 |
| Institution ambiguous history | 22 |
| Institution target collision | 5 |
| Source status changed | 12 |
| Source status requiring review | 12 |

Findings can overlap at a key; they are not unique programs or people. The
reported change for UNITID 100654, CIP `01.0999`, first major, bachelor's
award level is 9→18, matching the prior single-key check. The second run
reused the immutable output and confirmed the identical findings hash and
187,645 JSONL lines. The 38 MB findings file is reproducible and is not
committed to Git.

To reproduce, register and build each release with the pinned catalog, then
use their processed table paths:

```sh
edu-roi ipeds compare-program-award-tables \
  C2022_A/program-awards.parquet C2023_A/program-awards.parquet \
  findings.jsonl \
  --history data/crosswalks/nces-hd2022-to-hd2023-events.json \
  --history-source HD2023.zip
```

Institution events without an unambiguous continuing identity are recorded
as institution findings and their program rows are excluded from numerical
pairing. Key additions and removals within continuing institutions are review
findings. Counts refer to awards in different reporting periods, not distinct
graduates, completion rates, or causal changes in program quality. Individual
findings require review before scenario or recommendation use.
