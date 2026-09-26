# IPEDS EF2023A enrollment source review

**Scope:** Paired final-source registration, exact raw cohort lookup, immutable
processed table, verified processed lookup, and contextual scenario review.

The official [IPEDS complete data files inventory](https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?year=2023&surveyNumber=2)
identifies EF2023A as fall 2023 enrollment by race/ethnicity, gender,
attendance status, and level of student, revised January 2026. The reviewed
2023–24 final pair is:

| Source | URL | SHA-256 observed | Selected member |
| --- | --- | --- | --- |
| Data | `https://nces.ed.gov/ipeds/complete-data-files/EF2023A.zip` | `0238ff58ddf603b8606b1b131311e0b569323b787c395dc83b7830c987096cb0` | `ef2023a_rv.csv` |
| Dictionary | `https://nces.ed.gov/ipeds/complete-data-files/EF2023A_Dict.zip` | `777e929c493b16b001573b99880ddb64a2835301072ff32fb1a20bf38903d9bc` | `ef2023a.xlsx` |

The data ZIP also contains the initial `ef2023a.csv`; the catalog selects the
revised member. The workbook Introduction says **Final/revised release**. Its
`Varlist` defines `UNITID`, `EFALEVEL`, `LINE`, `SECTION`, `LSTUDY`, `EFTOTLT`
(grand total), and the paired `XEFTOTLT` source status. `FrequenciesRV`
provides labels for each level and line. The revised CSV contains 115,190
rows across 5,914 distinct institutions, with no duplicate `(UNITID,
EFALEVEL)` keys in the observed archive. A UNITID occurs at multiple levels;
registration must validate composite keys, not reject repeated UNITIDs.

Initial reviewed total-count populations:

| `EFALEVEL` | `LINE` | `SECTION` | `LSTUDY` | Population |
| --- | --- | --- | --- | --- |
| `1` | `29` | `3` | `4` | All students, total enrollment |
| `24` | `1` | `1` | `1` | Full-time, first-time, first-year, degree-seeking undergraduates |
| `39` | `2` | `1` | `1` | Full-time undergraduate transfer-ins in other degree/certificate-seeking group |
| `44` | `15` | `2` | `1` | Part-time, first-time, first-year, degree-seeking undergraduates |
| `59` | `16` | `2` | `1` | Part-time undergraduate transfer-ins in other degree/certificate-seeking group |

These are distinct overlapping categories. They must not be summed into a
single cohort or converted into admission, completion, or transfer
probabilities. The transfer-in category is an enrollment count at the reporting
institution, not an outcome for students who left it.

For University of Washington (`UNITID=236948`), the revised `EFTOTLT` cells
are respectively 55,620; 6,928; 1,415; 83; and 141, each with `XEFTOTLT=R`.
The paired registration checks the final revised workbook definitions and
frequency labels, every revised CSV row's `(UNITID, EFALEVEL)` uniqueness,
required columns, numeric count cells, and the selected cohorts' exact
`LINE`, `SECTION`, and `LSTUDY` layout. It stores separate immutable data and
dictionary artifacts. A lookup verifies both source hashes and returns the
explicit population, raw count, source status, fall year, and paired IDs.
Blank/negative cells and absent keys remain insufficient data, while zero is
observed; no source status meaning is inferred.

```bash
education-roi ipeds register-enrollment --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
education-roi ipeds resolve-enrollment 236948 full_time_first_time --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
education-roi ipeds build-enrollment --catalog data/manifests/ipeds-release-catalog.json --root /path/to/project
education-roi ipeds resolve-enrollment-table /path/to/enrollment.parquet 236948 full_time_first_time
education-roi scenario review-enrollment scenarios/examples/workforce-high-school.yaml /path/to/education.yaml --scenario-id example-bachelors --table /path/to/enrollment.parquet --cohort full_time_first_time
```

An isolated official-source run validated the full 115,190-row revised member
and resolved the five University of Washington counts above. Enrollment
categories must not be summed into a probability or substituted for each other.

The processed Parquet table retains one sorted row per reviewed institution and
`EFALEVEL` key, with cohort label, exact `LINE`/`SECTION`/`LSTUDY` keys,
parsed and raw count, source status, fall year, and paired artifact IDs. The
deterministic path includes both source hashes and transformation version; an
adjacent manifest records the output hash, key columns, and definition mapping.
An isolated official build produced 20,849 reviewed cohort rows, and a second
build returned the identical manifest. The processed-table reader verifies
the complete table and sidecar hashes, exact release and field mapping, sorted
unique composite keys, all raw-to-parsed count cells, and paired row lineage
before returning a selected observation. It includes both output hashes and
the exact population keys. An isolated official lookup returned all five
University of Washington counts and statuses above.

For an education scenario, pin `ipeds-fall-enrollment` to `2023-24-final` and
select one explicit cohort. Full-time and part-time cohorts require matching
attendance; the four undergraduate first-time/transfer-in cohorts require an
undergraduate credential. `all_students` is an institution-wide context count
and does not assert a matching credential or attendance population. The
scenario review output includes its configuration hash and is marked
`CONTEXT_ONLY`: it does not populate completion or transfer outcomes.
