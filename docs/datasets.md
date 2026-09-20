# Authoritative Dataset Inventory

**Status:** Plan 02 complete for architecture; revalidate endpoints at implementation time  
**Inventory date:** 2026-09-19

## Selection policy

Default analyses use the newest statistically appropriate **validated final** release, not necessarily the newest release. Provisional data require explicit opt-in and visible warnings. Every artifact is immutable and receives a manifest with source URL, release/vintage, retrieval time, SHA-256, byte size, publication status, and schema version.

## Source inventory

| Dataset | Canonical publisher | Primary use | Access/format | Cadence/version | Update strategy |
|---|---|---|---|---|---|
| ACS PUMS 1-year/5-year | U.S. Census Bureau | Earnings profiles/distributions | Census download/FTP; CSV archives plus dictionaries/code lists | Annual vintage; separate 1-year and 5-year products | Discover vintage from official PUMS data page/FTP, archive people files and documentation |
| IPEDS | NCES | Institution cost, aid, enrollment, completion, programs | IPEDS downloadable data files/Access database; CSV/ZIP and dictionaries | Annual collection; preliminary/provisional/final publication levels | Discover collection/release status, prefer final, retain survey component/version |
| College Scorecard | U.S. Department of Education | Institution/field earnings, net price, debt, repayment, completion | Bulk ZIPs and API (API key required); institution and field files | Irregular updates/change log; year/cohort fields within release | Snapshot bulk release and documentation; use change log; avoid live API as sole reproducible source |
| CPI | BLS | Dollar normalization | Public data tools/API and downloadable series | Monthly plus annual averages; revision/status per series | Snapshot selected series observations and metadata |
| OEWS | BLS | Occupational wage validation/context | Annual XLSX/TXT by national/state/metro/nonmetro/industry | May reference-year releases | Download “all data” plus documentation for exact release |
| Employment Projections | BLS | Forecast growth/openings context | XLSX tables/databases and crosswalks | Ten-year horizon, updated release | Snapshot tables, methodology, base/target years; label forecast |
| CIP | NCES | Canonical program taxonomy | Online taxonomy, Excel/Word downloads and crosswalks | Major revisions (current architecture must version) | Pin taxonomy and crosswalk edition; never merge versions silently |
| SOC | OMB/BLS | Occupation taxonomy | Manual, structure/definitions XLSX, crosswalks | Major revision cycles; 2018 SOC currently used by cited BLS pages | Pin exact SOC release/crosswalk; record many-to-many mappings |
| Federal Student Aid | U.S. Department of Education / FSA Partner Connect | Loan rates, limits, fees, program rules | Official web guidance and annual Electronic Announcements | Award-year/effective-date rules | Version effective-date rule tables; never hard-code “current” rate |
| Registered Apprenticeship | U.S. Department of Labor / Apprenticeship.gov | Later pathway counts/program context | Data/statistics pages and downloadable reports where offered | Reporting-year or live dashboard dependent | Snapshot official reports/metadata; assess outcome coverage before modeling returns |

## Current official observations

### ACS PUMS

Official page: https://www.census.gov/programs-surveys/acs/microdata.html

Census states that both 1-year and 5-year PUMS files are produced and made available through the Census microdata tool and FTP site. PUMS identifies nation, regions, divisions, states, and PUMAs; PUMA is the most detailed listed geography. Use downloadable people files, dictionaries, code lists, and the PUMS handbook.

Expected scale: hundreds of MB to multiple GB depending on product/geographies and compression. Determine byte size from HTTP metadata at acquisition rather than encoding estimates into policy.

### IPEDS

Official entry points:

- https://nces.ed.gov/ipeds/use-the-data
- https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx
- https://nces.ed.gov/ipeds/use-the-data/download-access-database

NCES pages were intermittently slow from the research environment; therefore implementation must test downloads directly and record final redirects. Use component-level files where practical. Record collection year, survey component, revision, and publication status.

The first implemented contract uses the Institutional Characteristics academic-year charges file only. Tuition is selected from `CHG1AY3` (in-district), `CHG2AY3` (in-state), or `CHG3AY3` (out-of-state) according to the scenario's required `tuition_residency`; `CHG4AY3` supplies books and supplies. Selection uses the exact `UNITID`. The resolver never substitutes one residency basis for another: if the requested column or value is unavailable, the result is insufficient data. These are institutional academic-year charges—not net price, program-specific price, aid, incremental living cost, or a guarantee of what a particular student pays. An explicit official NCES URL, release label, and publication status are required at registration; the code does not guess the newest release. Only schema-validated immutable artifacts in `VALIDATED` or `APPROVED` state may resolve scenarios.

Blank cells, negative sentinel values, absent UNITIDs, and absent exact releases remain unavailable. They are never converted to zero. Release-page discovery, dictionaries, imputation-status interpretation, residency policy beyond in-state charges, completion, aid, program production, and release comparison remain subsequent Plan 09 slices.

The live NCES release-information table reviewed on 2026-09-20 showed that release availability differs by component: Institutional Characteristics displayed 2025–26 provisional availability and final data through 2023–24, while **Pricing and Tuition (IC) displayed 2023–24 as provisional and final data only for 2009–10 through 2011–12**. Accordingly, `IC2023_AY` must be labeled `2023-24-provisional`; the broader IC final range does not make its pricing cells final. The release catalog treats component, collection year, publication status, data URL, dictionary URL, and inventory URL as one reviewed record. Default selection chooses the newest final release for the exact component. Preliminary or provisional data require both an exact release ID and explicit opt-in.

