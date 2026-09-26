# IPEDS EF2023A enrollment source review

**Scope:** Source catalog and cohort-key review only. Registration, processed
transformation, and scenario use require a subsequent implementation slice.

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
A later reader must preserve raw cells and statuses, distinguish zero from
missing/negative cells, verify all four key columns, and report the exact
population and fall-2023 period. No source status meaning is inferred here.
