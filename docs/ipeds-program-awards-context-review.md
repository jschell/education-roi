# Contextual program awards review

`edu-roi ipeds review-program-awards-context` connects a source CIP edition
and institution UNITID to the exact-key, verified final C2023_A table.

```sh
edu-roi ipeds review-program-awards-context TABLE.parquet 236948 \
  2023-24-final 11.0101 2010 1 5 \
  --crosswalk data/crosswalks/nces-cip-2010-to-2020.json
```

The positional values identify the source UNITID, release, CIP code and
edition, major number, and award level. For a different institution release,
pass a directional `--history` file. A CIP edition change requires a
directional `--crosswalk` file. Ambiguous mappings require explicit
`--target-cip-code` or `--target-unitid`, and still carry review state.

Only an exact/high-confidence CIP mapping and continuing/high-confidence
institution identity proceed to the table lookup. That lookup verifies the
entire table, sidecar, and raw-to-parsed count cells. Revised CIP codes,
merged or unresolved institutions, and other identity changes return
`REVIEW_REQUIRED` without an award observation. Deleted CIP codes fail
resolution. A missing exact table key yields `INSUFFICIENT_DATA`.

The result includes both directional resolutions and their source hashes.
An observed count means awards conferred at that key, not distinct graduates
or a completion probability. This command does not combine multiple CIP
targets or aggregate merger institutions.
