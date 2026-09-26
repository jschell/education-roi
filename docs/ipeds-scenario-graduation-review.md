# Scenario review of IPEDS graduation evidence

The processed GR2022 and GR2023 bachelor's cohort tables provide verified
institution observations for separate first-time, full-time entry cohorts.
To attach an observation as context, pin `ipeds-graduation-rates` to the exact
`2022-23-final` or `2023-24-final` release in the education scenario's data
policy. Build the corresponding processed GR table first, then run:

```bash
education-roi scenario review-graduation scenarios/examples/workforce-high-school.yaml /path/to/education.yaml --scenario-id example-bachelors --table /path/to/graduation.parquet
```

The command checks the scenario graph, bachelor's credential, full-time
attendance, release pin, table and manifest lineage, exact UNITID, and the
reviewed bachelor's award at 150% of normal time. Output includes cohort year,
denominator, award count, source statuses, and artifact/table hashes. An absent
or unavailable cohort remains insufficient data.

`completion_use` is `CONTEXT_ONLY`: the institution cohort is not a program or
individual completion probability, and it does not resolve on-time, late,
transfer, or leave-without-credential branches. Such a mapping requires
separate cohort and outcome definitions.
