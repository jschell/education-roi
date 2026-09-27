# NCES CIP 2010→2020 crosswalk source review

The official [NCES CIP resources page](https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56)
offers “Crosswalk 2010-2020” as `Crosswalk2010to2020.csv` through its Excel
download control. The downloaded CSV has SHA-256
`3aa75a01b38169b3093f17a15bc3e72d769192ef3fed8935b12215bc4ca087c7`.
The importer requires that exact digest, six reviewed columns, and all action
counts before writing `data/crosswalks/nces-cip-2010-to-2020.json`.

| NCES action | Rows | Treatment |
| --- | ---: | --- |
| No substantive changes | 1,994 | Same code, exact/high confidence |
| Moved to | 149 | Changed code, revised/medium confidence, manual review |
| Deleted | 12 | No mapping |
| New | 544 | No 2010 predecessor |

There are 2,699 source rows and 2,143 directional mappings. In particular,
`43.0116` moves to `43.0403`, while deleted `60.0406` has no mapping even
though its row repeats the old code in the 2020 column. An unchanged code with
a text change remains exact at the code level; the mapping note records that
the label changed. This source does not establish reverse mappings or assign
program outcomes across editions.

Rebuild from the official download with:

```sh
edu-roi ipeds build-cip-crosswalk Crosswalk2010to2020.csv \
  --output data/crosswalks/nces-cip-2010-to-2020.json
```

The command accepts an identical existing output and rejects a conflicting
one. Subsequent source changes require an explicit review of the digest,
actions, and mappings.
