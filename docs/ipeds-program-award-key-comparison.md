# Exact-key cross-release program award review

`edu-roi ipeds compare-program-award-key PREVIOUS.parquet CURRENT.parquet
UNITID CIPCODE MAJORNUM AWLEVEL` compares one exact CIP 2020, first/second
major, and award-level key in the final revised C2022_A and C2023_A tables.
It verifies both complete tables and processing manifests before comparing
counts. The periods are July 2021–June 2022 and July 2022–June 2023.

The report retains both table and manifest hashes, paired source artifact
IDs, raw counts and `XCTOTALT` status labels. A relative count change at or
above `--threshold` (default 0.25), zero-to-nonzero change, unavailable
observation, imputation flag, or status change requires review. Absolute
and relative changes are omitted when the institution identity cannot be
paired as a high-confidence continuation. `--history` accepts exact-release
UNITID history; `--history-source` can verify its source ZIP hash. A changed
or unresolved identity blocks numeric comparison. `--target-unitid` names
an explicit successor but does not waive review. `--fail-on-review` exits 1;
invalid input exits 2.

An isolated comparison using the official 301,055-row C2022_A and
303,460-row C2023_A tables found nine versus 18 reported awards for
UNITID 100654, CIP `01.0999`, first major, bachelor's level. The +100%
change requires review under the default threshold. These are awards
conferred in different years, not distinct graduates, a completion
probability, or evidence of a causal program effect. Full-universe program
comparison and aggregation across CIP or institution changes remain gated.