The catalog contract does not synthesize download paths or treat an adjacent component's status as the status of a charges release. The live complete-data-files page identifies the exact paired artifacts as `https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY.zip` and `https://nces.ed.gov/ipeds/complete-data-files/IC2023_AY_Dict.zip`. These reviewed links are stored together in the committed catalog snapshot. A newer provisional pricing release may be used only through explicit opt-in and must remain visibly provisional in outputs.

Inventory checks compare two complete, explicit catalog snapshots by release ID and component. They
classify newly observed entries as `DISCOVERED`, altered metadata or URLs as `CHANGED`, and entries
absent from the new snapshot as `MISSING`. Every difference requires review: the comparison does not
construct a likely URL, mutate the reviewed catalog, download a newly observed artifact, or treat a
missing page entry as proof that a release was withdrawn.

Run the same comparison from automation or during review with:

```console
edu-roi ipeds compare-inventory reviewed.json observed.json --fail-on-change
```

Output is deterministic JSON. Identical snapshots report `UNCHANGED`; differences report
`REVIEW_REQUIRED`. By default both states exit successfully so the JSON can be inspected. The
optional `--fail-on-change` flag exits 1 for review-required differences, while an invalid snapshot
exits 2.

### College Scorecard

Official data home: https://collegescorecard.ed.gov/data/

As observed on 2026-09-19, the site reported a June 10, 2026 update, a 470 MB all-files archive, a 23 MB most-recent institution ZIP, and a 17 MB most-recent field-of-study ZIP. Those sizes are observations, not permanent expectations.

The site documents institution-level history from 1996–97 through 2025–26 and field-of-study pooled award-year files. It also provides OPEID–UNITID crosswalks. The API requires a key. Prefer bulk snapshots for reproducibility.

Documentation and changes:

- https://collegescorecard.ed.gov/data/data-documentation/
- https://collegescorecard.ed.gov/data/api-documentation/
- https://collegescorecard.ed.gov/data/changelog/

The change log demonstrates why releases must be snapshotted: definitions and error handling change, including a prior correction where privacy-suppressed/unavailable integers had been returned as zero rather than null.

### BLS OEWS

Official tables: https://www.bls.gov/oes/tables.htm

The page exposes annual May releases, including national, state, metropolitan/nonmetropolitan, industry, and all-data downloads. Current page observation includes May 2025 XLSX and TXT. Treat OEWS as occupation evidence, never as direct major outcomes.

### BLS CPI

Official data: https://www.bls.gov/cpi/data.htm

Pin a specific series (proposed default: CPI-U U.S. city average, all items, annual average for annual modeling), observations, seasonal-adjustment status, and retrieval date. Do not mix monthly and annual conventions silently.

### BLS Employment Projections

Official occupational data: https://www.bls.gov/emp/data/occupational-data.htm

The page provides methodology, data definitions, XLSX occupational tables, National Employment Matrix data, openings/separations, and crosswalks. Current page observation identifies 2025–2035 projections and notes the occupational structure uses 2018 SOC. Forecasts must remain separate from historical evidence.

### CIP

Official taxonomy: https://nces.ed.gov/ipeds/cipcode/

Pin complete edition, code level (2/4/6 digit), title/description, and crosswalk. Program aggregation must retain the originating CIP vintage.

### SOC

Official 2018 SOC: https://www.bls.gov/soc/2018/home.htm

BLS provides the manual, structure, definitions, coding guidance, change files, and crosswalks. Store source code, target code, relationship, and mapping confidence. Do not assume one-to-one mappings.

### Federal Student Aid

Official borrower guidance:

- https://studentaid.gov/understand-aid/types/loans/interest-rates
- https://studentaid.gov/understand-aid/types/loans/subsidized-unsubsidized

Official partner announcements: https://fsapartners.ed.gov/knowledge-center/library/electronic-announcements

Rates, limits, origination fees, repayment programs, and effective dates can change materially. Model them as versioned rules keyed by disbursement date and borrower/program type.

### Registered Apprenticeship

Official statistics: https://www.apprenticeship.gov/data-and-statistics

Use for later pathway inventory and participation context. Before financial-return modeling, verify whether a release supports wages, completion, occupation, geography, and cohort outcomes. If not, return insufficient evidence instead of inferring outcomes.

## Licensing and usage

U.S. federal statistical data are generally intended for public use, but each artifact’s notices, API terms, disclosure restrictions, and citation requirements must be captured at download time. PUMS is disclosure-protected public microdata. College Scorecard and agency APIs may impose operational rate limits or key requirements even when the data are public.

## Storage estimate policy

Do not place source data in Git. At download time record:

- compressed and uncompressed bytes;
- record/row counts;
- extraction expansion ratio;
- expected processed Parquet size;
- retention by vintage.

Plan local storage for multiple ACS vintages; small metadata, manifests, schemas, and fixtures may be committed.

## Implementation-time verification checklist

- Resolve official URL and redirects.
- Confirm release/vintage and publication status.
- Download dictionary with the data.
- Record size and SHA-256.
- Confirm archive integrity.
- Compare schema with prior release.
- Validate classification vintage.
- Record license/notice.
- Run source-specific statistical checks.
- Never replace an earlier artifact.
